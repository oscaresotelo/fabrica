import streamlit as st
import sqlite3
import pandas as pd

# Nombre de la base de datos
DB_FILE = "minerva.db"  # Asumo que el archivo se llama minerva.db, si es minerva.db.sql cámbialo aquí

# Título de la aplicación Streamlit
st.set_page_config(page_title="Gestión de Materias Primas", layout="wide")
st.title("Gestión de precios y stock de materias primas")
st.markdown("---")

def get_db_connection():
    """Establece una conexión a la base de datos SQLite."""
    conn = sqlite3.connect(DB_FILE)
    return conn

def fetch_table_data(table_name):
    """
    Obtiene los datos de una tabla, uniendo con 'materias_primas'
    para mostrar el nombre de la materia prima.
    """
    conn = get_db_connection()
    if table_name == "precios_materias_primas":
        # Se elimina la referencia a la columna 'cantidad' de esta consulta
        query = """
        SELECT
            t1.id,
            t2.nombre AS materia_prima,
            t1.precio_unitario,
            t1.fecha,
            t1.costo_flete,
            t1.otros_costos,
            t1.cotizacion_usd
        FROM precios_materias_primas t1
        JOIN materias_primas t2 ON t1.materia_prima_id = t2.id
        """
    elif table_name == "stock_materias_primas":
        query = """
        SELECT
            t1.materia_prima_id AS id,
            t2.nombre AS materia_prima,
            t1.cantidad,
            t1.cantidad_actual
        FROM stock_materias_primas t1
        JOIN materias_primas t2 ON t1.materia_prima_id = t2.id
        """
    else:
        st.error("Tabla no soportada para la visualización.")
        return pd.DataFrame()

    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def update_table(table_name, df_updated):
    """Actualiza los registros de la tabla con los datos del DataFrame."""
    conn = get_db_connection()
    c = conn.cursor()

    # Obtener los nombres de las columnas para actualizar
    if table_name == "precios_materias_primas":
        # Se elimina la columna 'cantidad' de la lista de columnas a actualizar
        update_cols = ["precio_unitario", "fecha", "costo_flete", "otros_costos", "cotizacion_usd"]
        id_col = "id"
    elif table_name == "stock_materias_primas":
        update_cols = ["cantidad", "cantidad_actual"]
        id_col = "id"
    else:
        st.error(f"Actualización no implementada para la tabla {table_name}")
        return

    # Iterar sobre las filas actualizadas y ejecutar la sentencia UPDATE
    for index, row in df_updated.iterrows():
        try:
            set_clause = ", ".join([f"{col} = ?" for col in update_cols])
            update_query = f"UPDATE {table_name} SET {set_clause} WHERE {id_col} = ?"

            # Obtener los valores en el orden correcto
            values = [row[col] for col in update_cols] + [row[id_col]]

            c.execute(update_query, tuple(values))
        except Exception as e:
            st.error(f"Error al actualizar el registro con ID {row[id_col]}: {e}")
            conn.rollback()
            return

    conn.commit()
    conn.close()
    st.success(f"Tabla '{table_name}' actualizada correctamente.")

def delete_row(table_name, record_id):
    """Elimina un registro de la tabla por su ID."""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if table_name == "precios_materias_primas":
            c.execute("DELETE FROM precios_materias_primas WHERE id = ?", (record_id,))
        elif table_name == "stock_materias_primas":
            # Para stock_materias_primas, el id es materia_prima_id
            c.execute("DELETE FROM stock_materias_primas WHERE materia_prima_id = ?", (record_id,))
        else:
            st.error(f"Eliminación no implementada para la tabla {table_name}")
            return

        conn.commit()
        st.success(f"Registro con ID {record_id} de '{table_name}' eliminado.")
    except Exception as e:
        st.error(f"Error al eliminar el registro con ID {record_id}: {e}")
        conn.rollback()
    finally:
        conn.close()

# ---- Interfaz de usuario de Streamlit ----

# Seleccionar la tabla a gestionar
option = st.selectbox(
    "Selecciona la tabla que deseas gestionar:",
    ("precios_materias_primas", "stock_materias_primas")
)
st.markdown("---")

# Cargar y mostrar los datos de la tabla seleccionada
if option:
    st.subheader(f"Datos de la tabla: `{option}`")
    df = fetch_table_data(option)

    if not df.empty:
        # Editor de datos para modificar
        st.info("Puedes modificar los valores directamente en la tabla.")
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

        col1, col2 = st.columns([1, 1])

        with col1:
            if st.button("Guardar Cambios", use_container_width=True):
                # Obtener los IDs de las filas que no están en el DataFrame original
                original_ids = set(df['id'])
                edited_ids = set(edited_df['id'])
                new_rows_ids = list(edited_ids - original_ids)

                if new_rows_ids:
                    st.warning("La adición de nuevas filas no está soportada. Por favor, solo edita o elimina filas existentes.")
                else:
                    # Las eliminaciones se manejan por separado

                    # Identificar filas modificadas
                    df_diff = edited_df.loc[edited_df.index.difference(df.index)]
                    if not df_diff.empty:
                        update_table(option, edited_df)
                    else:
                        st.info("No se detectaron cambios para guardar.")

        with col2:
            # Eliminar registros
            st.warning("Advertencia: Esta acción eliminará el registro de forma permanente.")

            # Obtener los IDs disponibles para eliminación
            ids_to_delete = edited_df['id'].tolist()
            if ids_to_delete:
                id_to_delete = st.selectbox("Selecciona el ID del registro a eliminar:", ids_to_delete, key=f'delete_select_{option}')
                if st.button(f"Eliminar registro con ID {id_to_delete}", use_container_width=True, type="primary"):
                    delete_row(option, id_to_delete)
                    # Forzar la recarga para mostrar el cambio
                    st.rerun()
            else:
                st.info("No hay registros para eliminar.")
    else:
        st.info(f"No se encontraron datos en la tabla `{option}`.")