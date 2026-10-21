import streamlit as st
import sqlite3

def abm_lineas():
    st.header("ABM Líneas")
    conn = sqlite3.connect("minerva.db")
    cursor = conn.cursor()

    st.subheader("Agregar Línea")
    nombre = st.text_input("Nombre de la línea")
    if st.button("Agregar Línea"):
        if nombre:
            cursor.execute("INSERT INTO lineas (nombre) VALUES (?)", (nombre,))
            conn.commit()
            st.success("Línea agregada.")
        else:
            st.warning("El nombre es obligatorio.")

    st.subheader("Líneas existentes")
    cursor.execute("SELECT id, nombre FROM lineas")
    for id, nombre in cursor.fetchall():
        col1, col2 = st.columns([3,2])
        with col1: st.write(nombre)
        with col2:
            if st.button("Eliminar", key=f"del_linea_{id}"):
                cursor.execute("DELETE FROM lineas WHERE id=?", (id,))
                conn.commit()
                st.warning("Línea eliminada.")
                st.experimental_rerun()
    conn.close()
