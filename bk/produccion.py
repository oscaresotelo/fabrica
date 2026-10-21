import streamlit as st
import sqlite3
from datetime import datetime, date
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import uuid
import pandas as pd

DB_PATH = "minerva.db"

def gestionar_produccion():
    # --- Estilos ---
    st.markdown("""
    <style>
        .metric-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .stButton>button {
            background-color: #0072C6;
            color: white;
            font-weight: 600;
            border-radius: 8px;
            padding: 10px 20px;
            margin-top: 10px;
        }
        .stButton>button:hover {
            background-color: #005a9e;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("# 🏭 Gestión de Producción")
    st.markdown("---")

    def generar_numero_lote():
        return f"Lote-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

    def obtener_pedidos():
        with sqlite3.connect(DB_PATH) as conn:
            return conn.execute('''
                SELECT pp.id, c.nombre, r.nombre, pp.cantidad, pp.numero_pedido, pp.fecha, pp.estado, pp.receta_id, pp.lote, pp.cliente_id
                FROM pedidos_produccion pp
                JOIN clientes c ON pp.cliente_id = c.id
                JOIN recetas r ON pp.receta_id = r.id
                WHERE pp.estado IN ('pendiente', 'en_proceso')
                ORDER BY pp.fecha
            ''').fetchall()

    def obtener_ingredientes(receta_id):
        with sqlite3.connect(DB_PATH) as conn:
            return conn.execute('''
                SELECT mp.id, mp.nombre, ri.cantidad, ri.unidad, ri.materia_prima_id
                FROM receta_ingredientes ri
                JOIN materias_primas mp ON ri.materia_prima_id = mp.id
                WHERE ri.receta_id = ?
            ''', (receta_id,)).fetchall()

    def obtener_ingredientes_modificados_db(pedido_id):
        with sqlite3.connect(DB_PATH) as conn:
            return conn.execute('''
                SELECT mp.id, mp.nombre, rm.cantidad, rm.unidad, rm.materia_prima_id
                FROM receta_modificada rm
                JOIN materias_primas mp ON rm.materia_prima_id = mp.id
                WHERE rm.pedido_id = ?
            ''', (pedido_id,)).fetchall()

    def obtener_stock():
        """Lee cantidad_actual desde stock_materias_primas y devuelve dict {materia_prima_id: {'stock': value}}"""
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT materia_prima_id, cantidad_actual FROM stock_materias_primas").fetchall()
            return {r[0]: {"stock": float(r[1]) if r[1] is not None else 0.0} for r in rows}

    def obtener_materias_primas():
        with sqlite3.connect(DB_PATH) as conn:
            return conn.execute("SELECT id, nombre, unidad FROM materias_primas").fetchall()
    
    def obtener_composicion_colorante(conn, colorante_combinado_id):
        """Obtiene la composición de un colorante combinado desde la base de datos."""
        cur = conn.cursor()
        cur.execute("""
            SELECT colorante_primario_id, proporcion
            FROM composicion_colorantes
            WHERE colorante_combinado_id = ?
        """, (colorante_combinado_id,))
        return cur.fetchall()

    # ---------------------------
    # Conversor / cálculo batch
    # ---------------------------
    def convertir_a_litros(cantidad, unidad):
        """
        Convierte una cantidad dada en la unidad indicada a litros.
        Suposiciones:
        - 'L', 'LITRO', 'LITROS', 'L' => ya está en litros.
        - 'ML', 'CM3', 'CC' => dividido 1000 -> litros.
        - 'G' => dividido 1000 -> kg -> asumimos densidad 1 => litros.
        - 'KG' => asumimos 1 kg = 1 litro (densidad ~1 para la mayoría de ingredientes acuosos).
        - Si unidad es desconocida, intentamos interpretarla: si contiene 'L' o 'LT' => litros; si contiene 'G' => gramos.
        """
        if unidad is None:
            unidad = ""
        u = unidad.strip().upper()
        try:
            c = float(cantidad)
        except Exception:
            c = 0.0

        if u in ["L", "LITRO", "LITROS", "LTR", "LTS"]:
            return c
        if u in ["ML", "CM3", "CC"]:
            return c / 1000.0
        if u in ["G", "GR", "GRS"]:
            return c / 1000.0  # gramos -> kg -> litros (asumiendo densidad 1)
        if u in ["KG", "KILO", "KILOS", "KILOGRAMO", "KILOGRAMOS"]:
            return c  # asumimos 1 kg == 1 L (densidad ~1)
        # heurísticos
        if "ML" in u:
            return c / 1000.0
        if "G" in u and "KG" not in u:
            return c / 1000.0
        if "KG" in u:
            return c
        if "L" in u:
            return c
        # fallback: tratar como litros
        return c

    def calcular_batch_base(receta_id):
        """
        Suma las cantidades de la receta (convertidas a litros)
        y devuelve el batch_base en litros.
        Si por algún motivo no hay ingredientes, devuelve 1.0 para evitar divisiones por cero.
        """
        filas = obtener_ingredientes(receta_id)
        total = 0.0
        for _mpid, _nombre, cantidad, unidad, _mp in filas:
            total += convertir_a_litros(cantidad, unidad)
        return total if total > 0 else 1.0

    # ---------------------------
    # Descontar stock (usando batch real)
    # ---------------------------
    def descontar_stock(conn, ingredientes, cantidad_a_producir, cur, receta_id=None):
        """
        Descuenta el stock de materias primas, incluyendo los colorantes combinados.
        - ingredientes: lista de tuplas (mp.id, mp.nombre, cantidad_base, unidad, materia_prima_id)
        - cantidad_a_producir: litros que se van a producir (la función no decide si usar cantidad_real o cantidad de pedido)
        - receta_id: si se pasa, se usa para calcular el batch_base real; si no, se conserva compatibilidad usando 200
        Retorna: None si OK, o lista de faltantes [(nombre, requerido, disponible), ...]
        """
        ingredientes_escala = {}
        faltantes = []
        stock = obtener_stock()  # lee 'cantidad_actual'

        # escoger batch_base real
        if receta_id is not None:
            batch_base = calcular_batch_base(receta_id)
        else:
            batch_base = 200.0  # retrocompatibilidad

        # Calcular cantidades escaladas (en las mismas unidades que receta_base -> pero aquí trabajamos con 'cantidad' tal cual)
        for ingr_id, ingr_nombre, cantidad_base, unidad, materia_prima_id in ingredientes:
            # cantidad_base está en la unidad indicada por 'unidad' (p.ej. LITROS, KG, etc.).
            # Para la comparación de stock asumimos que stock está en la misma unidad base que 'stock_materias_primas'
            # (normalmente cantidad en litros o kilos según cómo gestionas stock). Aquí escalamos proporcionalmente.
            factor = float(cantidad_a_producir) / float(batch_base)
            cantidad_escalada = float(cantidad_base) * factor
            ingredientes_escala[materia_prima_id] = ingredientes_escala.get(materia_prima_id, 0.0) + cantidad_escalada

        # Verificar y descontar (incluye colorantes combinados)
        for materia_prima_id, cantidad_escalada in ingredientes_escala.items():
            # comprobar si es colorante combinado
            cur.execute("""
                SELECT 1 FROM composicion_colorantes WHERE colorante_combinado_id = ?
            """, (materia_prima_id,))
            es_colorante_combinado = cur.fetchone() is not None

            if es_colorante_combinado:
                composicion = obtener_composicion_colorante(conn, materia_prima_id)
                if not composicion:
                    st.warning(f"No se encontró la composición del colorante combinado con ID: {materia_prima_id}.")
                    continue
                for componente_id, proporcion in composicion:
                    cantidad_componente = cantidad_escalada * float(proporcion)
                    stock_componente = stock.get(componente_id, {"stock": 0.0})["stock"]
                    if stock_componente < cantidad_componente - 1e-9:
                        cur.execute("SELECT nombre FROM materias_primas WHERE id = ?", (componente_id,))
                        row = cur.fetchone()
                        ingrediente_nombre = row[0] if row else f"ID {componente_id}"
                        faltantes.append((ingrediente_nombre, cantidad_componente, stock_componente))
                    else:
                        nuevo_stock = max(stock_componente - cantidad_componente, 0.0)
                        cur.execute("""
                            UPDATE stock_materias_primas SET cantidad_actual = ? WHERE materia_prima_id = ?
                        """, (nuevo_stock, componente_id))
                        stock[componente_id] = {"stock": nuevo_stock}
            else:
                stock_actual = stock.get(materia_prima_id, {"stock": 0.0})["stock"]
                if stock_actual < cantidad_escalada - 1e-9:
                    cur.execute("SELECT nombre FROM materias_primas WHERE id = ?", (materia_prima_id,))
                    row = cur.fetchone()
                    ingrediente_nombre = row[0] if row else f"ID {materia_prima_id}"
                    faltantes.append((ingrediente_nombre, cantidad_escalada, stock_actual))
                else:
                    nuevo_stock = max(stock_actual - cantidad_escalada, 0.0)
                    cur.execute("""
                        UPDATE stock_materias_primas SET cantidad_actual = ? WHERE materia_prima_id = ?
                    """, (nuevo_stock, materia_prima_id))
                    stock[materia_prima_id] = {"stock": nuevo_stock}

        if faltantes:
            return faltantes
        return None

    def generar_pdf_receta(cliente, receta, cantidad, numero_pedido, fecha_pedido, lote, ingredientes):
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        width, height = letter
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, height - 50, f"Receta de Producción - {receta}")
        c.setFont("Helvetica", 12)
        y = height - 80
        for txt in [f"Cliente: {cliente}", f"Pedido: {numero_pedido}", f"Fecha pedido: {fecha_pedido}", f"Cantidad: {cantidad} litros", f"Lote: {lote or 'No asignado'}"]:
            c.drawString(50, y, txt)
            y -= 18
        c.drawString(50, y, "Ingredientes escalados:")
        y -= 20
        for nombre, cant, unidad in ingredients_normalize_for_pdf(ingredientes):
            if y < 50:
                c.showPage()
                y = height - 50
            c.drawString(70, y, f"- {nombre}: {cant:.3f} {unidad}")
            y -= 18
        c.drawString(50, y - 30, "Firma supervisor: _______________________")
        c.showPage()
        c.save()
        buf.seek(0)
        return buf

    def ingredients_normalize_for_pdf(ingredientes):
        """
        Normaliza cantidades para la presentación en PDF:
        Si la unidad es L o LITROS y la cantidad < 1 -> mostrar en cm3
        Si la unidad es KG y cantidad < 1 -> mostrar en g
        ingredientes: lista de (nombre, cantidad, unidad)
        """
        out = []
        for nombre, cant, unidad in ingredientes:
            u = (unidad or "").strip().lower()
            if u in ["l", "litros", "litro"] and abs(cant) < 1:
                out.append((nombre, cant * 1000.0, "cm³"))
            elif u in ["kg", "kilos", "kilo"] and abs(cant) < 1:
                out.append((nombre, cant * 1000.0, "g"))
            else:
                out.append((nombre, cant, unidad))
        return out

    def imprimir_rotulo(cliente, receta, lote, fecha_prod):
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        height = letter[1]
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 100, f"Producto: {receta}")
        c.drawString(50, height - 130, f"Número de Lote: {lote}")
        c.drawString(50, height - 160, f"Fecha producida: {fecha_prod}") 
        c.drawString(50, height - 190, f"Cliente: {cliente}")
        c.showPage()
        c.save()
        buf.seek(0)
        return buf

    # --- Lógica de la interfaz ---

    def handle_multiselect_change():
        """Callback para guardar la selección en el estado de la sesión."""
        st.session_state.current_selections = st.session_state.multiselect_key

    if 'current_selections' not in st.session_state:
        st.session_state.current_selections = []

    pedidos = obtener_pedidos()
    if not pedidos:
        st.info("ℹ️ No hay pedidos pendientes ni en proceso.")
        # st.stop()

    pedido_labels = [f"{p[1]} - {p[2]} - {p[4]} - Estado: {p[6].capitalize()}" for p in pedidos]

    st.multiselect("Seleccionar pedido",
                    pedido_labels,
                    default=st.session_state.current_selections,
                    key="multiselect_key",
                    on_change=handle_multiselect_change)

    pedidos_seleccionados = [pedidos[pedido_labels.index(seleccion)] for seleccion in st.session_state.current_selections if seleccion in pedido_labels]

    for i, pedido in enumerate(pedidos_seleccionados):
        try:
            pedido_id, cliente, receta, cantidad, numero_pedido, fecha, estado, receta_id, lote, cliente_id = pedido

            pedido_label = pedido_labels[pedido_labels.index(st.session_state.current_selections[i])]

            with st.expander(f"Detalles del pedido: {numero_pedido}"):
                stock = obtener_stock()

                ingredientes_modificados = obtener_ingredientes_modificados_db(pedido_id)
                if ingredientes_modificados:
                    ingredientes_raw = ingredientes_modificados
                else:
                    ingredientes_raw = obtener_ingredientes(receta_id)

                # calcular batch_base de la receta para mostrar escalado correcto
                batch_base = calcular_batch_base(receta_id)
                factor = float(cantidad) / float(batch_base)
                ingredientes = [(i[1], float(i[2]) * factor, i[3]) for i in ingredientes_raw]
                ingr_dict = {i[4]: float(i[2]) * factor for i in ingredientes_raw}

                materias_primas = obtener_materias_primas()
                materias_primas_dict = {mp[0]: mp[1] for mp in materias_primas}
                materias_primas_labels = {mp[0]: f"{mp[1]} ({mp[2]})" for mp in materias_primas}

                col1, col2 = st.columns([1,4])
                with col1:
                    st.markdown("### 🧾 Información del Pedido")
                    st.write(f"**Cliente:** {cliente}")
                    st.write(f"**Receta:** {receta}")
                    st.write(f"**Cantidad:** {cantidad} litros")
                    st.write(f"**N° Pedido:** {numero_pedido}")
                    st.write(f"**Fecha:** {fecha}")
                    st.write(f"**Estado:** `{estado}`")
                    
                    if lote:
                        st.write(f"**Lote asignado:** `{lote}`")
                        
                with col2:
                    st.markdown("### 🧪 Ingredientes Escalados")

                    with st.form(key=f"form_ingredientes_{pedido_id}"):
                        st.markdown("#### ✏️ Editar Ingredientes")
                        modificaciones = {}
                        for j, (ingr_id, ingr_nombre, cantidad_base, unidad, materia_prima_id) in enumerate(ingredientes_raw):
                            col_ingr1, col_ingr2, col_ingr3 = st.columns(3)

                            with col_ingr1:
                                nueva_materia_prima_id = st.selectbox(
                                    f"MP - {ingr_nombre} ({unidad})",
                                    options=list(materias_primas_labels.keys()),
                                    format_func=lambda x: materias_primas_labels[x],
                                    index=list(materias_primas_labels.keys()).index(materia_prima_id) if materia_prima_id in materias_primas_labels else 0,
                                    key=f"materia_prima_{pedido_id}_{ingr_id}_{j}"
                                )
                            with col_ingr2:
                                nueva_cantidad = st.number_input(
                                    "Cantidad",
                                    value=float(cantidad_base),
                                    format="%.3f",
                                    key=f"cantidad_{pedido_id}_{ingr_id}_{j}"
                                )
                            with col_ingr3:
                                nueva_unidad = st.text_input(
                                    "Unidad",
                                    value=unidad,
                                    key=f"unidad_{pedido_id}_{ingr_id}_{j}"
                                )

                            modificaciones[ingr_id] = {
                                'materia_prima_id': nueva_materia_prima_id,
                                'materia_prima_nombre': materias_primas_dict.get(nueva_materia_prima_id, "N/A"),
                                'cantidad': nueva_cantidad,
                                'unidad': nueva_unidad
                            }
                            
                        if st.form_submit_button("Guardar cambios en ingredientes"):
                            with sqlite3.connect(DB_PATH) as conn:
                                cur = conn.cursor()
                                try:
                                    conn.execute("BEGIN")
                                    cur.execute("DELETE FROM receta_modificada WHERE pedido_id = ?", (pedido_id,))
                                    for ingr_id, mod in modificaciones.items():
                                        cur.execute("""
                                            INSERT INTO receta_modificada (pedido_id, receta_id, materia_prima_id, cantidad, unidad)
                                            VALUES (?, ?, ?, ?, ?)
                                        """, (pedido_id, receta_id, mod['materia_prima_id'], mod['cantidad'], mod['unidad']))
                                    conn.commit()
                                    st.success("✅ Cambios en ingredientes guardados en la base de datos.")
                                    st.rerun()
                                except sqlite3.Error as e:
                                    conn.rollback()
                                    st.error(f"Ocurrió un error al guardar los cambios: {e}")

                    # mostrar ingredientes escalados usando batch_base real
                    batch_base = calcular_batch_base(receta_id)
                    factor = float(cantidad) / float(batch_base)
                    ingredientes_mostrar = [(materias_primas_dict.get(i[4], "N/A"), float(i[2]) * factor, i[3]) for i in ingredientes_raw]
                    st.dataframe(pd.DataFrame(ingredientes_mostrar, columns=["Ingrediente", "Cantidad", "Unidad"])
                                         .style.format({"Cantidad": "{:.3f}"}), use_container_width=True)

                colA, colB = st.columns(2)
                with colA:
                    st.download_button(label=f"📄 Descargar receta PDF - {numero_pedido}", data=generar_pdf_receta(cliente, receta, cantidad, numero_pedido, fecha, lote, ingredientes),
                                             file_name=f"receta_{numero_pedido}_{lote or 'sin_lote'}.pdf", mime="application/pdf")
                with colB:
                    if lote:
                        st.download_button(label=f"🏷️ Imprimir rótulo - {numero_pedido}", data=imprimir_rotulo(cliente, receta, lote, fecha),
                                                 file_name=f"rotulo_{numero_pedido}_{lote}.pdf", mime="application/pdf")

                st.markdown("---")

                if estado == "pendiente":
                    st.subheader("⚙️ Opciones para estado Pendiente")
                    opcion = st.selectbox(f"Operación para {numero_pedido}:", ["Simular sin descontar stock", "Simular descontando y mostrar faltantes", "Confirmar producción"], key=f"opcion_{pedido_id}")
                    
                    if st.button(f"Ejecutar operación para {numero_pedido}", key=f"button_{pedido_id}"):
                        if opcion.startswith("Simular"):
                            ingredientes_simulacion = obtener_ingredientes_modificados_db(pedido_id)
                            if not ingredientes_simulacion:
                                ingredientes_simulacion = obtener_ingredientes(receta_id)
                            
                            with sqlite3.connect(DB_PATH) as conn:
                                cur = conn.cursor()
                                # Simulación: usar cantidad del pedido para escalar
                                faltantes = descontar_stock(conn, ingredientes_simulacion, cantidad, cur, receta_id=receta_id)
                                if faltantes:
                                    st.warning("⚠️ Ingredientes faltantes:")
                                    for nombre, req, disp in faltantes:
                                        st.write(f"- {nombre}: requiere {req:.3f}, disponible {disp:.3f}")
                                    conn.rollback()  # Deshace los cambios de la simulación
                                else:
                                    st.success("✅ Suficiente stock disponible.")
                        elif opcion == "Confirmar producción":
                            lote_nuevo = generar_numero_lote()
                            with sqlite3.connect(DB_PATH) as conn:
                                cur = conn.cursor()
                                try:
                                    conn.execute("BEGIN")
                                    conn.execute("""
                                        INSERT OR IGNORE INTO lotes (numero, fecha, cliente_id, receta_id)
                                        VALUES (?, ?, ?, ?)
                                    """, (lote_nuevo, datetime.now().strftime("%Y-%m-%d"), cliente_id, receta_id))
                                    conn.execute("UPDATE pedidos_produccion SET estado = 'en_proceso', lote = ? WHERE id = ?", (lote_nuevo, pedido_id))
                                    conn.commit()
                                    st.success(f"✅ Pedido en proceso. Lote: {lote_nuevo}")
                                    if pedido_label in st.session_state.current_selections:
                                        st.session_state.current_selections.remove(pedido_label)
                                    st.rerun()
                                except sqlite3.Error as e:
                                    conn.rollback()
                                    st.error(f"Ocurrió un error al confirmar la producción: {e}")

                elif estado == "en_proceso":
                    st.subheader("⚙️ Opciones para estado En Proceso")
                    
                    fecha_produccion = st.date_input(
                        "🗓️ **Fecha de Realización de la Producción**",
                        value=datetime.now().date(),
                        max_value=datetime.now().date(),
                        key=f"fecha_prod_{pedido_id}",
                        help="Seleccione la fecha real en la que terminó la producción."
                    )
                    fecha_sql = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    cantidad_real = st.number_input("Cantidad real producida (litros):", min_value=0.0, value=float(cantidad), step=0.01, key=f"cantidad_real_{pedido_id}")
                    opcion = st.selectbox("Operación:", ["Simular descontando stock y mostrar faltantes", "Producir descontando stock"], key=f"opcion_en_proceso_{pedido_id}")
                    if st.button(f"Ejecutar operación para {numero_pedido}", key=f"button_en_proceso_{pedido_id}"):
                        with sqlite3.connect(DB_PATH) as conn:
                            cur = conn.cursor()
                            
                            try:
                                conn.execute("BEGIN")

                                ingredientes_finales = obtener_ingredientes_modificados_db(pedido_id)
                                if not ingredientes_finales:
                                    ingredientes_finales = obtener_ingredientes(receta_id)

                                if opcion == "Simular descontando stock y mostrar faltantes":
                                    # Simulación: usamos la cantidad del pedido para verificar
                                    faltantes = descontar_stock(conn, ingredientes_finales, cantidad, cur, receta_id=receta_id)
                                    if faltantes:
                                        st.warning("⚠️ Ingredientes faltantes:")
                                        for nombre, req, disp in faltantes:
                                            st.write(f"- {nombre}: requiere {req:.3f}, disponible {disp:.3f}")
                                    else:
                                        st.success("✅ Suficiente stock disponible para la producción.")
                                    conn.rollback()  # Deshace los cambios de la simulación

                                elif opcion == "Producir descontando stock":
                                    # PRODUCCIÓN REAL: usamos cantidad_real para descontar stock
                                    faltantes = descontar_stock(conn, ingredientes_finales, cantidad_real, cur, receta_id=receta_id)
                                    if faltantes:
                                        st.warning("⚠️ No se puede completar la producción debido a ingredientes faltantes:")
                                        for nombre, req, disp in faltantes:
                                            st.write(f"- {nombre}: requiere {req:.3f}, disponible {disp:.3f}")
                                        conn.rollback()
                                        st.stop()

                                    # Registrar movimientos usando la cantidad_real escalada según batch_base
                                    ingr_dict = {}
                                    batch_base = calcular_batch_base(receta_id)
                                    factor_real = float(cantidad_real) / float(batch_base)
                                    for ingr_id, ingr_nombre, cantidad_base, unidad, materia_prima_id in ingredientes_finales:
                                        cantidad_escalada = float(cantidad_base) * factor_real
                                        
                                        # Verifica si el ingrediente es un colorante combinado
                                        cur.execute("""
                                            SELECT 1 FROM composicion_colorantes WHERE colorante_combinado_id = ?
                                        """, (materia_prima_id,))
                                        es_colorante_combinado = cur.fetchone() is not None

                                        if es_colorante_combinado:
                                            composicion = obtener_composicion_colorante(conn, materia_prima_id)
                                            for componente_id, proporcion in composicion:
                                                cantidad_componente = cantidad_escalada * float(proporcion)
                                                ingr_dict[componente_id] = ingr_dict.get(componente_id, 0.0) + cantidad_componente
                                        else:
                                            ingr_dict[materia_prima_id] = ingr_dict.get(materia_prima_id, 0.0) + cantidad_escalada

                                    for materia_prima_id, cantidad_ingrediente in ingr_dict.items():
                                        cur.execute("""
                                            INSERT INTO movimientos_materia_prima
                                            (materia_prima_id, fecha, cantidad, tipo_movimiento, destino, lote)
                                            VALUES (?, ?, ?, 'egreso', 'produccion', ?)
                                        """, (materia_prima_id, fecha_sql, -abs(cantidad_ingrediente), lote))

                                    # Actualizar/insertar lote con fecha de producción (día)
                                    cur.execute("""
                                        INSERT OR IGNORE INTO lotes (numero, fecha, cliente_id, receta_id)
                                        VALUES (?, ?, ?, ?)
                                    """, (lote, fecha_produccion.strftime("%Y-%m-%d"), cliente_id, receta_id))
                                    
                                    # Registrar produccion (fecha y hora)
                                    cur.execute("""
                                        INSERT INTO producciones (pedido_id, fecha, lote, estado, cantidad_litros, litros_envasados, cantidad_real_litros)
                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                    """, (pedido_id, fecha_sql, lote, 'producido', cantidad, 0, cantidad_real))
                                    
                                    cur.execute("UPDATE pedidos_produccion SET estado = 'producido' WHERE id = ?", (pedido_id,))

                                    cur.execute("DELETE FROM receta_modificada WHERE pedido_id = ?", (pedido_id,))
                                    
                                    conn.commit()
                                    st.success(f"✅ Producción registrada el **{fecha_produccion.strftime('%Y-%m-%d')}**. Lote: {lote} - Cantidad real: {cantidad_real} litros")
                                    if pedido_label in st.session_state.current_selections:
                                        st.session_state.current_selections.remove(pedido_label)
                                    st.rerun()

                            except sqlite3.Error as e:
                                conn.rollback()
                                st.error(f"Ocurrió un error al registrar la producción: {e}")
                else:
                    st.info("ℹ️ Este pedido no está en estado pendiente ni en proceso.")

        except (ValueError, IndexError) as e:
            st.warning(f"El pedido seleccionado ya no está disponible. Error: {e}")
            if pedido_label in st.session_state.current_selections:
                st.session_state.current_selections.remove(pedido_label)
            st.rerun()
            
# Ejecutar
gestionar_produccion()
