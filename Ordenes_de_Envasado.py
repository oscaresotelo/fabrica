import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime, date
import time
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from io import BytesIO

DB_PATH = "minerva.db"

def get_connection(timeout=10):
    """
    Obtiene una conexión a SQLite configurada con row_factory.
    """
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    conn.row_factory = sqlite3.Row
    return conn

def execute_sql_with_retry(conn, query, params=(), retries=5, delay=0.1):
    """
    Ejecuta una consulta SQL con reintentos en caso de 'database is locked'.
    """
    for i in range(retries):
        try:
            cur = conn.cursor()
            cur.execute(query, params)
            return cur
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and i < retries - 1:
                st.warning(f"Base de datos bloqueada. Reintento {i+1}/{retries} en {delay * (2 ** i):.2f} s...")
                time.sleep(delay * (2 ** i))
            else:
                raise
        except Exception:
            raise
    raise Exception("Fallo al adquirir el bloqueo de la base de datos después de múltiples reintentos.")

def ensure_columns_exist():
    """
    Asegura que en la tabla ordenes_envasado existan las columnas fecha_pedido y fecha_envasado.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(ordenes_envasado);")
        cols = [r["name"] for r in cur.fetchall()]
        altered = False
        if "fecha_pedido" not in cols:
            cur.execute("ALTER TABLE ordenes_envasado ADD COLUMN fecha_pedido TEXT;")
            altered = True
        if "fecha_envasado" not in cols:
            cur.execute("ALTER TABLE ordenes_envasado ADD COLUMN fecha_envasado TEXT;")
            altered = True
        if altered:
            conn.commit()
    finally:
        conn.close()

try:
    ensure_columns_exist()
except Exception as e:
    try:
        st.warning(f"No fue posible asegurar columnas adicionales en ordenes_envasado: {e}")
    except Exception:
        pass

def fetch_df(query, params=()):
    conn = get_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
        return df
    finally:
        conn.close()

def agregar_stock_productos_envasados(conn, cliente_id, receta_id, envase_id, lote, cantidad_envases):
    """
    Agrega stock de productos envasados dentro de la transacción abierta.
    """
    fecha_ingreso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    execute_sql_with_retry(conn, """
        INSERT INTO stock_productos_envasados (cliente_id, receta_id, envase_id, lote, cantidad, fecha_ingreso)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (cliente_id, receta_id, envase_id, lote, cantidad_envases, fecha_ingreso))

def obtener_lotes_disponibles_para_producto_general(cliente_id, producto_id_general):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT pr.id AS produccion_id, pr.lote, pr.cantidad_litros, pr.litros_envasados, pr.cantidad_real_litros,
                   (pr.cantidad_real_litros - pr.litros_envasados) AS litros_remanentes,
                   ped.receta_id
            FROM producciones pr
            JOIN pedidos_produccion ped ON pr.pedido_id = ped.id
            JOIN recetas r ON ped.receta_id = r.id
            JOIN productos p ON r.id = p.id_receta
            WHERE ped.cliente_id = ? AND p.id = ? AND (pr.cantidad_real_litros - pr.litros_envasados) > 0
            ORDER BY pr.fecha ASC, pr.id ASC
        """, (cliente_id, producto_id_general))
        return cur.fetchall()
    finally:
        conn.close()

def get_productos_con_litros_disponibles_agregado():
    conn = get_connection()
    try:
        query = """
        SELECT
            pc.cliente_id,
            c.nombre AS cliente_nombre,
            pc.producto_id AS producto_id_pc,
            p.id AS producto_id_general,
            p.nombre AS producto_nombre_general,
            r.id AS receta_id,
            r.nombre AS receta_nombre,
            SUM(pr.cantidad_real_litros - pr.litros_envasados) AS total_litros_disponibles
        FROM productos_clientes pc
        JOIN clientes c ON pc.cliente_id = c.id
        JOIN productos p ON pc.producto_id = p.id
        JOIN recetas r ON p.id_receta = r.id
        JOIN pedidos_produccion pp ON pp.cliente_id = pc.cliente_id AND pp.receta_id = r.id
        JOIN producciones pr ON pr.pedido_id = pp.id
        WHERE (pr.cantidad_real_litros - pr.litros_envasados) > 0
        GROUP BY pc.cliente_id, c.nombre, pc.producto_id, p.id, p.nombre, r.id, r.nombre
        HAVING total_litros_disponibles > 0
        ORDER BY c.nombre, p.nombre;
        """
        df = pd.read_sql_query(query, conn)
        return df.to_dict(orient='records')
    finally:
        conn.close()

def get_envases_cliente(cliente_id):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("""
            SELECT id, descripcion, capacidad_litros
            FROM envases
            WHERE cliente_id = ?
        """, (cliente_id,)).fetchall()

def get_productos_cliente_with_receta_info(cliente_id):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("""
            SELECT pc.id, p.nombre AS producto_nombre, r.nombre AS receta_nombre,
                   r.id AS receta_id, p.id AS producto_general_id,
                   pc.uso, pc.linea
            FROM productos_clientes pc
            JOIN productos p ON pc.producto_id = p.id
            JOIN recetas r ON p.id_receta = r.id
            WHERE pc.cliente_id = ?
        """, (cliente_id,)).fetchall()

def get_producto_cliente_details(producto_cliente_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT uso, linea
            FROM productos_clientes
            WHERE id = ?
        """, (producto_cliente_id,))
        return cursor.fetchone()

