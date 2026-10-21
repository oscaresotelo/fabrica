import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# =================================================================================================
# LÓGICA DE BASE DE DATOS Y CONEXIÓN
# =================================================================================================
DB_PATH = "minerva.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def execute_query(query, params=()):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Error en la base de datos: {e}")
        return False
    finally:
        conn.close()

def get_productos_envasados():
    query = """
    SELECT
        spe.id,
        c.nombre AS cliente,
        r.nombre AS receta,
        e.descripcion AS envase,
        spe.cantidad,
        spe.lote
    FROM stock_productos_envasados spe
    LEFT JOIN clientes c ON spe.cliente_id = c.id
    LEFT JOIN recetas r ON spe.receta_id = r.id
    LEFT JOIN envases e ON spe.envase_id = e.id
    ORDER BY spe.fecha_ingreso DESC
    """
    df = pd.read_sql_query(query, get_connection())
    df['cliente'] = df['cliente'].fillna('Sin asignar')
    df['receta'] = df['receta'].fillna('No definida')
    df['envase'] = df['envase'].fillna('No definido')
    return df

def get_clientes_select():
    query = "SELECT id AS cliente_id, nombre AS cliente_nombre FROM clientes ORDER BY nombre"
    df = pd.read_sql_query(query, get_connection())
    return df

def get_recetas_select():
    query = "SELECT id AS receta_id, nombre AS receta_nombre FROM recetas ORDER BY nombre"
    df = pd.read_sql_query(query, get_connection())
    return df

@st.cache_data
def get_envases_by_receta(receta_id):
    query = """
    SELECT DISTINCT e.id AS envase_id, e.descripcion AS envase_descripcion
    FROM productos p
    JOIN envases e ON p.envase_id = e.id
    WHERE p.id_receta = ?
    ORDER BY e.descripcion
    """
    df = pd.read_sql_query(query, get_connection(), params=(receta_id,))
    return df

def actualizar_stock_producto(cliente_id, receta_id, envase_id, lote, cantidad_a_agregar):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, cantidad FROM stock_productos_envasados
        WHERE cliente_id = ? AND receta_id = ? AND envase_id = ? AND lote = ?
    """, (cliente_id, receta_id, envase_id, lote))

    existing_record = cursor.fetchone()

    if existing_record:
        query = """
            UPDATE stock_productos_envasados
            SET cantidad = cantidad + ?
            WHERE id = ?
        """
        success = execute_query(query, (cantidad_a_agregar, existing_record[0]))
        if success:
            st.success(f"Stock actualizado para el producto (Lote: {lote}). Cantidad añadida: {cantidad_a_agregar}.")
    else:
        query = """
            INSERT INTO stock_productos_envasados (cliente_id, receta_id, envase_id, lote, cantidad, fecha_ingreso)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        fecha_ingreso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        success = execute_query(query, (cliente_id, receta_id, envase_id, lote, cantidad_a_agregar, fecha_ingreso))
        if success:
            st.success(f"Nuevo producto envasado agregado al stock (Lote: {lote}). Cantidad: {cantidad_a_agregar}.")

    conn.close()
    return success

def get_precios_guardados():
    query = """
    SELECT
        c.nombre AS cliente,
        r.nombre AS receta,
        e.descripcion AS envase,
        ppe.precio_unitario,
        ppe.fecha_desde
    FROM precios_productos_envasados ppe
    LEFT JOIN clientes c ON ppe.cliente_id = c.id
    LEFT JOIN productos p ON ppe.producto_id = p.id
    LEFT JOIN recetas r ON p.id_receta = r.id
    LEFT JOIN envases e ON p.envase_id = e.id
    ORDER BY ppe.fecha_desde DESC, c.nombre
    """
    df = pd.read_sql_query(query, get_connection())
    return df

def get_all_products():
    query = """
    SELECT
        p.id,
        p.nombre,
        c.nombre AS cliente,
        l.nombre AS linea,
        e.descripcion AS envase,
        r.nombre AS receta
    FROM productos p
    LEFT JOIN clientes c ON p.cliente_id = c.id
    LEFT JOIN lineas l ON p.linea_id = l.id
    LEFT JOIN envases e ON p.envase_id = e.id
    LEFT JOIN recetas r ON p.id_receta = r.id
    ORDER BY p.nombre
    """
    df = pd.read_sql_query(query, get_connection())
    return df

