import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import io
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import base64
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from io import BytesIO

# =================================================================================================
# LÓGICA DE BASE DE DATOS Y CONEXIÓN
# =================================================================================================
DB_PATH = "minerva.db"

def get_connection():
    """Establece la conexión a la base de datos SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_df(query, params=()):
    """Ejecuta una consulta SQL y devuelve un DataFrame de pandas."""
    conn = get_connection()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

# =================================================================================================
# FUNCIONES ESPECÍFICAS PARA EL ABM DE REVENDEDORES
# =================================================================================================

def add_revendedor(nombre, nombre_empresa, contacto, descuento):
    """Agrega un nuevo revendedor a la base de datos."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO revendedores (nombre, nombre_empresa, contacto, descuento) VALUES (?, ?, ?, ?)", (nombre, nombre_empresa, contacto, descuento))
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Error al agregar revendedor: {e}")
        return False
    finally:
        conn.close()

def update_revendedor(revendedor_id, nombre, nombre_empresa, contacto, descuento):
    """Actualiza la información de un revendedor existente."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE revendedores SET nombre = ?, nombre_empresa = ?, contacto = ?, descuento = ? WHERE id = ?", (nombre, nombre_empresa, contacto, descuento, revendedor_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Error al actualizar revendedor: {e}")
        return False
    finally:
        conn.close()

def delete_revendedor(revendedor_id):
    """Elimina un revendedor de la base de datos."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM revendedores WHERE id = ?", (revendedor_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Error al eliminar revendedor: {e}")
        return False
    finally:
        conn.close()

# =================================================================================================
# INTERFAZ DE USUARIO PARA EL ABM DE REVENDEDORES
# =================================================================================================

def abm_revendedores():
    st.header("👤 ABM de Revendedores")
    st.markdown("---")

    # Formulario para Alta y Modificación
    with st.form("form_revendedor", clear_on_submit=True):
        st.subheader("📝 Alta / Modificación de Revendedor")
        
        # Se incluye la columna 'descuento' en la consulta
        revendedores_df = fetch_df("SELECT id, nombre, nombre_empresa, contacto, descuento FROM revendedores")
        
        # Selección para modificar
        opciones_revendedores = {"Nuevo": None}
        for index, row in revendedores_df.iterrows():
            opciones_revendedores[f"{row['nombre']} - ({row['id']})"] = row['id']
            
        revendedor_seleccionado = st.selectbox("Seleccione un revendedor para modificar o 'Nuevo' para agregar:", list(opciones_revendedores.keys()))
        revendedor_id = opciones_revendedores[revendedor_seleccionado]
        
        # Rellenar campos si se seleccionó un revendedor para modificar
        nombre_default = ""
        nombre_empresa_default = ""
        contacto_default = ""
        descuento_default = 0.0 # Valor por defecto para el descuento
        if revendedor_id:
            revendedor_info = revendedores_df[revendedores_df['id'] == revendedor_id].iloc[0]
            nombre_default = revendedor_info['nombre']
            nombre_empresa_default = revendedor_info['nombre_empresa']
            contacto_default = revendedor_info['contacto']
            descuento_default = revendedor_info['descuento']
        
        nombre = st.text_input("Nombre del revendedor:", value=nombre_default, key="revendedor_nombre")
        nombre_empresa = st.text_input("Nombre de la empresa:", value=nombre_empresa_default, key="revendedor_empresa")
        contacto = st.text_input("Contacto (teléfono, correo, etc.):", value=contacto_default, key="revendedor_contacto")
        # Nuevo campo para el descuento, con un valor por defecto para la edición
        descuento = st.number_input("Descuento (%)", min_value=0.0, max_value=100.0, value=descuento_default, step=0.01, key="revendedor_descuento")
        
        submit_button = st.form_submit_button(label="Guardar Revendedor")
        
        if submit_button:
            if not nombre:
                st.error("El nombre del revendedor no puede estar vacío.")
            else:
                if revendedor_id:
                    if update_revendedor(revendedor_id, nombre, nombre_empresa, contacto, descuento):
                        st.success(f"✅ Revendedor '{nombre}' actualizado con éxito.")
                else:
                    if add_revendedor(nombre, nombre_empresa, contacto, descuento):
                        st.success(f"✅ Revendedor '{nombre}' agregado con éxito.")
                st.rerun()

    st.markdown("---")

    # Tabla para ver y eliminar revendedores
    st.subheader("📋 Revendedores Registrados")
    # Se incluye la columna 'descuento' en la consulta para la tabla
    revendedores_df_final = fetch_df("SELECT id, nombre, nombre_empresa, contacto, descuento FROM revendedores")
    
    if not revendedores_df_final.empty:
        st.dataframe(revendedores_df_final, use_container_width=True)
        
        st.subheader("🗑️ Eliminar Revendedor")
        revendedor_a_eliminar = st.selectbox("Seleccione el revendedor que desea eliminar:", [""] + list(revendedores_df_final['nombre']))
        
        if st.button("Eliminar", key="btn_eliminar_revendedor"):
            if revendedor_a_eliminar:
                revendedor_id_eliminar = revendedores_df_final[revendedores_df_final['nombre'] == revendedor_a_eliminar].iloc[0]['id']
                if delete_revendedor(revendedor_id_eliminar):
                    st.success(f"🗑️ Revendedor '{revendedor_a_eliminar}' eliminado con éxito.")
                st.rerun()
            else:
                st.warning("Por favor, seleccione un revendedor para eliminar.")
    else:
        st.info("No hay revendedores registrados todavía.")

def main():
    st.set_page_config(layout="wide")
    abm_revendedores()

if __name__ == "__main__":
    main()