import streamlit as st
import sqlite3
from datetime import datetime, date
import pandas as pd

def compras_materia_prima():
    DB_PATH = "minerva.db"

    def get_connection():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    st.title("🛒 Gestión de Proveedores y Movimientos de Materia Prima")

    # --- 1. Alta de Proveedores ---
    st.subheader("📋 Alta de Proveedores")
    with st.expander("➕ Registrar nuevo proveedor"):
        with st.form("form_proveedor"):
            nombre = st.text_input("Nombre del proveedor", max_chars=100)
            contacto = st.text_input("Nombre de contacto")
            cuit = st.text_input("CUIT")
            direccion = st.text_input("Dirección")
            telefono = st.text_input("Teléfono")
            email = st.text_input("Email")
            submitted_prov = st.form_submit_button("Guardar proveedor")

            if submitted_prov:
                if nombre.strip() == "":
                    st.error("El nombre del proveedor es obligatorio.")
                else:
                    with get_connection() as conn:
                        try:
                            conn.execute("""
                                INSERT INTO proveedores (nombre, contacto, cuit, direccion, telefono, email)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (nombre.strip(), contacto.strip(), cuit.strip(), direccion.strip(), telefono.strip(), email.strip()))
                            st.success(f"Proveedor '{nombre}' guardado correctamente.")
                        except sqlite3.IntegrityError:
                            st.error("Ese proveedor ya existe.")

    # --- 2. Carga de datos ---
    with get_connection() as conn:
        proveedores_rows = conn.execute("SELECT id, nombre FROM proveedores ORDER BY nombre").fetchall()
        materias_rows = conn.execute("SELECT id, nombre || ' (' || unidad || ')' AS nombre FROM materias_primas ORDER BY nombre").fetchall()
        cot_row = conn.execute("SELECT venta FROM cotizacion_dolar ORDER BY datetime(fecha_hora) DESC LIMIT 1").fetchone()
        cotizacion_usd_actual = cot_row["venta"] if cot_row else None

    proveedores = [(r["id"], r["nombre"]) for r in proveedores_rows]
    materias = [(r["id"], r["nombre"]) for r in materias_rows]

    if not proveedores or not materias:
        st.warning("Debe existir al menos un proveedor y una materia prima para continuar.")
        st.stop()

    # --- 3. Movimiento ---
    tipo_movimiento = st.radio("Tipo de movimiento", options=["ingreso", "egreso"])

    if tipo_movimiento == "ingreso":
        with st.expander("➕ Registrar nuevo ingreso / compra"):
            with st.form("form_ingreso"):
                proveedor = st.selectbox("Proveedor", options=proveedores, format_func=lambda x: x[1])
                materia = st.selectbox("Materia Prima", options=materias, format_func=lambda x: x[1], key="materia_compra_key")

                # Obtener último precio en moneda original
                ultimo_precio = 0.0
                ultima_moneda = "ARS"
                materia_id = None
                precio_key_sufijo = "none"

                if materia:
                    materia_id = materia[0]
                    precio_key_sufijo = str(materia_id)
                    with get_connection() as conn:
                        query_ultima_compra = """
                            SELECT precio_unitario, moneda, cotizacion_usd
                            FROM compras_materia_prima
                            WHERE materia_prima_id = ? 
                            ORDER BY fecha DESC, id DESC
                            LIMIT 1
                        """
                        result = conn.execute(query_ultima_compra, (materia_id,)).fetchone()
                        if result:
                            ultimo_precio = result["precio_unitario"]
                            ultima_moneda = result["moneda"]
                            cotizacion_usada = result["cotizacion_usd"]
                            if ultima_moneda == "USD":
                                st.info(f"Último precio registrado en **USD**: $ {ultimo_precio:,.2f} USD (Cotización usada: {cotizacion_usada:,.2f} ARS)")
                            else:
                                st.info(f"Último precio registrado en **ARS**: $ {ultimo_precio:,.2f} ARS")
                        else:
                            st.info("No hay compras previas para esta materia prima. Precio inicial en ARS.")

                precio_inicial_str = f"{ultimo_precio:.2f}" if ultimo_precio > 0.0 else ""

                fecha = st.date_input("Fecha de movimiento", value=date.today())
                cantidad_str = st.text_input("Cantidad", key='cantidad')

                precio_unitario_str = st.text_input(
                    "Precio unitario (por unidad)",
                    key=f'precio_unitario_{precio_key_sufijo}',
                    value=precio_inicial_str
                )

                flete_str = st.text_input("Costo de flete", key='flete')
                otros_costos_str = st.text_input("Otros costos", key='otros_costos')

                moneda_options = ["ARS", "USD"]
                initial_index = moneda_options.index(ultima_moneda) if ultima_moneda in moneda_options else 0

                moneda = st.selectbox(
                    "Moneda",
                    moneda_options,
                    index=initial_index,
                    key=f'moneda_compra_{precio_key_sufijo}'
                )

                lote = st.text_input("Lote (opcional)")
                numero_comprobante = st.text_input("Número de comprobante (opcional)")

                submitted = st.form_submit_button("Registrar ingreso")

                if submitted:
                    def limpiar_valor(valor):
                        return ''.join(c for c in str(valor) if c not in ['+', '-'])

                    cantidad_str = limpiar_valor(cantidad_str)
                    precio_unitario_str = limpiar_valor(st.session_state[f'precio_unitario_{precio_key_sufijo}'])
                    flete_str = limpiar_valor(flete_str)
                    otros_costos_str = limpiar_valor(otros_costos_str)

                    try:
                        cantidad = float(cantidad_str) if cantidad_str else 0.0
                        precio_unitario = float(precio_unitario_str) if precio_unitario_str else 0.0
                        flete = float(flete_str) if flete_str else 0.0
                        otros_costos = float(otros_costos_str) if otros_costos_str else 0.0
                    except ValueError:
                        st.error("Por favor, ingrese valores numéricos válidos.")
                        st.stop()

                    if materia_id is None:
                        st.error("Debe seleccionar una materia prima.")
                        st.stop()

                    moneda = st.session_state[f'moneda_compra_{precio_key_sufijo}']

                    if moneda == "USD":
                        if cotizacion_usd_actual:
                            st.info(f"Cotización dólar utilizada: $ {cotizacion_usd_actual:.2f}")
                            cotizacion_usd = cotizacion_usd_actual
                        else:
                            st.warning("No hay cotización del dólar. Se usará 1 por defecto.")
                            cotizacion_usd = 1.0
                    else:
                        cotizacion_usd = 1.0

                    precio_unitario_pesos = precio_unitario * cotizacion_usd
                    costo_total = cantidad * precio_unitario_pesos + flete + otros_costos
                    st.info(f"Costo total estimado en pesos: ${costo_total:.2f}")

                    lote_val = lote.strip() if lote.strip() else "SIN-LOTE"
                    nro_comprobante = numero_comprobante.strip()

                    with get_connection() as conn:
                        cur = conn.cursor()

                        # Insert en compras (precio en moneda original)
                        cur.execute("""
                            INSERT INTO compras_materia_prima 
                            (proveedor_id, materia_prima_id, fecha, cantidad, precio_unitario, costo_total,
                             costo_flete, otros_costos, moneda, cotizacion_usd, observaciones, numero_comprobante)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            proveedor[0], materia_id, fecha.strftime("%Y-%m-%d"), cantidad, precio_unitario,
                            costo_total, flete, otros_costos, moneda, cotizacion_usd, "", nro_comprobante
                        ))

                        # Historial de precios (precio convertido a pesos)
                        cur.execute("""
                            INSERT INTO precios_materias_primas
                            (materia_prima_id, precio_unitario, fecha, cotizacion_usd, costo_flete, otros_costos)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            materia_id, precio_unitario_pesos, fecha.strftime("%Y-%m-%d"), cotizacion_usd, flete, otros_costos
                        ))

                        # Movimiento (precio en pesos)
                        cur.execute("""
                            INSERT INTO movimientos_materia_prima
                            (materia_prima_id, fecha, cantidad, tipo_movimiento, destino, costo_flete, otros_costos, lote, precio_unitario)
                            VALUES (?, ?, ?, 'ingreso', 'otro', ?, ?, ?, ?)
                        """, (
                            materia_id, fecha.strftime("%Y-%m-%d"), cantidad, flete, otros_costos, lote_val, precio_unitario_pesos
                        ))

                        # ---- ACTUALIZAR stock_materias_primas usando 'cantidad_actual' ----
                        stock_actual_row = cur.execute("""
                            SELECT cantidad_actual FROM stock_materias_primas WHERE materia_prima_id = ?
                        """, (materia_id,)).fetchone()

                        if stock_actual_row:
                            nueva_cantidad = stock_actual_row["cantidad_actual"] + cantidad
                            cur.execute("""
                                UPDATE stock_materias_primas SET cantidad_actual = ? WHERE materia_prima_id = ?
                            """, (nueva_cantidad, materia_id))
                        else:
                            cur.execute("""
                                INSERT INTO stock_materias_primas (materia_prima_id, cantidad_actual) VALUES (?, ?)
                            """, (materia_id, cantidad))

                        conn.commit()
                        st.success(f"Ingreso registrado. Stock actualizado: +{cantidad}")

    elif tipo_movimiento == "egreso":
        with st.expander("➖ Registrar egreso de materia prima"):
            with st.form("form_egreso"):
                materia = st.selectbox("Materia Prima", options=materias, format_func=lambda x: x[1])
                fecha = st.date_input("Fecha de movimiento", value=date.today())
                cantidad_egreso_str = st.text_input("Cantidad", key='cantidad_egreso')
                destino = st.selectbox("Destino del egreso", options=["laboratorio", "otro"])
                lote = st.text_input("Lote (opcional)")

                submitted = st.form_submit_button("Registrar egreso")

                if submitted:
                    def limpiar_valor_egreso(valor):
                        return ''.join(c for c in str(valor) if c not in ['+', '-'])

                    cantidad_egreso_str = limpiar_valor_egreso(cantidad_egreso_str)

                    try:
                        cantidad = float(cantidad_egreso_str) if cantidad_egreso_str else 0.0
                    except ValueError:
                        st.error("Por favor, ingrese un valor numérico válido para la cantidad de egreso.")
                        st.stop()

                    lote_val = lote.strip() if lote.strip() else "SIN-LOTE"

                    with get_connection() as conn:
                        cur = conn.cursor()

                        stock_actual_row = cur.execute("""
                            SELECT cantidad_actual FROM stock_materias_primas WHERE materia_prima_id = ?
                        """, (materia[0],)).fetchone()

                        cantidad_stock = stock_actual_row["cantidad_actual"] if stock_actual_row else 0

                        if cantidad > cantidad_stock:
                            st.error(f"No hay stock suficiente. Disponible: {cantidad_stock}.")
                        else:
                            cur.execute("""
                                INSERT INTO movimientos_materia_prima
                                (materia_prima_id, fecha, cantidad, tipo_movimiento, destino, costo_flete, otros_costos, lote, precio_unitario)
                                VALUES (?, ?, ?, 'egreso', ?, 0, 0, ?, NULL)
                            """, (
                                materia[0], fecha.strftime("%Y-%m-%d"), -cantidad, destino, lote_val
                            ))

                            nueva_cantidad = cantidad_stock - cantidad
                            cur.execute("""
                                UPDATE stock_materias_primas SET cantidad_actual = ? WHERE materia_prima_id = ?
                            """, (nueva_cantidad, materia[0]))

                            conn.commit()
                            st.success(f"Egreso registrado. Stock actualizado: -{cantidad}")

    # --- 4. Consulta de proveedores ---
    st.subheader("📁 Consulta de Proveedores")
    with st.expander("🔍 Buscar y ver todos los proveedores"):
        filtro_nombre = st.text_input("Buscar por nombre de proveedor")

        with get_connection() as conn:
            if filtro_nombre.strip():
                query = """
                    SELECT nombre, contacto, cuit, direccion, telefono, email
                    FROM proveedores
                    WHERE nombre LIKE ?
                    ORDER BY nombre
                """
                proveedores_df = pd.read_sql_query(query, conn, params=(f"%{filtro_nombre.strip()}%",))
            else:
                proveedores_df = pd.read_sql_query("""
                    SELECT nombre, contacto, cuit, direccion, telefono, email
                    FROM proveedores
                    ORDER BY nombre
                """, conn)

        st.dataframe(proveedores_df, use_container_width=True)

    # --- 5. Historial de movimientos ---
    st.subheader("📈 Historial de Movimientos")
    with st.expander("📋 Ver historial de ingresos y egresos"):
        with get_connection() as conn:
            materias_filtro = conn.execute("""
                SELECT id, nombre || ' (' || unidad || ')' AS nombre
                FROM materias_primas ORDER BY nombre
            """).fetchall()
            materias_dict = {r["id"]: r["nombre"] for r in materias_filtro}
            materias_opciones = list(materias_dict.items())

        materia_id_sel = st.selectbox("Materia prima a consultar", materias_opciones, format_func=lambda x: x[1])
        tipo_sel = st.selectbox("Filtrar por tipo de movimiento", options=["Todos", "ingreso", "egreso"])
        limite = st.slider("Cantidad de registros a mostrar", min_value=10, max_value=100, value=50)

        with get_connection() as conn:
            base_query = """
                SELECT mmp.fecha, mp.nombre || ' (' || mp.unidad || ')' AS materia, 
                       mmp.tipo_movimiento, mmp.cantidad, mmp.destino,
                       IFNULL(mmp.precio_unitario, '-') AS precio_unitario, 
                       mmp.lote
                FROM movimientos_materia_prima mmp
                JOIN materias_primas mp ON mp.id = mmp.materia_prima_id
                WHERE mmp.materia_prima_id = ?
            """

            params = [materia_id_sel[0]]

            if tipo_sel != "Todos":
                base_query += " AND mmp.tipo_movimiento = ?"
                params.append(tipo_sel)

            base_query += " ORDER BY mmp.fecha DESC LIMIT ?"
            params.append(limite)

            df_mov = pd.read_sql_query(base_query, conn, params=params)

        st.dataframe(df_mov, use_container_width=True)

if __name__ == "__main__":
    compras_materia_prima()
