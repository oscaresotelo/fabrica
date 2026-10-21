import streamlit as st
import sqlite3
import pandas as pd

DB_PATH = "minerva.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_data(query, params=()):
    conn = get_db_connection()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

st.title("📦 Stock Actual de Envases por Cliente")

# Cargar clientes para filtro
clientes_df = fetch_data("SELECT id, nombre FROM clientes ORDER BY nombre;")
cliente_dict = {row['nombre']: row['id'] for _, row in clientes_df.iterrows()}

cliente_seleccionado = st.selectbox("Seleccionar Cliente", ["--Todos--"] + list(cliente_dict.keys()))

if cliente_seleccionado == "--Todos--":
    # Mostrar stock de todos los clientes
    query = """
    SELECT 
        c.nombre AS cliente,
        e.descripcion AS envase,
        e.unidad,
        sec.uso,
        sec.linea,
        sec.cantidad
    FROM stock_envases_clientes sec
    JOIN clientes c ON sec.cliente_id = c.id
    JOIN envases e ON sec.envase_id = e.id
    ORDER BY c.nombre, e.descripcion, sec.uso, sec.linea
    """
    df_stock = fetch_data(query)
else:
    cliente_id = cliente_dict[cliente_seleccionado]
    query = """
    SELECT 
        c.nombre AS cliente,
        e.descripcion AS envase,
        e.unidad,
        sec.uso,
        sec.linea,
        sec.cantidad
    FROM stock_envases_clientes sec
    JOIN clientes c ON sec.cliente_id = c.id
    JOIN envases e ON sec.envase_id = e.id
    WHERE sec.cliente_id = ?
    ORDER BY e.descripcion, sec.uso, sec.linea
    """
    df_stock = fetch_data(query, (cliente_id,))

if df_stock.empty:
    st.info("No se encontraron registros de stock para el filtro seleccionado.")
else:
    # Mostrar tabla con formato y orden
    df_stock_display = df_stock.rename(columns={
        "cliente": "Cliente",
        "envase": "Envase",
        "unidad": "Unidad",
        "uso": "Uso",
        "linea": "Línea",
        "cantidad": "Cantidad"
    })
    st.dataframe(df_stock_display.style.format({"Cantidad": "{:.2f}"}), use_container_width=True)
