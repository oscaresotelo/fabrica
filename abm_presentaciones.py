import streamlit as st
import sqlite3

def abm_presentaciones():
    st.header("ABM Presentaciones")
    conn = sqlite3.connect("minerva.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id, nombre FROM productos")
    productos = cursor.fetchall()
    producto_dict = {nombre: id for id, nombre in productos}

    cursor.execute("SELECT id, descripcion FROM envases")
    envases = cursor.fetchall()
    envase_dict = {desc: id for id, desc in envases}

    st.subheader("Agregar Presentación")
    producto_nombre = st.selectbox("Producto", list(producto_dict.keys()))
    envase_nombre = st.selectbox("Envase Base", list(envase_dict.keys()))
    nombre_presentacion = st.text_input("Nombre Presentación")
    multiplicador = st.number_input("Multiplicador Unidades Base", min_value=1, step=1)
    orden_jerarquico = st.number_input("Orden Jerárquico", min_value=1, step=1)
    if st.button("Agregar Presentación"):
        if nombre_presentacion:
            cursor.execute("""
                INSERT INTO producto_presentaciones (producto_id, envase_base_id, nombre_presentacion, multiplicador_unidades_base, orden_jerarquico)
                VALUES (?, ?, ?, ?, ?)""", (producto_dict[producto_nombre], envase_dict[envase_nombre], nombre_presentacion, multiplicador, orden_jerarquico))
            conn.commit()
            st.success("Presentación agregada.")
            st.experimental_rerun()
        else:
            st.warning("El nombre de la presentación es obligatorio.")

    st.subheader("Presentaciones existentes")
    cursor.execute("""
        SELECT pp.id, p.nombre, e.descripcion, pp.nombre_presentacion, pp.multiplicador_unidades_base, pp.orden_jerarquico
        FROM producto_presentaciones pp
        JOIN productos p ON pp.producto_id = p.id
        JOIN envases e ON pp.envase_base_id = e.id
        ORDER BY p.nombre, pp.nombre_presentacion
    """)
    for id, producto, envase, nombre_pres, mult, orden in cursor.fetchall():
        st.write(f"Producto: {producto} | Envase: {envase} | Presentación: {nombre_pres} | Mult: {mult} | Orden: {orden}")
        if st.button("Eliminar", key=f"del_pres_{id}"):
            cursor.execute("DELETE FROM producto_presentaciones WHERE id=?", (id,))
            conn.commit()
            st.warning("Presentación eliminada.")
            st.experimental_rerun()
    conn.close()
