import streamlit as st
import sqlite3

def abm_envases():
    st.header("ABM Envases")
    conn = sqlite3.connect("minerva.db")
    cursor = conn.cursor()

    # Obtener clientes
    cursor.execute("SELECT id, nombre FROM clientes")
    clientes = cursor.fetchall()
    cliente_dict = {nombre: id for id, nombre in clientes}

    st.subheader("Agregar Envase")
    descripcion = st.text_input("Descripción")
    unidad = st.text_input("Unidad")
    capacidad = st.number_input("Capacidad en litros", min_value=0.0, step=0.01)
    cliente_nombre = st.selectbox("Cliente", list(cliente_dict.keys()))
    cliente_id = cliente_dict[cliente_nombre]
    if st.button("Agregar Envase"):
        if descripcion and unidad:
            cursor.execute("INSERT INTO envases (descripcion, unidad, capacidad_litros, cliente_id) VALUES (?, ?, ?, ?)",
                           (descripcion, unidad, capacidad, cliente_id))
            conn.commit()
            st.success("Envase agregado.")
        else:
            st.warning("Descripción y unidad son obligatorios.")

    st.subheader("Envases existentes")
    cursor.execute("""
        SELECT e.id, e.descripcion, e.unidad, e.capacidad_litros, c.nombre 
        FROM envases e JOIN clientes c ON e.cliente_id = c.id
    """)
    for id, desc, unidad, cap, cliente in cursor.fetchall():
        col1, col2, col3, col4, col5 = st.columns([3,2,2,2,2])
        with col1: st.write(desc)
        with col2: st.write(unidad)
        with col3: st.write(cap)
        with col4: st.write(cliente)
        with col5:
            if st.button("Eliminar", key=f"del_env_{id}"):
                cursor.execute("DELETE FROM envases WHERE id=?", (id,))
                conn.commit()
                st.warning("Envase eliminado.")
                st.experimental_rerun()
    conn.close()
