import streamlit as st
import sqlite3
import pandas as pd

DB_FILE = "minerva.db"

# --- Funciones de consulta ---
def get_combinados_para_editar():
    """Obtiene todos los colorantes combinados y Serum, sin filtrar por existencia en composicion_colorantes."""
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query("""
            SELECT id, nombre
            FROM materias_primas
            WHERE nombre LIKE 'Colorante%' OR TRIM(nombre)='SERUM'
            ORDER BY nombre
        """, conn)
        return df

def get_colorantes_primarios():
    """Obtiene todas las materias primas para ser usadas como primarias."""
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query("SELECT id, nombre FROM materias_primas ORDER BY nombre", conn)
        return df

def get_composicion(colorante_combinado_id):
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query("""
            SELECT cc.colorante_primario_id, mp.nombre, cc.proporcion
            FROM composicion_colorantes cc
            JOIN materias_primas mp ON cc.colorante_primario_id = mp.id
            WHERE cc.colorante_combinado_id = ?
        """, conn, params=(colorante_combinado_id,))
        return df

def add_composicion(colorante_combinado_id, colorante_primario_id, proporcion):
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        try:
            if colorante_primario_id == colorante_combinado_id:
                return False, "No se puede agregar un colorante a su propia composición."
            cur.execute("""
                INSERT INTO composicion_colorantes (colorante_combinado_id, colorante_primario_id, proporcion)
                VALUES (?, ?, ?)
            """, (colorante_combinado_id, colorante_primario_id, proporcion))
            conn.commit()
            return True, "Componente agregado correctamente."
        except sqlite3.IntegrityError:
            conn.rollback()
            return False, "Este componente ya existe en la composición."
        except Exception as e:
            conn.rollback()
            return False, f"Error al agregar componente: {e}"

def update_composicion(colorante_combinado_id, colorante_primario_id, proporcion):
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE composicion_colorantes
                SET proporcion = ?
                WHERE colorante_combinado_id = ? AND colorante_primario_id = ?
            """, (proporcion, colorante_combinado_id, colorante_primario_id))
            conn.commit()
            return True, "Proporción actualizada correctamente."
        except Exception as e:
            conn.rollback()
            return False, f"Error al actualizar la proporción: {e}"

def delete_composicion(colorante_combinado_id, colorante_primario_id):
    with sqlite3.connect(DB_FILE) as conn:
        try:
            conn.execute("""
                DELETE FROM composicion_colorantes
                WHERE colorante_combinado_id = ? AND colorante_primario_id = ?
            """, (colorante_combinado_id, colorante_primario_id))
            conn.commit()
            return True, "Componente eliminado correctamente."
        except Exception as e:
            conn.rollback()
            return False, f"Error al eliminar componente: {e}"

# --- Interfaz Streamlit ---
def abm_composicion_colorantes():
    st.title("Gestión de Composición de Colorantes / Serum")

    # Obtener colorantes y Serum
    colorantes_combinados_df = get_combinados_para_editar()
    colorantes_primarios_df = get_colorantes_primarios()

    if colorantes_combinados_df.empty or colorantes_primarios_df.empty:
        st.warning("No hay colorantes ni materias primas cargadas.")
        return

    colorantes_combinados = {c["nombre"].strip(): c["id"] for c in colorantes_combinados_df.to_dict('records')}
    colorantes_primarios = {c["nombre"].strip(): c["id"] for c in colorantes_primarios_df.to_dict('records')}

    # Selector principal (ahora Serum siempre aparece)
    st.markdown("#### Seleccionar colorante combinado o Serum")
    selected_combo_name = st.selectbox(
        "Colorante Combinado / Serum:",
        list(colorantes_combinados.keys()),
        key='main_selector'
    )
    selected_combo_id = colorantes_combinados[selected_combo_name]

    # Mostrar composición
    st.markdown("---")
    st.subheader(f"Composición actual de '{selected_combo_name}'")
    composicion_df = get_composicion(selected_combo_id)

    if composicion_df.empty:
        st.info("Este colorante combinado o Serum no tiene componentes definidos.")
    else:
        st.dataframe(composicion_df, hide_index=True)

    # Agregar componente
    st.markdown("---")
    with st.expander("➕ Agregar nuevo componente"):
        with st.form("add_componente_form"):
            colorante_primario_nombre = st.selectbox(
                "Seleccionar colorante primario:",
                list(colorantes_primarios.keys()),
                key='add_primario'
            )
            colorante_primario_id = colorantes_primarios[colorante_primario_nombre]
            proporcion = st.number_input("Proporción:", min_value=0.0, max_value=1.0, value=0.5, step=0.01, key='add_prop')

            submitted_add = st.form_submit_button("Agregar componente")
            if submitted_add:
                ok, msg = add_composicion(selected_combo_id, colorante_primario_id, proporcion)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
                st.experimental_rerun()

    # Modificar / eliminar componentes
    if not composicion_df.empty:
        st.markdown("---")
        st.subheader("⚙️ Modificar o Eliminar un componente")
        componentes_actuales = {row['nombre']: row['colorante_primario_id'] for index, row in composicion_df.iterrows()}
        colorante_sel = st.selectbox("Seleccionar componente:", list(componentes_actuales.keys()), key='update_selector')
        colorante_primario_id_mod = componentes_actuales[colorante_sel]
        initial_value = composicion_df.loc[composicion_df['nombre']==colorante_sel, 'proporcion'].iloc[0]

        col_mod, col_del = st.columns(2)
        with col_mod:
            nueva_proporcion = st.number_input("Nueva proporción:", min_value=0.0, max_value=1.0, value=initial_value, step=0.01, key='update_prop')
            if st.button("Actualizar proporción", key="update_button"):
                ok, msg = update_composicion(selected_combo_id, colorante_primario_id_mod, nueva_proporcion)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
                st.experimental_rerun()
        with col_del:
            if st.button("Eliminar componente", key="delete_button"):
                ok, msg = delete_composicion(selected_combo_id, colorante_primario_id_mod)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
                st.experimental_rerun()

if __name__ == "__main__":
    abm_composicion_colorantes()
