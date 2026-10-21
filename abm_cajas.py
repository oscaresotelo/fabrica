import sqlite3
import pandas as pd
import streamlit as st

DB_FILE = "minerva.db"

def get_productos():
    with sqlite3.connect(DB_FILE) as conn:
        return [row[0] for row in conn.execute("SELECT nombre FROM productos ORDER BY nombre")]

def get_lineas():
    with sqlite3.connect(DB_FILE) as conn:
        return [row[0] for row in conn.execute("SELECT nombre FROM lineas ORDER BY nombre")]

def get_cajas():
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql(
            "SELECT id, producto, linea, unidades_por_caja, descripcion FROM tipo_cajas ORDER BY producto, linea, unidades_por_caja",
            conn
        )

def add_caja(producto, linea, unidades_por_caja, descripcion):
    with sqlite3.connect(DB_FILE) as conn:
        exists = conn.execute(
            "SELECT count(*) FROM tipo_cajas WHERE producto=? AND linea=? AND unidades_por_caja=?",
            (producto, linea, unidades_por_caja)
        ).fetchone()[0]
        if exists:
            return False, "Ya existe una caja con esos datos"
        conn.execute(
            "INSERT INTO tipo_cajas (producto, linea, unidades_por_caja, descripcion) VALUES (?, ?, ?, ?)",
            (producto, linea, unidades_por_caja, descripcion)
        )
        conn.commit()
        return True, "Caja agregada correctamente"

def update_caja(id, producto, linea, unidades_por_caja, descripcion):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "UPDATE tipo_cajas SET producto=?, linea=?, unidades_por_caja=?, descripcion=? WHERE id=?",
            (producto, linea, unidades_por_caja, descripcion, id)
        )
        conn.commit()
        return True, "Caja editada correctamente"

def delete_caja(id):
    with sqlite3.connect(DB_FILE) as conn:
        m = conn.execute(
            "SELECT count(*) FROM movimientos_cajas WHERE tipo_caja=(SELECT descripcion FROM tipo_cajas WHERE id=?)",
            (id,)
        ).fetchone()[0]
        if m > 0:
            return False, "No puede eliminar una caja si tiene movimientos asociados."
        s = conn.execute(
            "SELECT count(*) FROM stock_cajas WHERE tipo_caja_id=? AND cantidad_actual>0",
            (id,)
        ).fetchone()[0]
        if s > 0:
            return False, "No puede eliminar una caja con stock actual."
        conn.execute("DELETE FROM tipo_cajas WHERE id=?", (id,))
        conn.commit()
        return True, "Caja eliminada correctamente"

def abm_cajas():
    st.title("ABM de Tipos de Cajas")
    st.markdown("Gestione el catálogo maestro de cajas de productos.")

    productos = get_productos()
    lineas = get_lineas()
    cajas = get_cajas()

    # --- Buscador ---
    st.markdown("#### Buscar caja para editar o eliminar")
    texto_busqueda = st.text_input("Buscar por producto, línea o descripción:")

    if texto_busqueda:
        df_filtrado = cajas[
            cajas.apply(lambda x: texto_busqueda.lower() in str(x['producto']).lower() 
                                    or texto_busqueda.lower() in str(x['linea']).lower() 
                                    or texto_busqueda.lower() in str(x['descripcion']).lower(), axis=1)
        ]
    else:
        df_filtrado = cajas

    # --- DataFrame en expander ---
    with st.expander("📦 Ver listado de cajas existentes", expanded=False):
        st.dataframe(
            df_filtrado,
            hide_index=True,
            use_container_width=True,
            height=400
        )

    # --- Alta de cajas ---
    with st.expander("➕ Agregar nuevo tipo de caja"):
        with st.form("add_caja_form"):
            producto = st.selectbox("Producto", productos)
            linea = st.selectbox("Línea", lineas)
            unidades = st.number_input("Unidades por caja", min_value=1, value=12)
            descripcion = st.text_input("Descripción")
            submitted = st.form_submit_button("Agregar")
            if submitted:
                ok, msg = add_caja(producto, linea, unidades, descripcion)
                st.success(msg) if ok else st.error(msg)
                st.experimental_rerun()

    # --- Edición y eliminación con buscador ---
    st.markdown("### Editar o eliminar caja (use el buscador)")
    if df_filtrado.empty:
        st.info("No hay cajas que coincidan con la búsqueda.")
    else:
        for idx, row in df_filtrado.iterrows():
            with st.expander(f"Editar caja: {row['descripcion']} ({row['producto']} · {row['linea']})"):
                producto_sel = st.selectbox("Producto", productos, 
                                            index=productos.index(row['producto']) if row['producto'] in productos else 0, key=f"prod_{row['id']}")
                linea_sel = st.selectbox("Línea", lineas, 
                                         index=lineas.index(row['linea']) if row['linea'] in lineas else 0, key=f"linea_{row['id']}")
                unidades = st.number_input("Unidades por caja", min_value=1, value=row['unidades_por_caja'], key=f"unid_{row['id']}")
                descripcion = st.text_input("Descripción", value=row['descripcion'], key=f"desc_{row['id']}")
                cols = st.columns([1,1])
                if cols[0].button("Guardar cambios", key=f"save_{row['id']}"):
                    ok, msg = update_caja(row['id'], producto_sel, linea_sel, unidades, descripcion)
                    st.success(msg) if ok else st.error(msg)
                    st.experimental_rerun()
                if cols[1].button("Eliminar", key=f"del_{row['id']}"):
                    ok, msg = delete_caja(row['id'])
                    st.success(msg) if ok else st.error(msg)
                    st.experimental_rerun()
