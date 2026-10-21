import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, datetime
import uuid
import time

def comprar_envases():
    DB_PATH = "minerva.db"

    def get_db_connection():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def fetch_data(query, params=(), max_retries=5):
        for attempt in range(max_retries):
            try:
                conn = get_db_connection()
                df = pd.read_sql_query(query, conn, params=params)
                conn.close()
                return df
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    st.error(f"Error de base de datos: {e}")
                    raise
        return pd.DataFrame()

    def generar_lote(envase_id):
        ahora = datetime.now().strftime("%Y%m%d%H%M%S")
        codigo_unico = uuid.uuid4().hex[:6].upper()
        return f"LE{envase_id}_{ahora}_{codigo_unico}"

    def asegurar_stock_envases_cliente(conn, cliente_id, envase_id):
        cursor = conn.cursor()
        cursor.execute("""
            SELECT cantidad FROM stock_envases_clientes
            WHERE cliente_id = ? AND envase_id = ? 
            AND (uso IS NULL OR uso = 'N/A') AND (linea IS NULL OR linea = 'N/A') 
        """, (cliente_id, envase_id))
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO stock_envases_clientes (cliente_id, envase_id, uso, linea, cantidad)
                VALUES (?, ?, 'N/A', 'N/A', 0)
            """, (cliente_id, envase_id))

    st.title("📦 Compra de Envases con Prorrateo de Flete")

    # --- Selección de Entidades ---
    clientes = fetch_data("SELECT id, nombre FROM clientes ORDER BY nombre;")
    cliente_dict = {row['nombre']: row['id'] for _, row in clientes.iterrows()}
    cliente_nombre = st.selectbox("Seleccionar Cliente", ["--Seleccione--"] + list(cliente_dict.keys()), key="cliente_select")
    
    if cliente_nombre == "--Seleccione--":
        st.stop()
    
    cliente_id = cliente_dict[cliente_nombre]

    proveedores = fetch_data("SELECT id, nombre FROM proveedores ORDER BY nombre;")
    proveedor_dict = {row['nombre']: row['id'] for _, row in proveedores.iterrows()}
    proveedor_nombre = st.selectbox("Seleccionar Proveedor", ["--Seleccione--"] + list(proveedor_dict.keys()), key="proveedor_select")

    if proveedor_nombre == "--Seleccione--":
        st.stop()
    
    proveedor_id = proveedor_dict[proveedor_nombre]

    # --- DATOS DEL COMPROBANTE Y FLETE ---
    st.subheader("Datos del Comprobante (Vínculo de Flete)")
    col_fact, col_flete = st.columns(2)
    with col_fact:
        nro_comprobante = st.text_input("Número de Comprobante / Factura", placeholder="Ej: 0001-0000456")
    with col_flete:
        # Se guarda el flete total en cada entrada para poder consultarlo después por comprobante
        flete_total_factura = st.number_input("Costo Total del Flete ($)", min_value=0.0, format="%.2f", help="Monto total pagado por el transporte de este comprobante")

    # --- CARGA DEL ENVASE ---
    st.divider()
    envases = fetch_data("SELECT id, descripcion, unidad FROM envases WHERE cliente_id = ? ORDER BY descripcion;", (cliente_id,))
    if envases.empty:
        st.warning("No hay envases registrados para este cliente.")
        st.stop()

    envase_dict = {f"{row['descripcion']} ({row['unidad']})": row['id'] for _, row in envases.iterrows()}
    envase_nombre = st.selectbox("Tipo de Envase a ingresar", ["--Seleccione--"] + list(envase_dict.keys()))

    if envase_nombre != "--Seleccione--":
        envase_id = envase_dict[envase_nombre]
        
        # Obtener último precio registrado
        ultimo_precio = 0.0
        with get_db_connection() as conn:
            res = conn.execute("SELECT precio_unitario FROM entradas_envases WHERE envase_id = ? ORDER BY id DESC LIMIT 1", (envase_id,)).fetchone()
            if res: ultimo_precio = res["precio_unitario"]

        c1, c2, c3 = st.columns(3)
        with c1:
            fecha_compra = st.date_input("Fecha de Compra", date.today())
        with c2:
            cantidad = st.number_input("Cantidad de Envases", min_value=1, step=1)
        with c3:
            precio_unitario = st.number_input("Precio Unitario ($)", min_value=0.01, value=max(0.01, ultimo_precio), format="%.2f")

        if st.button("Registrar Ingreso de Envase"):
            if not nro_comprobante.strip():
                st.error("Es obligatorio el número de comprobante para relacionar el flete.")
                st.stop()

            lote = generar_lote(envase_id)
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("BEGIN;")

                # 1. Insertar en entradas_envases incluyendo el nuevo campo costo_flete
                cursor.execute("""
                    INSERT INTO entradas_envases
                    (proveedor_id, fecha_ingreso, numero_comprobante, envase_id, cantidad_ingresada, 
                     precio_unitario, costo_flete, cliente_asignado_id, producto_asignado_id, lote)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (proveedor_id, fecha_compra.isoformat(), nro_comprobante, envase_id, 
                      cantidad, precio_unitario, flete_total_factura, cliente_id, None, lote))

                # 2. Actualizar stock_envases_clientes
                asegurar_stock_envases_cliente(conn, cliente_id, envase_id)
                cursor.execute("""
                    UPDATE stock_envases_clientes SET cantidad = cantidad + ?
                    WHERE cliente_id = ? AND envase_id = ? AND (uso IS NULL OR uso = 'N/A');
                """, (cantidad, cliente_id, envase_id))

                # 3. Stock por Lotes
                cursor.execute("""
                    INSERT INTO stock_envases_clientes_lotes (cliente_id, envase_id, lote, cantidad, fecha_ingreso, uso, linea)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                """, (cliente_id, envase_id, lote, cantidad, fecha_compra.isoformat(), "N/A", "N/A"))

                # 4. Movimiento
                obs = f"Ingreso Fact {nro_comprobante} | Flete asignado: ${flete_total_factura}"
                cursor.execute("""
                    INSERT INTO movimientos_envases (envase_id, fecha, cantidad, tipo_movimiento, observacion, lote)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (envase_id, datetime.now().isoformat(), cantidad, "Ingreso", obs, lote))

                conn.commit()
                st.success(f"✅ Registrado exitosamente. Lote: {lote}")
            except Exception as e:
                conn.rollback()
                st.error(f"Error al registrar: {e}")
            finally:
                conn.close()

    # --- ANÁLISIS DE COSTO TOTAL (PRORRATEO) ---
    if nro_comprobante:
        st.subheader(f"Análisis de Prorrateo: Comprobante {nro_comprobante}")
        df_items = fetch_data("""
            SELECT e.lote, env.descripcion, e.cantidad_ingresada as cant, e.precio_unitario as precio, e.costo_flete
            FROM entradas_envases e
            JOIN envases env ON e.envase_id = env.id
            WHERE e.numero_comprobante = ?
        """, (nro_comprobante,))

        if not df_items.empty:
            # Calculamos cuántas unidades totales vinieron en este flete
            total_unidades = df_items['cant'].sum()
            flete_total = df_items['costo_flete'].iloc[0] # Tomamos el valor de la factura
            
            flete_por_unidad = flete_total / total_unidades if total_unidades > 0 else 0
            
            df_items['Costo Productos ($)'] = df_items['cant'] * df_items['precio']
            df_items['Flete Asignado ($)'] = df_items['cant'] * flete_por_unidad
            df_items['Costo Real Total ($)'] = df_items['Costo Productos ($)'] + df_items['Flete Asignado ($)']
            
            st.table(df_items[['lote', 'descripcion', 'cant', 'Costo Productos ($)', 'Flete Asignado ($)', 'Costo Real Total ($)']])
            st.info(f"🚚 **Resumen de Flete:** ${flete_total:,.2f} distribuidos en {total_unidades} unidades (${flete_por_unidad:.2f} por envase).")

if __name__ == "__main__":
    comprar_envases()