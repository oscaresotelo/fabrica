import streamlit as st
import sqlite3
import pandas as pd

def get_connection():
    return sqlite3.connect('minerva.db')

def fetch_data(query, params=None):
    conn = get_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()
    return df

st.set_page_config(page_title="Minerva Productos Capilares", page_icon="💧", layout="wide")

# --- Estilos CSS personalizados ---
st.markdown("""
<style>
body {
    background-color: #f7f9fc;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
.metric-card {
    background: white;
    border-radius: 10px;
    padding: 25px 20px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    text-align: center;
    margin-bottom: 10px;
    transition: box-shadow 0.3s ease;
}
.metric-card:hover {
    box-shadow: 0 8px 20px rgba(0,0,0,0.15);
}
.metric-value {
    font-size: 48px;
    font-weight: 700;
    color: #0072C6;
    margin-bottom: 5px;
}
.metric-label {
    font-size: 18px;
    font-weight: 600;
    color: #555;
}
.stButton>button {
    background-color: #0072C6;
    color: white;
    font-weight: 600;
    border-radius: 8px;
    padding: 10px 18px;
    width: 100%;
    transition: background-color 0.3s ease;
    margin-top: 10px;
}
.stButton>button:hover {
    background-color: #005a9e;
}
.dataframe-container {
    background: white;
    padding: 15px;
    border-radius: 10px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    max-height: 500px;
    overflow-y: auto;
    margin-bottom: 40px;
}
h1, h2 {
    color: #0072C6;
    margin-top: 30px;
    margin-bottom: 20px;
    text-align: center;
}
.fecha-cotizacion {
    font-size: 14px;
    color: #999;
    font-style: italic;
    margin-top: -10px;
    text-align: right;
}
</style>
""", unsafe_allow_html=True)

# Título principal
st.markdown("<h1>Minerva Productos Capilares</h1>", unsafe_allow_html=True)
st.markdown("<h2>🏭 Dashboard de Producción y Stock</h2>", unsafe_allow_html=True)

# --- Consultas principales ---
try:
    pedidos = fetch_data("""
        SELECT COUNT(*) AS total
        FROM producciones p
        JOIN pedidos_produccion pp ON p.pedido_id = pp.id
        WHERE p.estado IN ('pendiente', 'proceso', 'en_proceso');
    """).iloc[0]['total']
except Exception as e:
    pedidos = None
    st.error(f"Error al obtener pedidos activos: {e}")

try:
    stock_bajo = fetch_data("""
        SELECT COUNT(*) AS total
        FROM stock_materias_primas s
        WHERE s.cantidad < 500;
    """).iloc[0]['total']
except Exception as e:
    stock_bajo = None
    st.error(f"Error al obtener stock bajo: {e}")

try:
    lotes_sin_envasar = fetch_data("""
        SELECT COUNT(*) AS total
        FROM producciones p
        WHERE p.estado = 'producido'
        AND p.id NOT IN (
            SELECT oe.produccion_id FROM ordenes_envasado oe
        );
    """).iloc[0]['total']
except Exception as e:
    lotes_sin_envasar = None
    st.error(f"Error al obtener lotes sin envasar: {e}")

try:
    cotizacion = fetch_data("""
        SELECT compra, venta, fecha_hora FROM cotizacion_dolar
        ORDER BY fecha_hora DESC LIMIT 1;
    """)
    if not cotizacion.empty:
        compra = cotizacion.iloc[0]['compra']
        venta = cotizacion.iloc[0]['venta']
        fecha_cot = cotizacion.iloc[0]['fecha_hora']
    else:
        compra = venta = fecha_cot = None
    except Exception as e:
        compra = venta = fecha_cot = None
    st.error(f"Error al obtener cotización dólar: {e}")

# --- Layout principal de métricas ---
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-value">{pedidos if pedidos is not None else 'Error'}</div>
        <div class="metric-label">Pedidos Activos</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🔍 Ver Detalle Pedidos", key="btn_pedidos"):
        try:
            df_pedidos = fetch_data("""
                SELECT p.id, pp.fecha, c.nombre AS cliente, p.estado, pp.cantidad, pp.numero_pedido
                FROM producciones p
                JOIN pedidos_produccion pp ON p.pedido_id = pp.id
                LEFT JOIN clientes c ON pp.cliente_id = c.id
                WHERE p.estado IN ('pendiente', 'proceso', 'en_proceso')
                ORDER BY pp.fecha DESC LIMIT 50;
            """)
            st.markdown("<h2>Pedidos Activos</h2>", unsafe_allow_html=True)
            st.markdown('<div class="dataframe-container">', unsafe_allow_html=True)
            st.dataframe(df_pedidos, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error al obtener detalle de pedidos: {e}")

with col2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-value">{stock_bajo if stock_bajo is not None else 'Error'}</div>
        <div class="metric-label">Stock Bajo MP</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🔍 Ver Stock Bajo", key="btn_stock"):
        try:
            df_stock_bajo = fetch_data("""
                SELECT m.nombre, s.cantidad, m.unidad
                FROM stock_materias_primas s
                JOIN materias_primas m ON s.materia_prima_id = m.id
                WHERE s.cantidad < 500
                ORDER BY s.cantidad ASC LIMIT 50;
            """)
            st.markdown("<h2>Stock Bajo</h2>", unsafe_allow_html=True)
            st.markdown('<div class="dataframe-container">', unsafe_allow_html=True)
            st.dataframe(df_stock_bajo, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error al obtener stock bajo: {e}")

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-value">{lotes_sin_envasar if lotes_sin_envasar is not None else 'Error'}</div>
        <div class="metric-label">Lotes Sin Envasar</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🔍 Ver Lotes", key="btn_lotes"):
        try:
            df_lotes = fetch_data("""
                SELECT p.lote, p.fecha, pp.numero_pedido, c.nombre AS cliente, p.estado
                FROM producciones p
                JOIN pedidos_produccion pp ON p.pedido_id = pp.id
                LEFT JOIN clientes c ON pp.cliente_id = c.id
                WHERE p.estado = 'producido'
                  AND p.id NOT IN (
                      SELECT oe.produccion_id FROM ordenes_envasado oe
                  )
                ORDER BY p.fecha DESC
                LIMIT 50;
            """)
            st.markdown("<h2>Lotes Sin Envasar</h2>", unsafe_allow_html=True)
            st.markdown('<div class="dataframe-container">', unsafe_allow_html=True)
            st.dataframe(df_lotes, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error al obtener lotes sin envasar: {e}")

with col4:
    if compra is not None and venta is not None:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">${compra:.2f} / ${venta:.2f}</div>
            <div class="metric-label">Dólar Compra / Venta</div>
            <div class="fecha-cotizacion">{fecha_cot}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">N/D</div>
            <div class="metric-label">Cotización Dólar</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

# --- Últimas compras ---
st.markdown("<h2>🧾 Últimas Compras de Materias Primas</h2>", unsafe_allow_html=True)

try:
    compras_df = fetch_data("""
        SELECT c.fecha, p.nombre AS proveedor, m.nombre AS materia_prima,
               c.numero_comprobante, c.cantidad, c.precio_unitario
        FROM compras_materia_prima c
        JOIN proveedores p ON c.proveedor_id = p.id
        JOIN materias_primas m ON c.materia_prima_id = m.id
        ORDER BY c.fecha DESC LIMIT 10;
    """)
    if not compras_df.empty:
        st.markdown('<div class="dataframe-container">', unsafe_allow_html=True)
        st.dataframe(compras_df, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("No hay datos de compras disponibles.")
except Exception as e:
    st.error(f"Error al obtener últimas compras: {e}")