# materias_primas.py (versión con precio unitario más reciente)

import streamlit as st
import sqlite3
import pandas as pd

DB_PATH = "minerva.db"

def conectar():
    return sqlite3.connect(DB_PATH)

def gestionar_materias_primas():
    usuario = st.session_state.get("usuario", None)
    if not usuario or usuario.get("rol") != "Administrador":
        st.error("Acceso denegado. Solo administradores.")
        st.stop()

    st.header("Gestión de Materias Primas")

    conn = conectar()
    cursor = conn.cursor()

    # Obtener materias primas con su precio unitario más reciente
    cursor.execute("""
        SELECT mp.id, mp.nombre, mp.unidad,
    (
            SELECT pmp.precio_unitario
            FROM precios_materias_primas pmp
            WHERE pmp.materia_prima_id = mp.id
            ORDER BY pmp.fecha DESC, pmp.id DESC -- Agregamos pmp.id DESC aquí
            LIMIT 1
        ) AS precio_unitario
    FROM materias_primas mp
    ORDER BY mp.nombre
    """)
    rows = cursor.fetchall()
    df = pd.DataFrame(rows, columns=["ID", "Nombre", "Unidad", "Precio Unitario ($/unidad)"])

    # Mostrar en data_editor (solo ID no editable, pero precio también solo lectura)
    df_editado = st.data_editor(
        df,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "ID": st.column_config.Column(disabled=True),
            "Precio Unitario ($/unidad)": st.column_config.Column(disabled=True),
        },
        key="editor_materias_primas"
    )

    if st.button("Guardar cambios"):
        cambios = []
        for _, row in df_editado.iterrows():
            cursor.execute("SELECT nombre, unidad FROM materias_primas WHERE id = ?", (row["ID"],))
            original = cursor.fetchone()
            if original and (row["Nombre"] != original[0] or row["Unidad"] != original[1]):
                cursor.execute("""
                    UPDATE materias_primas SET nombre = ?, unidad = ? WHERE id = ?
                """, (row["Nombre"], row["Unidad"], row["ID"]))
                cambios.append(f"- ID {row['ID']}: actualizado")

        if cambios:
            conn.commit()
            st.success("Cambios guardados:")
            for c in cambios:
                st.write(c)
        else:
            st.info("No hubo cambios.")

    st.markdown("---")
    st.subheader("Agregar nueva materia prima")

    nombre_nuevo = st.text_input("Nombre de la materia prima")
    unidad_nueva = st.selectbox("Unidad base", ["g", "kg", "ml", "litros", "unidades"])

    if st.button("Agregar materia prima"):
        if not nombre_nuevo.strip():
            st.warning("Debe ingresar un nombre válido.")
        else:
            cursor.execute("SELECT COUNT(*) FROM materias_primas WHERE nombre = ?", (nombre_nuevo.strip(),))
            if cursor.fetchone()[0] > 0:
                st.error("Ya existe una materia prima con ese nombre.")
            else:
                cursor.execute(
                    "INSERT INTO materias_primas (nombre, unidad) VALUES (?, ?)",
                    (nombre_nuevo.strip(), unidad_nueva)
                )
                conn.commit()
                st.success("Materia prima agregada correctamente.")
                st.experimental_rerun()

    conn.close()

if __name__ == "__main__":
    gestionar_materias_primas()
