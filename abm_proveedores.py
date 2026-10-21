import streamlit as st
import sqlite3

def abm_proveedores():
    st.header("ABM Proveedores")
    conn = sqlite3.connect("minerva.db")
    cursor = conn.cursor()

    # Alta
    st.subheader("Agregar Proveedor")
    nombre = st.text_input("Nombre")
    contacto = st.text_input("Contacto")
    cuit = st.text_input("CUIT")
    direccion = st.text_input("Dirección")
    telefono = st.text_input("Teléfono")
    email = st.text_input("Email")
    if st.button("Agregar Proveedor"):
        if nombre:
            cursor.execute("""
                INSERT INTO proveedores (nombre, contacto, cuit, direccion, telefono, email)
                VALUES (?, ?, ?, ?, ?, ?)""", (nombre, contacto, cuit, direccion, telefono, email))
            conn.commit()
            st.success("Proveedor agregado.")
        else:
            st.warning("El nombre es obligatorio.")

    # Listar y editar/eliminar
    st.subheader("Proveedores existentes")
    cursor.execute("SELECT id, nombre, contacto FROM proveedores")
    for id, nombre, contacto in cursor.fetchall():
        col1, col2, col3, col4 = st.columns([3,3,2,2])
        with col1: st.write(nombre)
        with col2: st.write(contacto if contacto else "-")
        with col3:
            if st.button("Editar", key=f"edit_prov_{id}"):
                nuevo_nombre = st.text_input(f"Nuevo nombre para {nombre}", value=nombre, key=f"input_prov_{id}")
                nuevo_contacto = st.text_input(f"Nuevo contacto para {nombre}", value=contacto or "", key=f"input_contacto_prov_{id}")
                if st.button("Guardar Cambios", key=f"save_prov_{id}"):
                    cursor.execute("UPDATE proveedores SET nombre=?, contacto=? WHERE id=?", (nuevo_nombre, nuevo_contacto, id))
                    conn.commit()
                    st.success("Proveedor actualizado.")
                    st.experimental_rerun()
        with col4:
            if st.button("Eliminar", key=f"del_prov_{id}"):
                cursor.execute("DELETE FROM proveedores WHERE id=?", (id,))
                conn.commit()
                st.warning("Proveedor eliminado.")
                st.experimental_rerun()
    conn.close()
