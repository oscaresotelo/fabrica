import streamlit as st
import sqlite3
import pandas as pd
from datetime import date

# --- Conexión a la base de datos ---
def get_db_connection():
    try:
        conn = sqlite3.connect('minerva.db')
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        st.error(f"Error al conectar con la base de datos: {e}")
        return None

# --- Funciones auxiliares ---
def fetch_data(query, params=()):
    conn = get_db_connection()
    if conn:
        try:
            df = pd.read_sql_query(query, conn, params=params)
            return df
        except Exception as e:
            st.error(f"Error en la consulta: {e}")
        finally:
            conn.close()
    return pd.DataFrame()

def execute_query(query, params=()):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return True
        except Exception as e:
            st.error(f"Error al ejecutar la consulta: {e}")
        finally:
            conn.close()
    return False

# --- Registrar salida (despacho) con trazabilidad ---
def registrar_salida_producto(stock_id, cantidad, fecha, destino, observacion):
    conn = get_db_connection()
    if not conn:
        st.error("Error al conectar con la base de datos para registrar salida producto envasado.")
        return False
    cursor = conn.cursor()
    try:
        # Validar cantidad suficiente
        cursor.execute("SELECT cantidad FROM stock_productos_envasados WHERE id = ?", (stock_id,))
        fila = cursor.fetchone()
        if not fila:
            st.error("No se encontró el stock seleccionado.")
            return False
        cantidad_actual = fila['cantidad']
        if cantidad > cantidad_actual:
            st.error(f"No hay suficiente stock. Disponible: {cantidad_actual}, solicitado: {cantidad}")
            return False

        nueva_cantidad = cantidad_actual - cantidad
        # Actualizar stock
        cursor.execute("""
            UPDATE stock_productos_envasados SET cantidad = ? WHERE id = ?
        """, (nueva_cantidad, stock_id))

        # Registrar movimiento salida
        cursor.execute("""
            INSERT INTO movimientos_productos_envasados (stock_id, fecha, cantidad, tipo_movimiento, destino, observacion)
            VALUES (?, ?, ?, 'Egreso', ?, ?)
        """, (stock_id, fecha, -cantidad, destino, observacion))

        # Registrar en tabla salidas_productos_envasados para seguimiento despacho
        cursor.execute("""
            INSERT INTO salidas_productos_envasados (orden_envasado_id, fecha_salida, cantidad_despachada, destino)
            VALUES (
                (SELECT oe.id FROM ordenes_envasado oe
                 JOIN stock_productos_envasados spe ON oe.envase_id = spe.envase_id
                 WHERE spe.id = ? LIMIT 1),
                ?, ?, ?
            )
        """, (stock_id, fecha, cantidad, destino))

        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error al registrar salida producto envasado: {e}")
        return False
    finally:
        conn.close()

# --- Interfaz ---
st.set_page_config(layout="wide")
st.title("🚚 Registrar Salida / Despacho de Productos Envasados")

# Mostrar stock disponible para seleccionar
stock_query = """
SELECT
    spe.id AS stock_id,
    c.nombre AS cliente,
    r.nombre AS producto,
    e.descripcion AS envase,
    spe.lote,
    spe.cantidad,
    spe.fecha_ingreso
FROM stock_productos_envasados spe
JOIN clientes c ON spe.cliente_id = c.id
JOIN recetas r ON spe.receta_id = r.id
JOIN envases e ON spe.envase_id = e.id
WHERE spe.cantidad > 0
ORDER BY spe.fecha_ingreso ASC;
"""

df_stock = fetch_data(stock_query)

if df_stock.empty:
    st.info("No hay productos envasados en stock para despachar.")
else:
    st.dataframe(df_stock[['cliente','producto','envase','lote','cantidad','fecha_ingreso']], use_container_width=True)

    stock_options = {
        f"{row['cliente']} - {row['producto']} - {row['envase']} - Lote {row['lote']} - Cantidad: {row['cantidad']}"
        : row['stock_id'] for idx, row in df_stock.iterrows()
    }

    seleccionado = st.selectbox("Seleccione el producto envasado a despachar:", list(stock_options.keys()))
    stock_id_seleccionado = stock_options.get(seleccionado)

    if stock_id_seleccionado:
        cantidad_max = df_stock[df_stock['id'] == stock_id_seleccionado]['cantidad'].values[0]
        cantidad_despachar = st.number_input(
            "Cantidad a despachar",
            min_value=1,
            max_value=int(cantidad_max),
            value=1,
            step=1
        )
        destino = st.text_input("Destino del despacho", value="Cliente")
        observacion = st.text_area("Observaciones (opcional)")

        if st.button("Registrar salida / despacho"):
            fecha_hoy = str(date.today())
            ok = registrar_salida_producto(stock_id_seleccionado, cantidad_despachar, fecha_hoy, destino, observacion)
            if ok:
                st.success(f"Salida registrada. Se despacharon {cantidad_despachar} unidades.")
                st.experimental_rerun()
            else:
                st.error("No se pudo registrar la salida.")

# --- Opcional: mostrar últimas salidas registradas ---
st.markdown("---")
st.subheader("📋 Últimos despachos registrados")

ultimos_despachos_query = """
SELECT
    sp.id,
    c.nombre AS cliente,
    r.nombre AS producto,
    e.descripcion AS envase,
    sp.cantidad_despachada,
    sp.fecha_salida,
    sp.destino
FROM salidas_productos_envasados sp
JOIN ordenes_envasado oe ON sp.orden_envasado_id = oe.id
JOIN producciones p ON oe.produccion_id = p.id
JOIN pedidos_produccion pp ON p.pedido_id = pp.id
JOIN clientes c ON pp.cliente_id = c.id
JOIN recetas r ON pp.receta_id = r.id
JOIN envases e ON oe.envase_id = e.id
ORDER BY sp.fecha_salida DESC, sp.id DESC
LIMIT 10;
"""

df_despachos = fetch_data(ultimos_despachos_query)

if df_despachos.empty:
    st.info("No hay despachos registrados.")
else:
    st.dataframe(df_despachos, use_container_width=True)
