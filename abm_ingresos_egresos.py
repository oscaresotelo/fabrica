import streamlit as st
import sqlite3
import pandas as pd

# =================================================================================================
# CONFIG
# =================================================================================================
DB_PATH = "minerva.db"
TIPOS_VALIDOS = ["INGRESO", "EGRESO"]

# =================================================================================================
# UTILIDADES DB
# =================================================================================================
def get_connection():
    """Establece la conexión a la base de datos."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_df(query, params=()):
    """Ejecuta una consulta SELECT y devuelve los resultados como un DataFrame de Pandas."""
    conn = get_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
    except sqlite3.Error as e:
        st.error(f"Error al ejecutar la consulta: {e}")
        return pd.DataFrame()
    finally:
        conn.close()
    return df

# =================================================================================================
# LÓGICA ABM
# =================================================================================================

def get_all_categorias():
    """Recupera todas las categorías de imputación."""
    query = "SELECT id, nombre, tipo FROM categorias_imputacion ORDER BY tipo, nombre"
    return fetch_df(query)

def create_categoria(nombre, tipo):
    """Inserta una nueva categoría."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO categorias_imputacion (nombre, tipo) VALUES (?, ?)",
            (nombre, tipo)
        )
        conn.commit()
        return True, "Categoría creada con éxito."
    except sqlite3.IntegrityError:
        return False, f"Error: Ya existe una categoría con el nombre '{nombre}'."
    except sqlite3.Error as e:
        return False, f"Error DB al crear: {e}"
    finally:
        conn.close()

def update_categoria(categoria_id, nombre, tipo):
    """Actualiza una categoría existente."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE categorias_imputacion SET nombre = ?, tipo = ? WHERE id = ?",
            (nombre, tipo, categoria_id)
        )
        conn.commit()
        if conn.execute("SELECT changes()").fetchone()[0] == 0:
            return False, f"No se encontró la categoría con ID {categoria_id} o no hubo cambios."
        return True, "Categoría actualizada con éxito."
    except sqlite3.IntegrityError:
        return False, f"Ya existe otra categoría con el nombre '{nombre}'."
    except sqlite3.Error as e:
        return False, f"Error DB al actualizar: {e}"
    finally:
        conn.close()

def delete_categoria(categoria_id):
    """Elimina una categoría por ID."""
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM imputaciones_pago WHERE categoria_imputacion_id = ?", (categoria_id,))
        count = cursor.fetchone()[0]

        if count > 0:
            return False, f"No se puede eliminar. Existen {count} registros dependientes en 'imputaciones_pago'."

        conn.execute("DELETE FROM categorias_imputacion WHERE id = ?", (categoria_id,))
        conn.commit()
        return True, "Categoría eliminada con éxito."
    except sqlite3.Error as e:
        return False, f"Error DB al eliminar: {e}"
    finally:
        conn.close()

# =================================================================================================
# INTERFAZ DE STREAMLIT (VISTAS)
# =================================================================================================

def mostrar_formulario_crear(categorias_df):
    """Formulario para dar de alta una nueva categoría."""
    st.subheader("➕ Crear Nueva Categoría")
    
    with st.form("form_crear_categoria", clear_on_submit=True):
        nombre = st.text_input("Nombre de la Categoría:", key="new_nombre").strip()
        tipo = st.selectbox("Tipo:", TIPOS_VALIDOS, key="new_tipo")
        
        submitted = st.form_submit_button("Guardar Categoría")
        
        if submitted:
            if not nombre:
                st.error("El nombre de la categoría no puede estar vacío.")
            elif nombre in categorias_df['nombre'].tolist():
                st.error(f"Ya existe una categoría con el nombre '{nombre}'.")
            else:
                success, message = create_categoria(nombre, tipo)
                if success:
                    st.success(f"✅ {message}")
                    st.rerun()
                else:
                    st.error(f"❌ {message}")

def mostrar_listado_y_edicion(categorias_df):
    """Muestra la tabla de categorías y permite edición/eliminación."""
    st.subheader("📋 Listado y Gestión de Categorías")
    
    if categorias_df.empty:
        st.info("No hay categorías de imputación registradas.")
        return

    edited_df = st.data_editor(
        categorias_df,
        column_config={
            "id": st.column_config.Column("ID", disabled=True),
            "nombre": st.column_config.TextColumn("Nombre", required=True),
            "tipo": st.column_config.SelectboxColumn(
                "Tipo",
                options=TIPOS_VALIDOS,
                required=True
            ),
        },
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        key="categorias_data_editor"
    )

    if st.button("Guardar Cambios Editados", type="primary", use_container_width=True):
        updated = 0
        changes = st.session_state.categorias_data_editor.get("edited_rows")

        if changes:
            for index, row_data in changes.items():
                original_row = categorias_df.iloc[index].to_dict()
                categoria_id = original_row['id']
                
                new_nombre = row_data.get('nombre', original_row['nombre'])
                new_tipo = row_data.get('tipo', original_row['tipo'])

                if new_nombre != original_row['nombre'] or new_tipo != original_row['tipo']:
                    success, message = update_categoria(categoria_id, new_nombre, new_tipo)
                    if success:
                        updated += 1
                    else:
                        st.error(f"Error al actualizar la categoría ID {categoria_id}: {message}")
            
            if updated > 0:
                st.success(f"✅ {updated} categorías actualizadas con éxito.")
                st.rerun()

    st.markdown("---")

    st.subheader("🗑️ Eliminar Categoría")
    
    opciones_eliminar = dict(zip(
        categorias_df['nombre'] + " (" + categorias_df['tipo'] + ")",
        categorias_df['id']
    ))
    
    categoria_a_eliminar_display = st.selectbox(
        "Seleccione la categoría a eliminar:",
        list(opciones_eliminar.keys()),
        key="delete_select"
    )
    
    categoria_id_eliminar = opciones_eliminar.get(categoria_a_eliminar_display)
    
    if categoria_id_eliminar:
        if st.button(f"Confirmar Eliminación de {categoria_a_eliminar_display}", help="Esta acción es irreversible."):
            success, message = delete_categoria(categoria_id_eliminar)
            if success:
                st.success(f"✅ {message}")
                st.rerun()
            else:
                st.error(f"❌ {message}")

# =================================================================================================
# FUNCIÓN PRINCIPAL REUTILIZABLE (Coincide con el nombre del archivo)
# =================================================================================================

def abm_ingresos_egresos():
    """Función principal que es llamada desde app.py o módulos principales."""
    st.title("Administración de Categorías de Imputación (ABM)")
    st.markdown("Las categorías se utilizan para clasificar el flujo de **INGRESO** y **EGRESO** de fondos.")
    st.markdown("---")

    categorias_df = get_all_categorias()

    col1, col2 = st.columns([1, 2])
    
    with col1:
        mostrar_formulario_crear(categorias_df)
    
    with col2:
        mostrar_listado_y_edicion(categorias_df)

# =================================================================================================
# SI SE EJECUTA DIRECTAMENTE
# =================================================================================================

if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="ABM Categorías de Imputación")
    abm_ingresos_egresos()