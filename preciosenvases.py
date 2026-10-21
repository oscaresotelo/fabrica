import streamlit as st
import sqlite3

def abm_precios_envases():
    st.title("ABM Precios y Descripción de Envases")
    conn = sqlite3.connect("minerva.db")
    cursor = conn.cursor()

    # 1. Alta de precios de envases
    st.subheader("Asignar/Actualizar Precio de Envase")
    cursor.execute("SELECT id, descripcion FROM envases")
    envases = cursor.fetchall()
    envase_dict = {nombre: id for id, nombre in envases}
    envase_nombre = st.selectbox("Seleccionar Envase", list(envase_dict.keys()))
    nuevo_precio = st.number_input("Precio unitario", min_value=0.0)

    if st.button("Asignar/Actualizar Precio"):
        if envase_nombre and nuevo_precio:
            envase_id = envase_dict[envase_nombre]
            cursor.execute("""
                UPDATE entradas_envases SET precio_unitario = ? WHERE envase_id = ?
            """, (nuevo_precio, envase_id))
            conn.commit()
            st.success(f"Precio del envase '{envase_nombre}' actualizado a ${nuevo_precio}.")

        else:
            st.warning("Por favor, selecciona un envase y asigna un precio.")

    # 2. Modificación de la descripción del envase
    st.subheader("Modificar Descripción de Envase")
    envase_sel = st.selectbox("Seleccionar Envase a Modificar", list(envase_dict.keys()), key="select_modificar_envase")
    nueva_descripcion = st.text_input("Nueva Descripción", value=envase_sel)

    if st.button("Modificar Descripción"):
        if envase_sel and nueva_descripcion:
            envase_id = envase_dict[envase_sel]
            cursor.execute("UPDATE envases SET descripcion = ? WHERE id = ?", (nueva_descripcion, envase_id))
            conn.commit()
            st.success(f"Descripción del envase {envase_sel} actualizada a '{nueva_descripcion}'.")
            st.experimental_rerun()
        else:
            st.warning("Por favor, selecciona un envase e ingresa una nueva descripción.")

    # Listar los envases para control
    st.subheader("Listado de Envases con Precios")
    cursor.execute("""
        SELECT e.id, e.descripcion, ee.precio_unitario
        FROM envases e
        LEFT JOIN entradas_envases ee ON e.id = ee.envase_id
        GROUP BY e.id, e.descripcion, ee.precio_unitario
    """)
    envases_con_precios = cursor.fetchall()

    if envases_con_precios:
        st.write("Envases:")
        for id, descripcion, precio in envases_con_precios:
            precio_str = f"${precio:.2f}" if precio else "Sin precio asignado"
            st.write(f"- {descripcion}: {precio_str}")
    else:
        st.info("No hay envases cargados.")

    conn.close()

# --- Ejecución principal ---
if __name__ == "__main__":
    abm_precios_envases()