def get_producto_id(receta_id, envase_id):
    query = "SELECT id FROM productos WHERE id_receta = ? AND envase_id = ?"
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, (receta_id, envase_id))
        result = cursor.fetchone()
        return result['id'] if result else None
    except sqlite3.Error as e:
        st.error(f"Error al buscar el producto: {e}")
        return None
    finally:
        conn.close()

def set_precio(cliente_id, producto_id, envase_id, nuevo_precio):
    conn = get_connection()
    fecha_actual = datetime.now().strftime("%Y-%m-%d")
    query = """
    INSERT INTO precios_productos_envasados (cliente_id, producto_id, envase_id, precio_unitario, fecha_desde)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(cliente_id, producto_id, envase_id, fecha_desde) DO UPDATE SET
        precio_unitario = excluded.precio_unitario
    """
    try:
        cursor = conn.cursor()
        cursor.execute(query, (cliente_id, producto_id, envase_id, nuevo_precio, fecha_actual))
        conn.commit()
        st.success("Precio actualizado con éxito.")
        return True
    except sqlite3.Error as e:
        st.error(f"Error al actualizar el precio: {e}")
        return False
    finally:
        conn.close()

# =================================================================================================
# INTERFAZ DE STREAMLIT
# =================================================================================================
st.set_page_config(page_title="Carga de Stock y Precios", layout="wide")
st.title("Carga de Stock y Precios")
st.markdown("---")

tab1, tab2, tab3 = st.tabs(["🛒 Cargar Stock", "💲 Gestionar Precios", "📊 Ver Productos"])

# ---------------------- TAB 1 ----------------------
with tab1:
    st.subheader("Añadir Stock a un Producto Existente")

    clientes_df = get_clientes_select()
    recetas_df = get_recetas_select()

    if clientes_df.empty or recetas_df.empty:
        st.warning("No hay clientes o recetas en la base de datos. Por favor, agregue primero.")
    else:
        selected_cliente_nombre = st.selectbox(
            "Selecciona el Cliente",
            options=clientes_df['cliente_nombre'].tolist(),
            key='cliente_select_tab1'
        )
        cliente_id = clientes_df[clientes_df['cliente_nombre'] == selected_cliente_nombre]['cliente_id'].iloc[0]
        st.write(f"DEBUG Cliente seleccionado tab1: {selected_cliente_nombre} (ID: {cliente_id})")

        selected_receta_nombre = st.selectbox(
            "Selecciona la Receta",
            options=recetas_df['receta_nombre'].tolist(),
            key='receta_select_tab1'
        )
        receta_row = recetas_df[recetas_df['receta_nombre'] == selected_receta_nombre]
        if receta_row.empty:
            st.error(f"No se encontró la receta '{selected_receta_nombre}'.")
            receta_id = None
        else:
            receta_id = int(receta_row['receta_id'].iloc[0])

        envase_id = None
        selected_envase_descripcion = None

        if receta_id is not None:
            envases_df = get_envases_by_receta(receta_id)
            if envases_df.empty:
                st.warning("No se encontraron envases asociados a esta receta.")
            else:
                envase_dict = dict(zip(envases_df['envase_descripcion'], envases_df['envase_id']))
                selected_envase_descripcion = st.selectbox(
                    "Selecciona el Envase",
                    options=list(envase_dict.keys()),
                    key='envase_select_tab1'
                )
                envase_id = envase_dict[selected_envase_descripcion]

        with st.form("form_carga_stock"):
            lote = st.text_input("Lote")
            cantidad_a_agregar = st.number_input("Cantidad a Agregar", min_value=1, step=1)
            submit_button = st.form_submit_button("Añadir Stock")

            if submit_button:
                if None in (cliente_id, receta_id, envase_id) or lote.strip() == "" or cantidad_a_agregar <= 0:
                    st.error("Por favor, complete todos los campos correctamente.")
                else:
                    st.write(f"DEBUG Guardando stock: cliente_id={cliente_id}, receta_id={receta_id}, envase_id={envase_id}, lote='{lote}', cantidad={cantidad_a_agregar}")
                    if actualizar_stock_producto(cliente_id, receta_id, envase_id, lote, cantidad_a_agregar):
                        st.rerun()

    st.markdown("---")
    st.subheader("Stock Actual de Productos Envasados")
    stock_df = get_productos_envasados()
    st.dataframe(stock_df, use_container_width=True)

