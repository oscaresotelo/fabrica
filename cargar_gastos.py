import streamlit as st
import sqlite3
import pandas as pd
from datetime import date

DB_NAME = "minerva.db"

def obtener_categorias():
    with sqlite3.connect(DB_NAME) as conn:
        try:
            return pd.read_sql_query("SELECT id, nombre FROM categorias_imputacion", conn)
        except:
            return pd.DataFrame({'id': [1], 'nombre': ['General']})

def guardar_gasto(datos):
    # Query ajustado a la estructura real de tu DB
    query = """
        INSERT INTO gastos (
            fecha_pago, 
            fecha_factura,
            beneficiario_nombre, 
            categoria_id, 
            numero_comprobante, 
            importe_total, 
            moneda, 
            observaciones
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(query, datos)
        conn.commit()

st.title("💸 Registro de Gastos Minerva")

df_cat = obtener_categorias()
categorias_dict = dict(zip(df_cat['nombre'], df_cat['id']))

with st.form("form_gastos_final", clear_on_submit=True):
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Fechas y Beneficiario")
        f_pago = st.date_input("Fecha de Pago (Efectivo)", value=date.today())
        f_factura = st.date_input("Fecha de la Factura (Comprobante)", value=date.today())
        beneficiario = st.text_input("Beneficiario (Obligatorio)*")
        categoria = st.selectbox("Categoría*", options=list(categorias_dict.keys()))

    with col2:
        st.subheader("Detalles Económicos")
        nro_comprobante = st.text_input("N° Comprobante (Único)")
        importe = st.number_input("Importe Total*", min_value=0.0, step=0.01)
        moneda = st.selectbox("Moneda", options=["ARS", "USD"])
        observaciones = st.text_area("Observaciones")

    if st.form_submit_button("Registrar Gasto"):
        if beneficiario and importe > 0:
            try:
                valores = (
                    f_pago.strftime("%Y-%m-%d"),
                    f_factura.strftime("%Y-%m-%d"), # Ahora enviamos el campo faltante
                    beneficiario,
                    categorias_dict[categoria],
                    nro_comprobante if nro_comprobante else None,
                    importe,
                    moneda,
                    observaciones
                )
                guardar_gasto(valores)
                st.success("✅ Gasto guardado correctamente.")
            except sqlite3.IntegrityError as e:
                if "UNIQUE" in str(e):
                    st.error("Error: El número de comprobante ya existe.")
                else:
                    st.error(f"Error de integridad: {e}")
            except Exception as e:
                st.error(f"Error inesperado: {e}")
        else:
            st.warning("Completa el beneficiario y el importe.")

# Vista previa de historial
st.divider()
try:
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql_query("SELECT * FROM gastos ORDER BY id DESC LIMIT 5", conn)
        st.write("Últimos 5 registros:", df)
except:
    pass