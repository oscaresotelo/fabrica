import streamlit as st
import sqlite3
import pandas as pd

# Configuración de la conexión
DB_NAME = "minerva.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

st.title("Gestión de Stock de Materias Primas")

# 1. Buscador de Materia Prima
st.header("Buscar Materia Prima")
search_term = st.text_input("Ingrese el nombre de la materia prima:")

if search_term:
    conn = get_connection()
    # Consulta para unir las tablas y traer el nombre y el stock
    query = """
        SELECT mp.id, mp.nombre, mp.unidad, s.cantidad_actual
        FROM materias_primas mp
        LEFT JOIN stock_materias_primas s ON mp.id = s.materia_prima_id
        WHERE mp.nombre LIKE ?
    """
    df = pd.read_sql(query, conn, params=(f'%{search_term}%',))
    conn.close()

    if not df.empty:
        st.write("Resultados encontrados:")
        st.dataframe(df)

        # Seleccionar ID para actualizar
        selected_id = st.selectbox("Seleccione el ID de la materia prima a actualizar:", df['id'])
        
        # Obtener datos de la fila seleccionada
        row = df[df['id'] == selected_id].iloc[0]
        st.info(f"Actualizando: {row['nombre']} ({row['unidad']})")
        
        # 2. Formulario de Actualización
        with st.form("update_stock"):
            new_stock = st.number_input("Nueva cantidad actual:", value=float(row['cantidad_actual'] or 0.0))
            submit = st.form_submit_button("Actualizar Stock")
            
            if submit:
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    
                    # Verificar si ya existe el registro en la tabla de stock
                    cursor.execute("SELECT 1 FROM stock_materias_primas WHERE materia_prima_id = ?", (int(selected_id),))
                    exists = cursor.fetchone()
                    
                    if exists:
                        # Actualizar registro existente
                        cursor.execute("""
                            UPDATE stock_materias_primas 
                            SET cantidad_actual = ? 
                            WHERE materia_prima_id = ?
                        """, (new_stock, int(selected_id)))
                    else:
                        # Insertar nuevo registro si no existe (con cantidad inicial 0 en el otro campo requerido)
                        cursor.execute("""
                            INSERT INTO stock_materias_primas (materia_prima_id, cantidad_actual, cantidad)
                            VALUES (?, ?, 0)
                        """, (int(selected_id), new_stock))
                    
                    conn.commit()
                    conn.close()
                    st.success(f"Stock actualizado correctamente para ID {selected_id}")
                    st.rerun() # Recargar para ver los cambios
                except Exception as e:
                    st.error(f"Error al actualizar: {e}")
    else:
        st.warning("No se encontraron materias primas con ese nombre.")