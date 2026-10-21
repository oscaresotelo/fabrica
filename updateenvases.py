import streamlit as st
import sqlite3

# Función para conectarse a la base de datos 'minerva.db'
def load_db():
    try:
        # Conexión directa al archivo de base de datos
        conn = sqlite3.connect('minerva.db')
        return conn
    except Exception as e:
        st.error(f"Error al conectarse a la base de datos: {e}")
        return None

# Carga la base de datos al inicio de la aplicación
conn = load_db()

if conn:
    st.title("Actualizar ID de Envase de un Producto")
    st.markdown("---")

    # Obtener la lista de productos existentes
    try:
        productos_query = "SELECT id, id_receta, envase_id FROM productos;"
        productos_df = conn.execute(productos_query).fetchall()
        
        recetas_query = "SELECT id, nombre FROM recetas;"
        recetas_df = conn.execute(recetas_query).fetchall()

        envases_query = "SELECT id, descripcion FROM envases;"
        envases_df = conn.execute(envases_query).fetchall()

        # Crear diccionarios para una búsqueda rápida
        recetas_dict = {receta[0]: receta[1] for receta in recetas_df}
        envases_dict = {envase[0]: envase[1] for envase in envases_df}

        # Generar una lista de opciones para el selectbox de productos
        productos_options = []
        for p_id, r_id, e_id in productos_df:
            receta_nombre = recetas_dict.get(r_id, "Desconocida")
            envase_descripcion = envases_dict.get(e_id, "Desconocido")
            productos_options.append((p_id, f"ID: {p_id} | Receta: {receta_nombre} | Envase Actual: {envase_descripcion}"))

    except sqlite3.OperationalError:
        st.warning("No se pudo cargar la información. Asegúrate de que las tablas 'productos', 'recetas' y 'envases' existen en tu archivo SQL.")
        productos_options = []

    if productos_options:
        # Selector para elegir el producto a modificar
        producto_seleccionado = st.selectbox(
            "Selecciona el producto a modificar:",
            productos_options,
            format_func=lambda x: x[1]
        )
        
        producto_id = producto_seleccionado[0]

        # Selector para elegir el nuevo envase
        envases_options = envases_df
        nuevo_envase_seleccionado = st.selectbox(
            "Selecciona el nuevo envase:",
            envases_options,
            format_func=lambda x: f"ID: {x[0]} | {x[1]}"
        )
        
        nuevo_envase_id = nuevo_envase_seleccionado[0]

        st.markdown("---")
        
        # Botón para ejecutar la actualización
        if st.button("Actualizar ID de Envase"):
            try:
                # Consulta SQL para actualizar la tabla 'productos'
                update_query = "UPDATE productos SET envase_id = ? WHERE id = ?;"
                conn.execute(update_query, (nuevo_envase_id, producto_id))
                conn.commit()
                st.success(f"¡El envase del producto con ID {producto_id} se actualizó correctamente a ID {nuevo_envase_id}!")
                st.balloons()
            except sqlite3.OperationalError as e:
                st.error(f"Error al actualizar la base de datos: {e}")
            finally:
                conn.close()

else:
    st.error("No se pudo establecer la conexión con la base de datos.")