# ---------------------- TAB 2 ----------------------
with tab2:
    st.subheader("Asignar Precios a Productos por Cliente")

    clientes_df = get_clientes_select()
    recetas_df = get_recetas_select()

    if clientes_df.empty or recetas_df.empty:
        st.warning("Asegúrese de que haya clientes y recetas en la base de datos.")
    else:
        selected_cliente_nombre = st.selectbox(
            "Selecciona el Cliente",
            options=clientes_df['cliente_nombre'].tolist(),
            key='cliente_select_tab2'
        )
        cliente_id = clientes_df[clientes_df['cliente_nombre'] == selected_cliente_nombre]['cliente_id'].iloc[0]
        st.write(f"DEBUG Cliente seleccionado tab2: {selected_cliente_nombre} (ID: {cliente_id})")

        selected_receta_nombre = st.selectbox(
            "Selecciona la Receta",
            options=recetas_df['receta_nombre'].tolist(),
            key='receta_select_tab2'
        )
        receta_row = recetas_df[recetas_df['receta_nombre'] == selected_receta_nombre]

        if receta_row.empty:
            st.error(f"Error: No se encontró la receta '{selected_receta_nombre}' en la base de datos.")
            receta_id = None
        else:
            receta_id = int(receta_row['receta_id'].iloc[0])
            st.info(f"Receta seleccionada: '{selected_receta_nombre}' (ID: {receta_id})")

        envase_id = None
        selected_envase_descripcion = None

        if receta_id is not None:
            envases_df = get_envases_by_receta(receta_id)

            if envases_df.empty:
                st.warning(f"No se encontraron envases asociados a la receta ID {receta_id}. Por favor, agregue productos con esta receta primero.")
            else:
                envase_dict = dict(zip(envases_df['envase_descripcion'], envases_df['envase_id']))
                selected_envase_descripcion = st.selectbox(
                    "Selecciona el Envase",
                    options=list(envase_dict.keys()),
                    key='envase_select_tab2'
                )
                envase_id = envase_dict[selected_envase_descripcion]

        with st.form("form_set_precio"):
            nuevo_precio = st.number_input("Nuevo Precio Unitario", min_value=0.0, step=0.01)
            submit_precio_button = st.form_submit_button("Guardar Precio")

            if submit_precio_button:
                if selected_cliente_nombre and selected_receta_nombre and selected_envase_descripcion and nuevo_precio >= 0:
                    producto_id = get_producto_id(receta_id, envase_id)

                    if producto_id is None:
                        st.error("Error: No se encontró un producto para la combinación de receta y envase seleccionados.")
                    else:
                        st.write(f"DEBUG Guardando precio: cliente_id={cliente_id}, producto_id={producto_id}, envase_id={envase_id}, precio={nuevo_precio}")
                        # Además de guardar precio, guardar stock con cantidad 0 y lote 'inicial' si no existe
                        if set_precio(cliente_id, producto_id, envase_id, nuevo_precio):
                            actualizar_stock_producto(cliente_id, receta_id, envase_id, "inicial", 0)
                            st.rerun()
                else:
                    st.error("Por favor, complete todos los campos.")

    st.markdown("---")
    st.subheader("Precios guardados")
    precios_df = get_precios_guardados()
    st.dataframe(precios_df, use_container_width=True)

# ---------------------- TAB 3 ----------------------
with tab3:
    st.subheader("Lista Completa de Productos (Maestro)")
    all_products_df = get_all_products()
    st.dataframe(all_products_df, use_container_width=True)
