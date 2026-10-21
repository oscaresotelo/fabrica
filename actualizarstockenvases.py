# import streamlit as st
# import sqlite3

# def actualizar_stock_envases():
#     st.header("Reducir Stock de Envases")

#     conn = sqlite3.connect("minerva.db")
#     cursor = conn.cursor()

#     # Obtener lista de envases con su stock actual
#     cursor.execute("""
#         SELECT e.id, e.descripcion, COALESCE(s.cantidad, 0)
#         FROM envases e
#         LEFT JOIN stock_envases_clientes s ON e.id = s.envase_id
#     """)
#     envases = cursor.fetchall()

#     # Diccionario unificado: la clave es la que muestra el selectbox
#     envases_dict = {
#         f"{desc} (Stock: {cantidad})": {"id": id_, "stock": cantidad}
#         for id_, desc, cantidad in envases
#     }

#     # Crear formulario
#     with st.form("restar_stock"):
#         envase_descripcion = st.selectbox("Seleccione un envase", options=list(envases_dict.keys()))
#         cantidad_a_restar = st.number_input("Cantidad a restar", min_value=1, step=1)
#         submitted = st.form_submit_button("Restar Stock")

#         if submitted:
#             envase_info = envases_dict[envase_descripcion]
#             envase_id = envase_info["id"]
#             stock_actual = envase_info["stock"]

#             # Obtener el stock actual desde la base
#             cursor.execute("SELECT cantidad FROM stock_envases_clientes WHERE envase_id = ?", (envase_id,))
#             result = cursor.fetchone()

#             if result is None:
#                 st.error("No existe stock para ese envase. Primero debe realizar un ingreso.")
#                 conn.close()
#                 st.stop()

#             stock_actual = result[0]

#             # Validar que la cantidad a restar no sea mayor al stock actual
#             if cantidad_a_restar > stock_actual:
#                 st.error(f"No hay suficiente stock. Stock actual: {stock_actual}")
#                 conn.close()
#                 st.stop()

#             # Restar la cantidad del stock
#             nuevo_stock = stock_actual - cantidad_a_restar
#             cursor.execute("UPDATE stock_envases_clientes SET cantidad = ? WHERE envase_id = ?", (nuevo_stock, envase_id))
#             conn.commit()

#             st.success(f"Stock actualizado. Nuevo stock: {nuevo_stock}")

#             conn.close()
#             st.rerun()

#     conn.close()

# actualizar_stock_envases()
import streamlit as st
import sqlite3

def actualizar_stock_envases():
    st.header("Actualizar Stock de Envases")

    conn = sqlite3.connect("minerva.db")
    cursor = conn.cursor()

    # Obtener lista de envases con su stock actual
    cursor.execute("""
        SELECT e.id, e.descripcion, COALESCE(s.cantidad, 0)
        FROM envases e
        LEFT JOIN stock_envases_clientes s ON e.id = s.envase_id
    """)
    envases = cursor.fetchall()

    # Diccionario con clave única usando ID + descripción
    envases_dict = {
        f"{desc} (ID {id_})": {"id": id_, "desc": desc, "stock": cantidad}
        for id_, desc, cantidad in envases
    }

    # ---- SELECCIÓN DEL ENVASE (fuera del formulario) ----
    seleccion = st.selectbox("Seleccione un envase", options=list(envases_dict.keys()))

    envase_info = envases_dict[seleccion]
    st.info(f"Stock actual: **{envase_info['stock']}**")

    # ---- FORMULARIO SOLO PARA ACTUALIZAR ----
    with st.form("actualizar_stock"):
        nuevo_stock = st.number_input("Nuevo stock", min_value=0, step=1)
        submitted = st.form_submit_button("Actualizar")

        if submitted:
            cursor.execute("""
                UPDATE stock_envases_clientes 
                SET cantidad = ? 
                WHERE envase_id = ?
            """, (nuevo_stock, envase_info["id"]))

            conn.commit()
            st.success("Stock actualizado.")
            st.rerun()

    conn.close()

actualizar_stock_envases()
