import streamlit as st
import sqlite3
import pandas as pd

# Título de la aplicación
st.title('Validación de Movimientos de Materia Prima')

# Función para conectar a la base de datos SQLite
def conectar_db():
    try:
        conn = sqlite3.connect('minerva.db')  # Reemplaza con el nombre de tu base de datos
        return conn
    except sqlite3.Error as e:
        st.error(f"Error de SQLite: {e}")
        return None

# Función para obtener los valores únicos de una columna
def obtener_valores_unicos(conn, tabla, columna):
    try:
        query = f"SELECT DISTINCT {columna} FROM {tabla}"
        df = pd.read_sql_query(query, conn)
        return df[columna].tolist()
    except sqlite3.Error as e:
        st.error(f"Error al obtener valores únicos de {columna}: {e}")
        return []

# Función para validar los movimientos de materia prima
def validar_movimientos(materia_prima_filtro=None, receta_filtro=None, estado_filtro=None):
    conn = conectar_db()
    if not conn:
        return None

    try:
        query = """
        SELECT
            mmp.id AS movimiento_id,
            mmp.lote,
            mmp.materia_prima_id,
            mp.nombre AS materia_prima_nombre,
            mmp.cantidad,
            r.nombre AS receta_nombre,
            p.fecha AS produccion_fecha,
            p.estado AS produccion_estado,
            CASE
                WHEN p.estado = 'anulado' THEN 'Producción Anulada'
                WHEN mmp.tipo_movimiento != 'egreso' THEN 'No es un Egreso'
                WHEN mmp.destino != 'produccion' THEN 'No es para Producción'
                ELSE 'OK'
            END AS validacion
        FROM movimientos_materia_prima AS mmp
        JOIN materias_primas AS mp ON mmp.materia_prima_id = mp.id
        JOIN lotes AS l ON mmp.lote = l.numero
        JOIN recetas AS r ON l.receta_id = r.id
        JOIN producciones AS p ON l.numero = p.lote
        WHERE 1=1  -- Condición siempre verdadera para facilitar la concatenación de filtros
        """

        # Agregar filtros dinámicamente
        if materia_prima_filtro:
            query += f" AND mp.nombre = '{materia_prima_filtro}'"
        if receta_filtro:
            query += f" AND r.nombre = '{receta_filtro}'"
        if estado_filtro:
            query += f" AND p.estado = '{estado_filtro}'"

        query += " ORDER BY mmp.lote, mmp.materia_prima_id"

        df = pd.read_sql_query(query, conn)
    except sqlite3.Error as e:
        st.error(f"Error al ejecutar la consulta: {e}")
        return None
    finally:
        conn.close()

    return df

# --- Interfaz Streamlit ---

# Conectar a la base de datos
conn = conectar_db()
if not conn:
    st.stop()

# Obtener valores únicos para los filtros
materias_primas = [''] + obtener_valores_unicos(conn, 'materias_primas', 'nombre')
recetas = [''] + obtener_valores_unicos(conn, 'recetas', 'nombre')
estados = [''] + obtener_valores_unicos(conn, 'producciones', 'estado')

conn.close()

# Crear filtros en la barra lateral
st.sidebar.header("Filtros")
materia_prima_filtro = st.sidebar.selectbox("Materia Prima:", materias_primas)
receta_filtro = st.sidebar.selectbox("Receta:", recetas)
estado_filtro = st.sidebar.selectbox("Estado de Producción:", estados)

# Validar y mostrar los movimientos filtrados
df_validacion = validar_movimientos(materia_prima_filtro, receta_filtro, estado_filtro)

if df_validacion is not None:
    if isinstance(df_validacion, pd.DataFrame):
        if not df_validacion.empty:
            st.subheader("Validación de Movimientos de Materia Prima")
            st.dataframe(
                df_validacion,
                column_config={
                    "movimiento_id": st.column_config.Column("ID Movimiento", disabled=True),
                    "lote": "Lote",
                    "materia_prima_id": "ID Materia Prima",
                    "materia_prima_nombre": "Materia Prima",
                    "cantidad": "Cantidad",
                    "receta_nombre": "Receta",
                    "produccion_fecha": "Fecha Producción",
                    "produccion_estado": "Estado Producción",
                    "validacion": "Validación",
                },
                hide_index=True,
            )
        else:
            st.warning("No hay movimientos que coincidan con los filtros seleccionados.")
    else:
        st.error("Los datos retornados no tienen el formato correcto.")
else:
    st.error("No se pudieron obtener los datos. Verifica la conexión a la base de datos y la consulta SQL.")