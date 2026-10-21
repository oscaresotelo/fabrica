import streamlit as st
import sqlite3

def abm_recetas():
    st.header("ABM Recetas")
    conn = sqlite3.connect("minerva.db")
    cursor = conn.cursor()

    # --- Cargar opciones para selects ---
    # Clientes
    cursor.execute("SELECT id, nombre FROM clientes")
    clientes = cursor.fetchall()
    cliente_dict = {nombre: id for id, nombre in clientes}

    # Líneas
    cursor.execute("SELECT id, nombre FROM lineas")
    lineas = cursor.fetchall()
    linea_dict = {nombre: id for id, nombre in lineas}

    # Usos únicos ya cargados
    cursor.execute("SELECT DISTINCT uso FROM recetas WHERE uso IS NOT NULL AND uso != ''")
    usos = [row[0] for row in cursor.fetchall()]

    # Materias primas
    cursor.execute("SELECT id, nombre, unidad FROM materias_primas")
    materias = cursor.fetchall()
    mp_dict = {f"{m[1]} ({m[2]})": m[0] for m in materias}

    # --- Alta de receta ---
    st.subheader("Agregar Receta")
    nombre = st.text_input("Nombre de la receta")
    cliente_nombre = st.selectbox("Cliente", list(cliente_dict.keys()))
    linea_nombre = st.selectbox("Línea", [""] + list(linea_dict.keys()))
    uso_sel = st.text_input("Uso (puede escribir uno nuevo o copiar uno existente)")
    if st.button("Agregar Receta"):
        if nombre and cliente_nombre:
            cliente_id = cliente_dict[cliente_nombre]
            linea = linea_nombre if linea_nombre else ""
            uso = uso_sel.strip()
            cursor.execute(
                "INSERT INTO recetas (nombre, cliente_id, uso, linea) VALUES (?, ?, ?, ?)",
                (nombre, cliente_id, uso, linea)
            )
            conn.commit()
            st.success("Receta agregada.")
            st.rerun()
        else:
            st.warning("El nombre y cliente son obligatorios.")

    # --- Listado y gestión de recetas ---
    st.subheader("Recetas existentes")
    cursor.execute("""
        SELECT r.id, r.nombre, c.nombre, r.uso, r.linea 
        FROM recetas r JOIN clientes c ON r.cliente_id = c.id
        ORDER BY r.nombre
    """)
    recetas = cursor.fetchall()
    receta_dict = {f"{r[1]} (Cliente: {r[2]}, Uso: {r[3]}, Línea: {r[4]})": r[0] for r in recetas}

    if recetas:
        receta_sel = st.selectbox("Seleccionar receta para editar/gestionar ingredientes", list(receta_dict.keys()))
        receta_id = receta_dict[receta_sel]

        # Mostrar datos de la receta seleccionada
        cursor.execute("SELECT nombre, cliente_id, uso, linea FROM recetas WHERE id=?", (receta_id,))
        nombre, cliente_id, uso, linea = cursor.fetchone()
        cliente_nombre = [k for k, v in cliente_dict.items() if v == cliente_id][0]
        linea_nombre = linea if linea else ""

        st.write(f"**Nombre:** {nombre}")
        st.write(f"**Cliente:** {cliente_nombre}")
        st.write(f"**Uso:** {uso}")
        st.write(f"**Línea:** {linea_nombre}")

        # Edición de datos generales
        with st.expander("Editar datos de la receta"):
            nuevo_nombre = st.text_input("Nuevo nombre", value=nombre, key=f"edit_nombre_{receta_id}")
            nuevo_cliente_nombre = st.selectbox("Nuevo cliente", list(cliente_dict.keys()), index=list(cliente_dict.keys()).index(cliente_nombre), key=f"edit_cliente_{receta_id}")
            nuevo_linea_nombre = st.selectbox("Nueva línea", [""] + list(linea_dict.keys()), index=([""] + list(linea_dict.keys())).index(linea_nombre) if linea_nombre in linea_dict else 0, key=f"edit_linea_{receta_id}")
            nuevo_uso = st.text_input("Nuevo uso", value=uso or "", key=f"edit_uso_{receta_id}")
            if st.button("Guardar cambios", key=f"save_receta_{receta_id}"):
                nuevo_cliente_id = cliente_dict[nuevo_cliente_nombre]
                cursor.execute(
                    "UPDATE recetas SET nombre=?, cliente_id=?, uso=?, linea=? WHERE id=?",
                    (nuevo_nombre, nuevo_cliente_id, nuevo_uso, nuevo_linea_nombre, receta_id)
                )
                conn.commit()
                st.success("Receta actualizada.")
                st.rerun()

        # Eliminación de receta
        if st.button("Eliminar receta", key=f"del_receta_{receta_id}"):
            cursor.execute("DELETE FROM receta_ingredientes WHERE receta_id=?", (receta_id,))
            cursor.execute("DELETE FROM recetas WHERE id=?", (receta_id,))
            conn.commit()
            st.warning("Receta eliminada.")
            st.rerun()

        # --- Gestión de ingredientes ---
        st.markdown("### Ingredientes de la receta")
        cursor.execute("""
            SELECT ri.id, mp.nombre, ri.cantidad, ri.unidad
            FROM receta_ingredientes ri
            JOIN materias_primas mp ON ri.materia_prima_id = mp.id
            WHERE ri.receta_id=?
        """, (receta_id,))
        ingredientes = cursor.fetchall()
        for ing_id, mp_nombre, cantidad, unidad in ingredientes:
            col1, col2, col3, col4 = st.columns([3,2,2,2])
            with col1: st.write(mp_nombre)
            with col2: st.write(cantidad)
            with col3: st.write(unidad)
            with col4:
                if st.button("Eliminar", key=f"del_ing_{ing_id}"):
                    cursor.execute("DELETE FROM receta_ingredientes WHERE id=?", (ing_id,))
                    conn.commit()
                    st.warning("Ingrediente eliminado.")
                    st.rerun()

        # --- Alta de ingrediente ---
        st.markdown("#### Agregar ingrediente a la receta")
        mp_sel = st.selectbox("Materia prima", list(mp_dict.keys()), key=f"mp_sel_{receta_id}")
        mp_id = mp_dict[mp_sel] if mp_sel else None
        cantidad = st.number_input("Cantidad", min_value=0.0, step=0.01, key=f"cant_{receta_id}")
        unidad = st.text_input("Unidad", value="", key=f"unidad_{receta_id}")
        if st.button("Agregar ingrediente", key=f"add_ing_{receta_id}"):
            if mp_id and cantidad > 0 and unidad:
                cursor.execute(
                    "INSERT INTO receta_ingredientes (receta_id, materia_prima_id, cantidad, unidad) VALUES (?, ?, ?, ?)",
                    (receta_id, mp_id, cantidad, unidad)
                )
                conn.commit()
                st.success("Ingrediente agregado.")
                st.rerun()
            else:
                st.warning("Todos los campos son obligatorios para el ingrediente.")

    conn.close()