def crear_orden_final(cliente_id, producto_cliente_id, envase_id, lotes_a_consumir_final, capacidad_envase, envasadora_id, fecha_pedido=None):
    """
    Crea órdenes de envasado consumiendo de múltiples lotes de producción.
    
    Agnóstico a las columnas 'uso' y 'linea': la validación y el descuento de stock 
    en 'stock_envases_clientes' se realizan únicamente utilizando cliente_id y envase_id.
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        fecha_creacion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Normalizar fecha_pedido
        if fecha_pedido is None:
            fecha_pedido_str = date.today().isoformat()
        elif isinstance(fecha_pedido, datetime):
            fecha_pedido_str = fecha_pedido.date().isoformat()
        elif isinstance(fecha_pedido, date):
            fecha_pedido_str = fecha_pedido.isoformat()
        else:
            fecha_pedido_str = str(fecha_pedido)

        ordenes_creadas_count = 0
        litros_totales_envasados_en_esta_orden = 0.0
        lotes_afectados_info = []

        # 1. Calcular total de unidades necesarias
        total_unidades_necesarias = sum(
            round(ld.get('Litros a Envasar', 0.0) / capacidad_envase)
            for ld in lotes_a_consumir_final
            if ld.get('Litros a Envasar', 0.0) > 0
        )

        if total_unidades_necesarias <= 0:
            st.error("❌ No hay unidades a envasar. Especifique una cantidad válida.")
            return False

        # 2. Verificar stock total en stock_envases_clientes solo por cliente_id y envase_id
        cur.execute("""
            SELECT SUM(cantidad) AS stock_total 
            FROM stock_envases_clientes
            WHERE cliente_id = ? AND envase_id = ?
        """, (cliente_id, envase_id))
        stock_row = cur.fetchone()
        stock_disponible = stock_row["stock_total"] if (stock_row and stock_row["stock_total"] is not None) else 0

        if stock_disponible < total_unidades_necesarias:
            st.error(f"❌ Stock insuficiente de envases: se necesitan {total_unidades_necesarias} unidades pero hay {stock_disponible} disponibles en inventario.")
            return False

        # 3. Iniciar transacción única
        execute_sql_with_retry(conn, "BEGIN;")

        for lote_data in lotes_a_consumir_final:
            produccion_id = lote_data.get('produccion_id')
            lote_nombre = lote_data.get('lote_nombre')
            litros_a_consumir_de_este_lote = lote_data.get('Litros a Envasar', 0.0)
            receta_id_lote = lote_data.get('receta_id')

            if litros_a_consumir_de_este_lote <= 0:
                continue

            unidades_a_consumir_de_este_lote = round(litros_a_consumir_de_este_lote / capacidad_envase)
            litros_a_consumir_de_este_lote_ajustado = unidades_a_consumir_de_este_lote * capacidad_envase

            if unidades_a_consumir_de_este_lote <= 0:
                continue

            # Insertar en ordenes_envasado
            execute_sql_with_retry(conn, """
                INSERT INTO ordenes_envasado (
                    produccion_id, fecha, fecha_pedido, producto_cliente_id,
                    envase_id, cantidad_unidades, estado, envasadora_id
                ) VALUES (?, ?, ?, ?, ?, ?, 'pendiente', ?)
            """, (produccion_id, fecha_creacion, fecha_pedido_str, producto_cliente_id, envase_id, unidades_a_consumir_de_este_lote, envasadora_id))

            # Actualizar litros_envasados en producciones
            execute_sql_with_retry(conn, """
                UPDATE producciones
                SET litros_envasados = litros_envasados + ?
                WHERE id = ?
            """, (litros_a_consumir_de_este_lote_ajustado, produccion_id))

            # Agregar al stock de productos envasados
            agregar_stock_productos_envasados(conn, cliente_id, receta_id_lote, envase_id, lote_nombre, unidades_a_consumir_de_este_lote)

            # Descontar envases de stock_envases_clientes (sin filtrar por uso/linea)
            cur.execute("""
                SELECT rowid, cantidad FROM stock_envases_clientes
                WHERE cliente_id = ? AND envase_id = ? AND cantidad > 0
                ORDER BY rowid ASC
            """, (cliente_id, envase_id))
            rows = cur.fetchall()

            unidades_por_descontar = unidades_a_consumir_de_este_lote
            for r in rows:
                if unidades_por_descontar <= 0:
                    break
                r_id = r["rowid"]
                r_cant = r["cantidad"]
                descontar = min(unidades_por_descontar, r_cant)

                execute_sql_with_retry(conn, """
                    UPDATE stock_envases_clientes
                    SET cantidad = cantidad - ?
                    WHERE rowid = ?
                """, (descontar, r_id))
                unidades_por_descontar -= descontar

            litros_totales_envasados_en_esta_orden += litros_a_consumir_de_este_lote_ajustado
            ordenes_creadas_count += 1
            lotes_afectados_info.append(f"Lote {lote_nombre} (ID: {produccion_id}): {unidades_a_consumir_de_este_lote} unidades ({litros_a_consumir_de_este_lote_ajustado:.2f} L)")

        conn.commit()

        if ordenes_creadas_count > 0:
            st.success(f"🎉 Orden finalizada exitosamente. Se crearon {ordenes_creadas_count} órdenes de envasado para un total de {litros_totales_envasados_en_esta_orden:.2f} L.")
            st.info("Detalle de lotes afectados:")
            for info in lotes_afectados_info:
                st.write(f"- {info}")

            # Limpiar session state
            st.session_state.current_order_selection = []
            st.session_state.last_selected_product_general_id = None
            st.session_state.last_selected_cliente_id = None
            st.session_state.last_selected_envase_id = None
            st.session_state.last_selected_capacidad_envase = None
            st.session_state.last_selected_producto_cliente_id_final = None
            st.session_state.last_selected_envasadora_id = None
            st.session_state.last_selected_fecha_pedido = None

            return True
        else:
            st.error("No se pudo crear ninguna orden de envasado. Revise las cantidades y el stock disponible.")
            return False

    except sqlite3.IntegrityError as e:
        if conn:
            conn.rollback()
        st.error(f"Error de integridad de la base de datos al crear la orden: {e}.")
        return False
    except Exception as e:
        if conn:
            conn.rollback()
        st.error(f"Ocurrió un error inesperado al crear la orden: {e}")
        return False
    finally:
        if conn:
            conn.close()

def generar_pdf_orden_envasado(buffer, cliente, producto, envase, capacidad_litros, detalle_lotes_df, total_litros, total_unidades, envasadora_id, fecha_pedido=None, fecha_envasado=None, uso_linea=None):
    """
    Genera un PDF con la información de la orden.
    """
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    capacidad_cc = capacidad_litros * 1000

    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, height - 2 * cm, "ORDEN DE ENVASADO")

    c.setFont("Helvetica", 10)
    fecha_text = datetime.now().strftime('%d/%m/%Y %H:%M')
    c.drawString(2 * cm, height - 3 * cm, f"Generado: {fecha_text}")
    if fecha_pedido:
        c.drawString(2 * cm, height - 4 * cm, f"Fecha pedido: {fecha_pedido}")
    if fecha_envasado:
        c.drawString(2 * cm, height - 4.75 * cm, f"Fecha envasado: {fecha_envasado}")

    c.drawString(2 * cm, height - 5.5 * cm, f"Cliente: {cliente}")
    c.drawString(2 * cm, height - 6.25 * cm, f"Producto: {producto}")
    if uso_linea:
        c.drawString(2 * cm, height - 7 * cm, f"Uso / Línea: {uso_linea}")
        y = height - 8 * cm
    else:
        y = height - 7 * cm

    c.drawString(2 * cm, y, f"Envase: {envase} ({capacidad_cc:.0f} cc)")
    y -= 0.75 * cm
    c.drawString(2 * cm, y, f"Envasadora: {envasadora_id}")
    y -= 0.75 * cm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, y, "Detalle por Lote:")
    y -= 0.75 * cm

    c.setFont("Helvetica", 10)
    for _, row in detalle_lotes_df.iterrows():
        lote = row.get('lote_nombre', '')
        litros = row.get('Litros a Envasar', 0.0)
        unidades = row.get('Unidades Calculadas', 0)
        c.drawString(2.5 * cm, y, f"Lote {lote}: {litros:.3f} L → {unidades} unidades")
        y -= 0.5 * cm
        if y < 3 * cm:
            c.showPage()
            y = height - 2 * cm

    y -= 0.5 * cm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2 * cm, y, f"TOTAL: {total_litros:.3f} L / {total_unidades} unidades")

    c.showPage()
    c.save()
    return buffer.getvalue()

def ordenes_envasado():
    st.title("📦 Órdenes de Envasado")

    st.warning("⚠️ Si experimenta errores de 'base de datos bloqueada', asegúrese de que 'minerva.db' no esté abierto en otra aplicación.")

    # Inicializar session_state
    if 'current_order_selection' not in st.session_state:
        st.session_state.current_order_selection = []
    if 'last_selected_envasadora_id' not in st.session_state:
        st.session_state.last_selected_envasadora_id = None
    if 'last_selected_fecha_pedido' not in st.session_state:
        st.session_state.last_selected_fecha_pedido = None

    productos_agregados = get_productos_con_litros_disponibles_agregado()
    if not productos_agregados:
        st.info("No hay productos con litros disponibles para envasar en ninguna producción.")
        return

    clientes_con_productos = sorted(list(set([p['cliente_nombre'] for p in productos_agregados])))

    tab1, tab2 = st.tabs(["📝 Crear Orden de Envasado", "🏷️ Marcar como Envasada"])

    with tab1:
        selected_cliente_nombre = st.selectbox("Seleccionar Cliente", clientes_con_productos, key="select_cliente_envasado_tab1")
        productos_para_cliente = [p for p in productos_agregados if p['cliente_nombre'] == selected_cliente_nombre]

        opciones_producto_agregado = [
            f"{p['producto_nombre_general']} (Total Disp: {p['total_litros_disponibles']:.2f} L)"
            for p in productos_para_cliente
        ]
        selected_producto_agregado_label = st.selectbox("Seleccionar Producto para Envasar", opciones_producto_agregado, key="select_producto_agregado_tab1")

        selected_agregado_data = next(
            p for p in productos_para_cliente
            if f"{p['producto_nombre_general']} (Total Disp: {p['total_litros_disponibles']:.2f} L)" == selected_producto_agregado_label
        )

        cliente_id = selected_agregado_data['cliente_id']
        cliente_nombre = selected_agregado_data['cliente_nombre']
        producto_id_general = selected_agregado_data['producto_id_general']
        producto_nombre_general = selected_agregado_data['producto_nombre_general']
        receta_id = selected_agregado_data['receta_id']
        receta_nombre = selected_agregado_data['receta_nombre']
        total_litros_disponibles_para_producto = selected_agregado_data['total_litros_disponibles']

        st.markdown("### Producto seleccionado para Envasar:")
        st.write(f"📘 **Producto:** `{producto_nombre_general}`")
        st.write(f"🧑‍💼 **Cliente:** `{cliente_nombre}`")
        st.write(f"🔄 **Total Litros Disponibles para este Producto (todos los lotes):** `{total_litros_disponibles_para_producto:.2f} L`")

        st.markdown("---")
        st.subheader("Configuración de Producto Cliente")
        productos_clientes_entries = get_productos_cliente_with_receta_info(cliente_id)

        producto_cliente_id_final = None
        nombre_producto_seleccionado_pc = ""

        matching_pc_entries_by_product_and_receta = [
            (pc_id, prod_name, rec_name_db, rec_id_db, prod_general_id_db, uso_pc, linea_pc)
            for pc_id, prod_name, rec_name_db, rec_id_db, prod_general_id_db, uso_pc, linea_pc in productos_clientes_entries
            if prod_general_id_db == producto_id_general and rec_id_db == receta_id
        ]

        if len(matching_pc_entries_by_product_and_receta) == 1:
            producto_cliente_id_final = matching_pc_entries_by_product_and_receta[0][0]
            nombre_producto_seleccionado_pc = matching_pc_entries_by_product_and_receta[0][1]
            st.info(f"Producto Cliente asignado automáticamente (por Producto y Receta): **{nombre_producto_seleccionado_pc}** (ID: {producto_cliente_id_final})")
        elif len(matching_pc_entries_by_product_and_receta) > 1:
            opciones_pc = {
                f"{name} (Receta: {rec_name}, Uso: {uso_pc}, Línea PC: {linea_pc}, ID: {pc_id})": pc_id
                for pc_id, name, rec_name, _, _, uso_pc, linea_pc in matching_pc_entries_by_product_and_receta
            }
            selected_pc_option = st.selectbox("Seleccionar configuración de Producto Cliente", list(opciones_pc.keys()), key="select_pc_config_tab1")
            producto_cliente_id_final = opciones_pc[selected_pc_option]
            nombre_producto_seleccionado_pc = selected_pc_option.split(' (Receta:')[0]
        else:
            matching_pc_entries_only_by_product = [
                (pc_id, prod_name, rec_name_db, rec_id_db, prod_general_id_db, uso_pc, linea_pc)
                for pc_id, prod_name, rec_name_db, rec_id_db, prod_general_id_db, uso_pc, linea_pc in productos_clientes_entries
                if prod_general_id_db == producto_id_general
            ]
            if not matching_pc_entries_only_by_product:
                st.error("❌ No hay productos válidos registrados para este cliente en 'productos_clientes' que coincidan con el producto general.")
                return
            opciones_pc_fallback = {
                f"{name} (Receta: {rec_name}, Uso: {uso_pc}, Línea PC: {linea_pc}, ID: {pc_id})": pc_id
                for pc_id, name, rec_name, _, _, uso_pc, linea_pc in matching_pc_entries_only_by_product
            }
            selected_pc_option_fallback = st.selectbox("Seleccionar configuración de Producto Cliente (Alternativa)", list(opciones_pc_fallback.keys()), key="select_pc_config_fallback_tab1")
            producto_cliente_id_final = opciones_pc_fallback[selected_pc_option_fallback]
            nombre_producto_seleccionado_pc = selected_pc_option_fallback.split(' (Receta:')[0]

        envases = get_envases_cliente(cliente_id)
        if not envases:
            st.error("⚠️ No hay envases registrados para este cliente en la tabla 'envases'.")
            return

        st.markdown("### ➕ Crear Orden de Envasado para este Producto")

        envase_options = {e[1]: e[0] for e in envases}
        envase_sel_desc = st.selectbox("Seleccionar envase", list(envase_options.keys()), key="select_envase_order_tab1")
        envase_id = envase_options[envase_sel_desc]
        capacidad_envase = next(e[2] for e in envases if e[0] == envase_id)

        fecha_pedido_input = st.date_input("Fecha del pedido de envasado", value=st.session_state.get('last_selected_fecha_pedido', date.today()), key="fecha_pedido_input_tab1")

        st.markdown("---")
        st.subheader("Seleccionar Lotes y Cantidades a Envasar")

        lotes_disponibles_data = obtener_lotes_disponibles_para_producto_general(cliente_id, producto_id_general)
        if not lotes_disponibles_data:
            st.warning("No hay lotes de producción disponibles para este producto. No se puede crear la orden.")
            return

        df_lotes = pd.DataFrame([
            {
                "produccion_id": row["produccion_id"],
                "lote_nombre": row["lote"],
                "Litros del Lote Original": row["cantidad_real_litros"],
                "litros_remanentes": row["litros_remanentes"],
                "receta_id": row["receta_id"],
                "cantidad_real_litros": row["cantidad_real_litros"],
                "Litros a Envasar": 0.0
            }
            for row in lotes_disponibles_data
        ])

        if df_lotes["litros_remanentes"].sum() <= 0:
            st.warning("Todos los lotes disponibles para este producto tienen 0 litros remanentes. No se puede envasar.")
            return

        st.write("Especifique los litros a envasar de cada lote:")
        edited_df_lotes = st.data_editor(
            df_lotes,
            column_config={
                "produccion_id": st.column_config.NumberColumn("ID Producción", disabled=True),
                "lote_nombre": st.column_config.TextColumn("Lote", disabled=True),
                "Litros del Lote Original": st.column_config.NumberColumn("Litros del Lote Original", disabled=True, format="%.2f L"),
                "litros_remanentes": st.column_config.NumberColumn("Litros Disponibles", disabled=True, format="%.2f L"),
                "receta_id": st.column_config.NumberColumn("Receta ID", disabled=True),
                "cantidad_real_litros": st.column_config.NumberColumn("Cantidad Real de Litros", disabled=True, format="%.2f L"),
                "Litros a Envasar": st.column_config.NumberColumn("Litros a Envasar", min_value=0.0, step=0.01, format="%.2f L")
            },
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key="lotes_a_envasar_editor_tab1"
        )

        litros_a_envasar_total_seleccionado = edited_df_lotes["Litros a Envasar"].sum()
        cantidad_unidades_total_calculada = round(litros_a_envasar_total_seleccionado / capacidad_envase)

        st.markdown(f"🧪 **Litros TOTALES a envasar (seleccionados):** `{litros_a_envasar_total_seleccionado:.2f} L`")
        st.markdown(f"📦 **Unidades TOTALES a envasar (calculadas):** `{cantidad_unidades_total_calculada}`")
        st.markdown("---")

        if st.button("➕ Agregar a Orden Pendiente", key="add_to_pending_order_button_tab1"):
            if litros_a_envasar_total_seleccionado <= 0:
                st.error("❌ Debe especificar al menos 1 litro a envasar para agregar a la orden pendiente.")
            else:
                lotes_a_consumir_filtrados = edited_df_lotes[edited_df_lotes["Litros a Envasar"] > 0].to_dict(orient='records')
                valid_lotes = True
                for lote_data in lotes_a_consumir_filtrados:
                    produccion_id = lote_data['produccion_id']
                    litros_a_envasar_de_lote = lote_data['Litros a Envasar']
                    original_remanente = df_lotes[df_lotes['produccion_id'] == produccion_id]['litros_remanentes'].iloc[0]
                    if litros_a_envasar_de_lote > original_remanente:
                        st.error(f"❌ Error de validación: No se puede envasar {litros_a_envasar_de_lote:.2f} L del lote {lote_data['lote_nombre']}. Solo hay {original_remanente:.2f} L disponibles.")
                        valid_lotes = False
                        break
                    if litros_a_envasar_de_lote < 0:
                        st.error(f"❌ Error de validación: La cantidad a envasar del lote {lote_data['lote_nombre']} no puede ser negativa.")
                        valid_lotes = False
                        break

                if valid_lotes:
                    st.session_state.current_order_selection = lotes_a_consumir_filtrados
                    st.session_state.last_selected_product_general_id = producto_id_general
                    st.session_state.last_selected_cliente_id = cliente_id
                    st.session_state.last_selected_envase_id = envase_id
                    st.session_state.last_selected_capacidad_envase = capacidad_envase
                    st.session_state.last_selected_producto_cliente_id_final = producto_cliente_id_final
                    existing_envasadora = st.session_state.get('last_selected_envasadora_id')
                    if existing_envasadora in [1, 2, 3, 4]:
                        st.session_state.last_selected_envasadora_id = existing_envasadora
                    else:
                        st.session_state.last_selected_envasadora_id = 1
                    st.session_state.last_selected_fecha_pedido = fecha_pedido_input
                    st.success("✅ Lotes agregados a la orden pendiente. Revise abajo para finalizar.")
                    st.rerun()

        st.markdown("---")
        st.subheader("📋 Orden Pendiente de Envasado (Previsualización)")

        if not st.session_state.current_order_selection:
            st.info("No hay ítems en la orden pendiente. Agregue lotes desde la sección superior.")
        else:
            df_pending_order = pd.DataFrame(st.session_state.current_order_selection)
            pc_details_for_summary = None
            if st.session_state.last_selected_producto_cliente_id_final:
                pc_details_for_summary = get_producto_cliente_details(st.session_state.last_selected_producto_cliente_id_final)

            current_producto_nombre_general = producto_nombre_general
            current_envase_sel_desc = next((e[1] for e in envases if e[0] == st.session_state.last_selected_envase_id), "N/A")

            df_pending_order['Unidades Calculadas'] = round(df_pending_order['Litros a Envasar'] / st.session_state.last_selected_capacidad_envase)

            st.dataframe(df_pending_order[['lote_nombre', 'Litros a Envasar', 'Unidades Calculadas']], use_container_width=True)
            total_litros_pending = df_pending_order['Litros a Envasar'].sum()
            total_unidades_pending = int(df_pending_order['Unidades Calculadas'].sum())

            st.markdown(f"**Total Litros a Envasar:** `{total_litros_pending:.2f} L`")
            st.markdown(f"**Total Unidades a Envasar:** `{total_unidades_pending}`")

            if pc_details_for_summary:
                st.markdown(f"**Producto Cliente Seleccionado (Uso/Línea):** `{pc_details_for_summary['uso']} / {pc_details_for_summary['linea']}`")
            else:
                st.markdown(f"**Producto Cliente Seleccionado (Uso/Línea):** `N/A`")

            st.markdown("---")
            st.subheader("Seleccionar Envasadora")
            envasadora_options = [1, 2, 3, 4]
            default_envasadora = st.session_state.get('last_selected_envasadora_id')
            if default_envasadora not in envasadora_options:
                default_envasadora = envasadora_options[0]
            st.session_state.last_selected_envasadora_id = st.selectbox(
                "Selecciona la envasadora a utilizar:",
                options=envasadora_options,
                index=envasadora_options.index(default_envasadora),
                key="envasadora_selector_tab1"
            )
            st.write(f"Envasadora seleccionada: **{st.session_state.last_selected_envasadora_id}**")
            st.markdown("---")

            st.warning("⚠️ Revise la orden pendiente. Una vez finalizada, los cambios se aplicarán a la base de datos.")

            col_finalizar, col_cancelar, col_pdf = st.columns(3)
            with col_finalizar:
                if st.button("✅ Finalizar Orden", key="finalize_order_button_tab1"):
                    if st.session_state.last_selected_producto_cliente_id_final is None:
                        st.error("Error: Producto Cliente no definido para la orden pendiente.")
                    elif st.session_state.last_selected_envase_id is None:
                        st.error("Error: Envase no definido para la orden pendiente.")
                    elif not st.session_state.current_order_selection:
                        st.error("Error: La orden pendiente está vacía.")
                    elif st.session_state.last_selected_envasadora_id is None:
                        st.error("Error: Debe seleccionar una envasadora.")
                    else:
                        if crear_orden_final(
                            st.session_state.last_selected_cliente_id,
                            st.session_state.last_selected_producto_cliente_id_final,
                            st.session_state.last_selected_envase_id,
                            st.session_state.current_order_selection,
                            st.session_state.last_selected_capacidad_envase,
                            st.session_state.last_selected_envasadora_id,
                            fecha_pedido=st.session_state.get('last_selected_fecha_pedido')
                        ):
                            st.rerun()

            with col_cancelar:
                if st.button("❌ Cancelar Orden Pendiente", key="cancel_pending_order_button_tab1"):
                    st.session_state.current_order_selection = []
                    st.session_state.last_selected_product_general_id = None
                    st.session_state.last_selected_cliente_id = None
                    st.session_state.last_selected_envase_id = None
                    st.session_state.last_selected_capacidad_envase = None
                    st.session_state.last_selected_producto_cliente_id_final = None
                    st.session_state.last_selected_envasadora_id = None
                    st.session_state.last_selected_fecha_pedido = None
                    st.info("Orden cancelada.")
                    st.rerun()

            with col_pdf:
                buffer_pdf_tab1 = BytesIO()
                df_ped_pdf = pd.DataFrame(st.session_state.current_order_selection)
                df_ped_pdf['Unidades Calculadas'] = round(df_ped_pdf['Litros a Envasar'] / st.session_state.last_selected_capacidad_envase)
                tot_lit = df_ped_pdf['Litros a Envasar'].sum()
                tot_uni = int(df_ped_pdf['Unidades Calculadas'].sum())

                pdf_bytes_tab1 = generar_pdf_orden_envasado(
                    buffer_pdf_tab1,
                    cliente=cliente_nombre,
                    producto=producto_nombre_general,
                    envase=current_envase_sel_desc,
                    capacidad_litros=st.session_state.last_selected_capacidad_envase,
                    detalle_lotes_df=df_ped_pdf,
                    total_litros=tot_lit,
                    total_unidades=tot_uni,
                    envasadora_id=st.session_state.last_selected_envasadora_id,
                    fecha_pedido=st.session_state.get('last_selected_fecha_pedido')
                )
                st.download_button(
                    label="📄 Previsualizar PDF",
                    data=pdf_bytes_tab1,
                    file_name="orden_envasado_borrador.pdf",
                    mime="application/pdf",
                    key="btn_pdf_preview_tab1"
                )

    with tab2:
        st.subheader("🏷️ Órdenes Pendientes de Envasar")
        conn = get_connection()
        try:
            df_pendientes = pd.read_sql_query("""
                SELECT oe.id AS orden_id, oe.fecha, oe.fecha_pedido, oe.cantidad_unidades, oe.envasadora_id, oe.estado,
                       p.nombre AS producto, c.nombre AS cliente, e.descripcion AS envase, e.capacidad_litros,
                       pr.lote
                FROM ordenes_envasado oe
                JOIN productos_clientes pc ON oe.producto_cliente_id = pc.id
                JOIN clientes c ON pc.cliente_id = c.id
                JOIN productos p ON pc.producto_id = p.id
                JOIN envases e ON oe.envase_id = e.id
                JOIN producciones pr ON oe.produccion_id = pr.id
                WHERE oe.estado = 'pendiente'
                ORDER BY oe.id DESC
            """, conn)
        finally:
            conn.close()

        if df_pendientes.empty:
            st.info("🎉 No hay órdenes pendientes de envasar en este momento.")
        else:
            st.dataframe(df_pendientes, use_container_width=True)

            st.markdown("### Acciones sobre Orden Pendiente")
            orden_id_sel = st.selectbox("Seleccionar ID de Orden para procesar", df_pendientes["orden_id"].tolist(), key="select_orden_marcar_tab2")

            col_marcar, col_pdf_tab2 = st.columns(2)

            with col_marcar:
                if st.button("✅ Marcar como Envasada", key="btn_marcar_envasada_tab2"):
                    conn_m = get_connection()
                    try:
                        fecha_env_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        execute_sql_with_retry(conn_m, """
                            UPDATE ordenes_envasado
                            SET estado = 'envasado', fecha_envasado = ?
                            WHERE id = ?
                        """, (fecha_env_str, orden_id_sel))
                        conn_m.commit()
                        st.success(f"✅ Orden #{orden_id_sel} marcada como envasada exitosamente.")
                        st.rerun()
                    except Exception as e_m:
                        if conn_m: conn_m.rollback()
                        st.error(f"Error al actualizar orden: {e_m}")
                    finally:
                        if conn_m: conn_m.close()

            with col_pdf_tab2:
                orden_row = df_pendientes[df_pendientes["orden_id"] == orden_id_sel].iloc[0]
                pdf_buffer = BytesIO()
                det_lote_df = pd.DataFrame([{
                    "lote_nombre": orden_row["lote"],
                    "Litros a Envasar": orden_row["cantidad_unidades"] * orden_row["capacidad_litros"],
                    "Unidades Calculadas": orden_row["cantidad_unidades"]
                }])
                pdf_data = generar_pdf_orden_envasado(
                    pdf_buffer,
                    cliente=orden_row["cliente"],
                    producto=orden_row["producto"],
                    envase=orden_row["envase"],
                    capacidad_litros=orden_row["capacidad_litros"],
                    detalle_lotes_df=det_lote_df,
                    total_litros=orden_row["cantidad_unidades"] * orden_row["capacidad_litros"],
                    total_unidades=orden_row["cantidad_unidades"],
                    envasadora_id=orden_row["envasadora_id"],
                    fecha_pedido=orden_row.get("fecha_pedido")
                )
                st.download_button(
                    label="📄 Descargar PDF de la Orden",
                    data=pdf_data,
                    file_name=f"orden_envasado_{orden_id_sel}.pdf",
                    mime="application/pdf",
                    key=f"btn_pdf_download_{orden_id_sel}"
                )