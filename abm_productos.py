import streamlit as st
import sqlite3
import pandas as pd

def abm_productos():
    st.header("ABM Productos")
    
    # Conexión a la base de datos
    try:
        conn = sqlite3.connect("minerva.db")
        cursor = conn.cursor()
    except sqlite3.Error as e:
        st.error(f"Error al conectar con la base de datos: {e}")
        return

    # Obtener todas las líneas
    cursor.execute("SELECT id, nombre FROM lineas ORDER BY nombre")
    lineas = cursor.fetchall()
    linea_dict = {nombre: id for id, nombre in lineas}
    linea_nombres = list(linea_dict.keys())

    # Obtener todos los clientes
    cursor.execute("SELECT id, nombre FROM clientes ORDER BY nombre")
    clientes = cursor.fetchall()
    cliente_dict = {nombre: id for id, nombre in clientes}
    cliente_nombres = list(cliente_dict.keys())

    # Obtener todos los envases
    cursor.execute("SELECT id, descripcion FROM envases ORDER BY descripcion")
    envases = cursor.fetchall()
    envase_dict = {desc: id for id, desc in envases}
    envase_nombres = [""] + list(envase_dict.keys())

    # Obtener todas las recetas
    cursor.execute("SELECT id, nombre FROM recetas ORDER BY nombre")
    recetas = cursor.fetchall()
    receta_dict = {nombre: id for id, nombre in recetas}
    receta_nombres = [""] + list(receta_dict.keys())
    
    st.subheader("Agregar Producto")
    with st.form(key="form_agregar_producto"):
        # Campos para la tabla 'productos'
        st.markdown("##### Datos del Producto (Tabla `productos`)")
        nombre = st.text_input("Nombre del producto")
        linea_nombre = st.selectbox("Línea", linea_nombres)
        cliente_nombre = st.selectbox("Cliente", cliente_nombres)
        receta_nombre = st.selectbox("Receta", receta_nombres)
        envase_nombre = st.selectbox("Envase (Opcional)", envase_nombres)
        
        # Campos adicionales para la tabla 'productos_clientes'
        st.markdown("##### Datos del Producto Cliente (Tabla `productos_clientes`)")
        uso = st.text_input("Uso del producto (e.g., 'Cera', 'Gel de afeitar')")
        linea_pc = st.text_input("Línea del producto cliente (e.g., 'LINEA BLACK')")
        
        submit_button = st.form_submit_button("Agregar Producto")

        if submit_button:
            if nombre and linea_nombre and cliente_nombre and receta_nombre and uso and linea_pc:
                linea_id = linea_dict[linea_nombre]
                cliente_id = cliente_dict[cliente_nombre]
                envase_id = envase_dict.get(envase_nombre)
                receta_id = receta_dict[receta_nombre]
                
                try:
                    conn.execute("BEGIN;")
                    cursor.execute("""
                        INSERT INTO productos (nombre, linea_id, cliente_id, envase_id, id_receta)
                        VALUES (?, ?, ?, ?, ?)""", 
                        (nombre, linea_id, cliente_id, envase_id, receta_id))
                    
                    producto_id = cursor.lastrowid
                    
                    cursor.execute("""
                        INSERT INTO productos_clientes (producto_id, cliente_id, uso, linea)
                        VALUES (?, ?, ?, ?)""",
                        (producto_id, cliente_id, uso, linea_pc))
                    
                    conn.commit()
                    st.success("✅ Producto agregado con éxito.")
                    st.rerun()
                except sqlite3.Error as e:
                    conn.rollback()
                    st.error(f"❌ Error al agregar el producto: {e}")
            else:
                st.warning("El nombre, la línea, el cliente, la receta, el uso y la línea del producto cliente son obligatorios.")

    st.subheader("Editar o Eliminar Productos")
    
    # Consulta unificada para obtener todos los datos necesarios
    query = """
        SELECT 
            p.id, 
            p.nombre AS Nombre, 
            l.nombre AS Linea, 
            c.nombre AS Cliente, 
            e.descripcion AS Envase,
            r.nombre AS Receta,
            pc.uso AS Uso,
            pc.linea AS 'Linea (Cliente)'
        FROM productos p
        JOIN lineas l ON p.linea_id = l.id
        JOIN clientes c ON p.cliente_id = c.id
        LEFT JOIN envases e ON p.envase_id = e.id
        LEFT JOIN recetas r ON p.id_receta = r.id
        LEFT JOIN productos_clientes pc ON p.id = pc.producto_id
        ORDER BY p.nombre
    """
    df_productos = pd.read_sql_query(query, conn)
    
    if not df_productos.empty:
        # Añadir una columna de selección para eliminar
        df_productos['Eliminar'] = False

        # Usar st.data_editor para una visualización interactiva
        edited_df = st.data_editor(
            df_productos,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "id": st.column_config.Column("ID", disabled=True),
                "Eliminar": st.column_config.CheckboxColumn("Seleccionar", help="Selecciona los productos para eliminar", default=False)
            }
        )

        # Botones para guardar cambios o eliminar
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Guardar Cambios"):
                # Lógica para guardar los cambios en la base de datos
                try:
                    for index, row in edited_df.iterrows():
                        original_row = df_productos.loc[index]
                        if not row.equals(original_row):
                            # Si la fila ha sido modificada, actualizamos
                            conn.execute("BEGIN;")

                            # Obtener los IDs de los campos de texto
                            new_linea_id = linea_dict.get(row['Linea'])
                            new_cliente_id = cliente_dict.get(row['Cliente'])
                            new_envase_id = envase_dict.get(row['Envase'])
                            new_receta_id = receta_dict.get(row['Receta'])

                            # Actualizar tabla 'productos'
                            cursor.execute("""
                                UPDATE productos 
                                SET nombre=?, linea_id=?, cliente_id=?, envase_id=?, id_receta=?
                                WHERE id=?
                            """, (row['Nombre'], new_linea_id, new_cliente_id, new_envase_id, new_receta_id, row['id']))
                            
                            # Actualizar tabla 'productos_clientes'
                            cursor.execute("""
                                UPDATE productos_clientes
                                SET uso=?, linea=?
                                WHERE producto_id=?
                            """, (row['Uso'], row['Linea (Cliente)'], row['id']))

                    conn.commit()
                    st.success("✅ ¡Cambios guardados con éxito!")
                    st.rerun()
                except sqlite3.Error as e:
                    conn.rollback()
                    st.error(f"❌ Error al guardar los cambios: {e}")

        with col2:
            if st.button("🗑️ Eliminar Seleccionados"):
                # Lógica para eliminar los productos seleccionados
                rows_to_delete = edited_df[edited_df['Eliminar']]
                if not rows_to_delete.empty:
                    try:
                        conn.execute("BEGIN;")
                        for product_id in rows_to_delete['id']:
                            # Eliminar de la tabla 'productos_clientes' primero
                            cursor.execute("DELETE FROM productos_clientes WHERE producto_id=?", (product_id,))
                            # Eliminar de la tabla 'productos'
                            cursor.execute("DELETE FROM productos WHERE id=?", (product_id,))
                        conn.commit()
                        st.warning(f"🗑️ Se eliminaron {len(rows_to_delete)} producto(s) y sus relaciones.")
                        st.rerun()
                    except sqlite3.Error as e:
                        conn.rollback()
                        st.error(f"❌ Error al eliminar los productos: {e}")
                else:
                    st.warning("⚠️ No hay productos seleccionados para eliminar.")

    else:
        st.info("No hay productos registrados.")
    
    conn.close()

if __name__ == "__main__":
    abm_productos()
