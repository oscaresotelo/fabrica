import streamlit as st
import sqlite3

# Función para conectarse a la base de datos 'minerva.db'
def connect_to_db():
    try:
        conn = sqlite3.connect('minerva.db')
        return conn
    except Exception as e:
        st.error(f"Error al conectarse a la base de datos: {e}")
        return None

# Carga la base de datos al inicio de la aplicación
conn = connect_to_db()

if conn:
    st.title("Asociar Tipo de Caja a un Producto (Sin Asignar)")
    st.markdown("---")

    # Obtener la lista de productos sin tipo de caja asignado
    try:
        productos_query = "SELECT p.id, r.nombre AS nombre_receta, e.descripcion AS envase_actual, p.tipo_caja_id FROM productos p JOIN recetas r ON p.id_receta = r.id LEFT JOIN envases e ON p.envase_id = e.id WHERE p.tipo_caja_id IS NULL;"
        productos_data = conn.execute(productos_query).fetchall()

        tipo_cajas_query = "SELECT id, descripcion FROM tipo_cajas;"
        tipo_cajas_data = conn.execute(tipo_cajas_query).fetchall()

        # Crear diccionarios para búsqueda rápida de descripciones
        tipo_cajas_dict = {caja[0]: caja[1] for caja in tipo_cajas_data}

        # Generar una lista de opciones para el selectbox de productos
        productos_options = []
        for p_id, r_nombre, e_descripcion, t_id in productos_data:
            caja_actual = tipo_cajas_dict.get(t_id, "Sin asignar")
            productos_options.append((p_id, f"ID: {p_id} | Receta: {r_nombre} | Envase: {e_descripcion} | Caja Actual: {caja_actual}"))

    except sqlite3.OperationalError:
        st.warning("No se pudo cargar la información. Asegúrate de que las tablas 'productos', 'recetas', 'envases' y 'tipo_cajas' existen en tu base de datos.")
        productos_options = []

    if productos_options:
        # Selector para elegir el producto a modificar
        producto_seleccionado = st.selectbox(
            "Selecciona el producto a modificar:",
            productos_options,
            format_func=lambda x: x[1]
        )
        
        producto_id = producto_seleccionado[0]

        # Selector para elegir el nuevo tipo de caja
        tipo_cajas_options = [(None, "Sin asignar")] + tipo_cajas_data
        nuevo_tipo_caja_seleccionado = st.selectbox(
            "Selecciona el nuevo tipo de caja:",
            tipo_cajas_options,
            format_func=lambda x: f"ID: {x[0]} | {x[1]}" if x[0] else "Sin asignar"
        )
        
        nuevo_tipo_caja_id = nuevo_tipo_caja_seleccionado[0]

        st.markdown("---")
        
        # Botón para ejecutar la actualización
        if st.button("Actualizar Tipo de Caja"):
            try:
                # Consulta SQL para actualizar la tabla 'productos'
                update_query = "UPDATE productos SET tipo_caja_id = ? WHERE id = ?;"
                conn.execute(update_query, (nuevo_tipo_caja_id, producto_id))
                conn.commit()
                st.success(f"¡El tipo de caja del producto con ID {producto_id} se actualizó correctamente a ID {nuevo_tipo_caja_id}!")
                st.balloons()
            except sqlite3.OperationalError as e:
                st.error(f"Error al actualizar la base de datos: {e}")
            finally:
                conn.close()

else:
    st.error("No se pudo establecer la conexión con la base de datos.")