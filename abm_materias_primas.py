import streamlit as st
import sqlite3

def abm_materias_primas():
    st.header("ABM Materias Primas")
    conn = sqlite3.connect("minerva.db")
    cursor = conn.cursor()

    st.subheader("Agregar Materia Prima")
    nombre = st.text_input("Nombre")
    unidad = st.text_input("Unidad")
    if st.button("Agregar Materia Prima"):
        if nombre and unidad:
            cursor.execute("INSERT INTO materias_primas (nombre, unidad) VALUES (?, ?)", (nombre, unidad))
            conn.commit()
            st.success("Materia prima agregada.")
        else:
            st.warning("Nombre y unidad son obligatorios.")

    st.subheader("Materias Primas existentes")
    cursor.execute("SELECT id, nombre, unidad FROM materias_primas")
    for id, nombre, unidad in cursor.fetchall():
        col1, col2, col3 = st.columns([3,2,2])
        with col1: st.write(nombre)
        with col2: st.write(unidad)
        with col3:
            if st.button("Eliminar", key=f"del_mp_{id}"):
                cursor.execute("DELETE FROM materias_primas WHERE id=?", (id,))
                conn.commit()
                st.warning("Materia prima eliminada.")
                st.experimental_rerun()
    conn.close()
