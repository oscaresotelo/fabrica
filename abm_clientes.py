import streamlit as st
import sqlite3

def abm_clientes():
    st.header("ABM Clientes")
    conn = sqlite3.connect("minerva.db")
    cursor = conn.cursor()

    # Alta
    st.subheader("Agregar Cliente")
    nombre = st.text_input("Nombre")
    contacto = st.text_input("Contacto")
    if st.button("Agregar Cliente"):
        if nombre:
            cursor.execute("INSERT INTO clientes (nombre, contacto) VALUES (?, ?)", (nombre, contacto))
            conn.commit()
            st.success("Cliente agregado.")
        else:
            st.warning("El nombre es obligatorio.")

    # Listar y editar/eliminar
    st.subheader("Clientes existentes")
    cursor.execute("SELECT id, nombre, contacto FROM clientes")
    for id, nombre, contacto in cursor.fetchall():
        col1, col2, col3, col4 = st.columns([3,3,2,2])
        with col1: st.write(nombre)
        with col2: st.write(contacto if contacto else "-")
        with col3:
            if st.button("Editar", key=f"edit_cliente_{id}"):
                nuevo_nombre = st.text_input(f"Nuevo nombre para {nombre}", value=nombre, key=f"input_cliente_{id}")
                nuevo_contacto = st.text_input(f"Nuevo contacto para {nombre}", value=contacto or "", key=f"input_contacto_{id}")
                if st.button("Guardar Cambios", key=f"save_cliente_{id}"):
                    cursor.execute("UPDATE clientes SET nombre=?, contacto=? WHERE id=?", (nuevo_nombre, nuevo_contacto, id))
                    conn.commit()
                    st.success("Cliente actualizado.")
                    st.experimental_rerun()
        with col4:
            if st.button("Eliminar", key=f"del_cliente_{id}"):
                cursor.execute("DELETE FROM clientes WHERE id=?", (id,))
                conn.commit()
                st.warning("Cliente eliminado.")
                st.experimental_rerun()
    conn.close()
