import streamlit as st
import sqlite3

def obtener_clientes(conn):
    return conn.execute("SELECT id, nombre FROM clientes ORDER BY nombre").fetchall()

def obtener_materias_primas(conn):
    return conn.execute("SELECT id, nombre, unidad FROM materias_primas ORDER BY nombre").fetchall()

def obtener_recetas(conn):
    return conn.execute("SELECT id, nombre FROM recetas ORDER BY nombre").fetchall()

def obtener_ingredientes_de_receta(conn, receta_id):
    return conn.execute("""
        SELECT ri.id, mp.nombre, ri.cantidad, ri.unidad
        FROM receta_ingredientes ri
        JOIN materias_primas mp ON ri.materia_prima_id = mp.id
        WHERE ri.receta_id = ?
    """, (receta_id,)).fetchall()

def ajustar_unidad(cantidad, unidad):
    if unidad.lower() in ["kg", "kilos", "kilogramos"] and cantidad < 1:
        return cantidad * 1000, "g"
    elif unidad.lower() in ["l", "litro", "litros"] and cantidad < 1:
        return cantidad * 1000, "cm³"
    else:
        return cantidad, unidad

def gestionar_recetas():
    st.header("Gestión de Recetas")

    conn = sqlite3.connect("minerva.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Convertir filas a tuplas para Streamlit
    clientes = [(c["id"], c["nombre"]) for c in obtener_clientes(conn)]
    materias = [(m["id"], m["nombre"], m["unidad"]) for m in obtener_materias_primas(conn)]
    recetas = [(r["id"], r["nombre"]) for r in obtener_recetas(conn)]

    # Sidebar: Crear nueva receta
    with st.sidebar:
        st.subheader("Nueva Receta")
        nuevo_nombre = st.text_input("Nombre de la receta")
        nuevo_cliente = st.selectbox("Cliente", clientes, format_func=lambda x: x[1])

        if st.button("Crear Receta"):
            if nuevo_nombre and nuevo_cliente:
                cursor.execute("INSERT INTO recetas (nombre, cliente_id) VALUES (?, ?)",
                               (nuevo_nombre.upper(), nuevo_cliente[0]))
                conn.commit()
                st.success("Receta creada correctamente.")
                st.rerun()
            else:
                st.warning("Debe completar el nombre y seleccionar un cliente.")

    # Seleccionar receta a editar
    st.subheader("Editar Receta Existente")
    receta_seleccionada = st.selectbox("Seleccione una receta", recetas, format_func=lambda x: x[1])

    if receta_seleccionada:
        receta_id = receta_seleccionada[0]
        cursor.execute("SELECT nombre, cliente_id FROM recetas WHERE id = ?", (receta_id,))
        receta_info = cursor.fetchone()
        nombre_actual, cliente_actual_id = receta_info["nombre"], receta_info["cliente_id"]

        nuevo_nombre = st.text_input("Nombre de la receta", value=nombre_actual)
        nuevo_cliente = st.selectbox("Cliente asociado", clientes, format_func=lambda x: x[1],
                                     index=[i for i, c in enumerate(clientes) if c[0] == cliente_actual_id][0])

        if st.button("Actualizar Receta"):
            cursor.execute("UPDATE recetas SET nombre = ?, cliente_id = ? WHERE id = ?",
                           (nuevo_nombre.upper(), nuevo_cliente[0], receta_id))
            conn.commit()
            st.success("Receta actualizada correctamente.")
            st.rerun()

        # Ingredientes actuales
        st.markdown("### Ingredientes actuales")
        ingredientes = obtener_ingredientes_de_receta(conn, receta_id)
        if ingredientes:
            for ingr in ingredientes:
                id_ri, nombre_mp, cantidad, unidad = ingr
                cantidad_ajustada, unidad_ajustada = ajustar_unidad(cantidad, unidad)
                col1, col2, col3 = st.columns([4, 3, 2])
                with col1:
                    st.write(f"**{nombre_mp} ({unidad_ajustada})**")
                with col2:
                    nueva_cantidad = st.number_input(
                        label=f"Cantidad {nombre_mp}",
                        value=float(f"{cantidad_ajustada:.4f}"),
                        min_value=0.0,
                        format="%.4f",
                        key=f"cantidad_{id_ri}"
                    )
                with col3:
                    if st.button("Actualizar", key=f"update_{id_ri}"):
                        # Volver a convertir si fue visualizado en gramos/cm³
                        if unidad_ajustada == "g":
                            cantidad_guardar = nueva_cantidad / 1000
                        elif unidad_ajustada == "cm³":
                            cantidad_guardar = nueva_cantidad / 1000
                        else:
                            cantidad_guardar = nueva_cantidad

                        cursor.execute("UPDATE receta_ingredientes SET cantidad = ? WHERE id = ?", (cantidad_guardar, id_ri))
                        conn.commit()
                        st.success(f"Cantidad actualizada para {nombre_mp}.")
                        st.rerun()

                if st.button(f"Eliminar {nombre_mp}", key=f"delete_{id_ri}"):
                    cursor.execute("DELETE FROM receta_ingredientes WHERE id = ?", (id_ri,))
                    conn.commit()
                    st.success(f"{nombre_mp} eliminado de la receta.")
                    st.rerun()
        else:
            st.info("La receta no tiene ingredientes aún.")

        # Agregar nuevo ingrediente
        st.markdown("### Agregar Ingrediente")
        mp = st.selectbox("Materia Prima", materias, format_func=lambda x: f"{x[1]} ({x[2]})")
        cantidad = st.number_input("Cantidad", min_value=0.0, format="%.4f", key="nueva_cantidad")
        unidad = mp[2]

        if st.button("Agregar Ingrediente"):
            cursor.execute("""
                INSERT INTO receta_ingredientes (receta_id, materia_prima_id, cantidad, unidad)
                VALUES (?, ?, ?, ?)
            """, (receta_id, mp[0], cantidad, unidad))
            conn.commit()
            st.success("Ingrediente agregado.")
            st.rerun()

    conn.close()

# --- Control de acceso ---
if "usuario" not in st.session_state:
    st.error("Acceso denegado. Inicie sesión.")
elif st.session_state.usuario["rol"] != "Administrador":
    st.error("Acceso restringido. Solo para Administradores.")
else:
    gestionar_recetas()
