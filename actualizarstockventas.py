import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# =================================================================================================
# CONFIGURACIÓN DE BASE DE DATOS
# =================================================================================================
DB_PATH = "minerva.db" 
LOTE_POR_DEFECTO = 'SIN_LOTE' 

def get_connection():
    """Establece la conexión a la base de datos SQLite y configura el row_factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_df(query, params=()):
    """Ejecuta una consulta SQL y devuelve un DataFrame de pandas."""
    conn = get_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.error(f"Error en la consulta de datos. Detalle: {e}")
        st.code(query)
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

@st.cache_data
def fetch_productos():
    """Obtiene la lista de productos (recetas)."""
    return fetch_df("SELECT id, nombre FROM recetas ORDER BY nombre")

@st.cache_data
def fetch_clientes():
    """Obtiene la lista de clientes."""
    return fetch_df("SELECT id, nombre FROM clientes ORDER BY nombre")

# ----------------- FUNCIÓN DE ASOCIACIÓN CORREGIDA -----------------

def fetch_cliente_dueno_por_receta(receta_id):
    """Obtiene el nombre del cliente asociado a la receta, usando la columna 'cliente_id'."""
    if not receta_id:
        return None
    query = """
    SELECT c.nombre
    FROM recetas r
    JOIN clientes c ON c.id = r.cliente_id 
    WHERE r.id = ?
    """
    df = fetch_df(query, params=(receta_id,))
    return df['nombre'].iloc[0] if not df.empty else None

# ----------------- FUNCIONES DE FILTRADO Y STOCK -----------------

def fetch_envases_asociados(receta_id):
    """Obtiene la lista de envases asociados a una receta a través de la tabla 'productos'."""
    if not receta_id:
        return pd.DataFrame()
    query = """
    SELECT 
        e.id, 
        e.descripcion || ' (' || e.capacidad_litros || ' L)' AS detalle 
    FROM envases e
    JOIN productos pr ON pr.envase_id = e.id
    WHERE pr.id_receta = ? 
    ORDER BY detalle
    """
    return fetch_df(query, params=(receta_id,))

def fetch_total_stock_producto(receta_id):
    """Calcula el stock total disponible para un producto (receta)."""
    if not receta_id:
        return 0
    query = "SELECT SUM(cantidad) AS total_stock FROM stock_productos_envasados WHERE receta_id = ?"
    df = fetch_df(query, params=(receta_id,))
    return int(df['total_stock'].iloc[0]) if not df.empty and df['total_stock'].iloc[0] is not None else 0

def fetch_stock_por_envase(receta_id, envase_id):
    """Calcula el stock disponible para una combinación específica de producto y envase."""
    if not receta_id or not envase_id:
        return 0
    query = "SELECT SUM(cantidad) AS stock_envase FROM stock_productos_envasados WHERE receta_id = ? AND envase_id = ?"
    df = fetch_df(query, params=(receta_id, envase_id))
    return int(df['stock_envase'].iloc[0]) if not df.empty and df['stock_envase'].iloc[0] is not None else 0

# =================================================================================================
# LÓGICA TRANSACCIONAL: MOVIMIENTO DE STOCK (INGRESO Y EGRESO)
# =================================================================================================

def registrar_movimiento_stock_transaccional(receta_id, envase_id, cliente_id, cantidad_mov, observacion, tipo_movimiento):
    """
    Función transaccional para SUMAR o RESTAR la cantidad al stock existente.
    """
    conn = get_connection()
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S") 

    # Definir el impacto (positivo para ingreso, negativo para egreso)
    cantidad_impacto = cantidad_mov if tipo_movimiento == 'Ingreso' else -cantidad_mov

    try:
        # 1. Buscar stock existente
        cursor.execute("""
            SELECT id, cantidad FROM stock_productos_envasados 
            WHERE receta_id = ? AND envase_id = ? AND cliente_id = ? AND lote = ?
        """, (receta_id, envase_id, cliente_id, LOTE_POR_DEFECTO))
        
        stock_existente = cursor.fetchone()
        
        # VALIDACIÓN DE STOCK PARA EGRESO
        if tipo_movimiento == 'Egreso':
            cant_actual = stock_existente['cantidad'] if stock_existente else 0
            if cant_actual < cantidad_mov:
                return False, f"❌ Stock insuficiente. Solo hay **{cant_actual}** unidades disponibles."

        if stock_existente:
            # 2. Actualizar stock (Suma o Resta según cantidad_impacto)
            stock_id = stock_existente['id']
            cursor.execute("UPDATE stock_productos_envasados SET cantidad = cantidad + ? WHERE id = ?", (cantidad_impacto, stock_id))
            accion = "Actualizado"
        else:
            # 3. Crear nuevo (Solo si es Ingreso, porque Egreso ya validó arriba)
            cursor.execute("""
                INSERT INTO stock_productos_envasados (receta_id, envase_id, cliente_id, lote, cantidad, fecha_ingreso)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (receta_id, envase_id, cliente_id, LOTE_POR_DEFECTO, cantidad_impacto, fecha_actual)) 
            stock_id = cursor.lastrowid
            accion = "Creado"
        
        # 4. Registrar Movimiento Histórico (Se guarda la cantidad positiva pero con el tipo correcto)
        cursor.execute("""
            INSERT INTO movimientos_productos_envasados (stock_id, fecha, cantidad, tipo_movimiento, observacion)
            VALUES (?, ?, ?, ?, ?)
        """, (stock_id, fecha_actual, cantidad_mov, tipo_movimiento, observacion))
        
        conn.commit()
        return True, f"Stock {accion} correctamente. {tipo_movimiento} de **{cantidad_mov}** unidades registrado."

    except Exception as e:
        conn.rollback()
        return False, f"❌ Error en la transacción: {e}"
    finally:
        conn.close()

# =================================================================================================
# INTERFAZ STREAMLIT
# =================================================================================================

def app_stock_ingreso():
    st.set_page_config(layout="wide")
    st.title("Gestión de Stock de Productos Envasados 📦↕️")
    st.markdown("---")

    productos_df = fetch_productos()
    clientes_df = fetch_clientes()

    if productos_df.empty or clientes_df.empty:
        st.error("No se pudo cargar la lista de Productos o Clientes.")
        return

    prod_map = {row['nombre']: row['id'] for _, row in productos_df.iterrows()}
    cliente_map = {row['nombre']: row['id'] for _, row in clientes_df.iterrows()}
    cliente_options = list(cliente_map.keys())

    # --- 1. SELECCIÓN DE PRODUCTO Y STOCK ---
    col1, col2 = st.columns([2, 1])
    
    with col1:
        producto_nombre = st.selectbox("1. Receta (Producto)", options=list(prod_map.keys()), key='ingreso_producto_select')
        receta_id = prod_map.get(producto_nombre)
        st.metric("Stock Total del Producto", f"{fetch_total_stock_producto(receta_id):,} unidades")

    with col2:
        envases_df = fetch_envases_asociados(receta_id)
        envase_map = {row['detalle']: row['id'] for _, row in envases_df.iterrows()} if not envases_df.empty else {}
        envase_detalle = st.selectbox("2. Envase Asociado", options=list(envase_map.keys()), key='ingreso_envase_select', disabled=envases_df.empty)
        envase_id = envase_map.get(envase_detalle)
        st.metric("Stock Actual de este Envase", f"{fetch_stock_por_envase(receta_id, envase_id):,} unidades")

    default_client_name = fetch_cliente_dueno_por_receta(receta_id)
    default_index = cliente_options.index(default_client_name) if default_client_name in cliente_options else 0

    st.markdown("---")
    st.subheader("Detalles de la Operación")

    # --- 2. FORMULARIO ---
    with st.form("form_gestion_stock"):
        st.session_state['trans_receta_id'] = receta_id
        st.session_state['trans_envase_id'] = envase_id

        # Agregamos selector de TIPO DE MOVIMIENTO
        col_tipo, col_cli, col_qty = st.columns([1, 2, 1])
        
        with col_tipo:
            tipo_mov = st.radio("Operación", ["Ingreso", "Egreso"], key='tipo_mov_radio')

        with col_cli:
            cliente_nombre = st.selectbox("3. Stock para Cliente (Dueño)", options=cliente_options, index=default_index, key='ingreso_cliente_select')
            cliente_id = cliente_map.get(cliente_nombre)
            
        with col_qty:
            cantidad_input = st.number_input("4. Cantidad", min_value=1, value=1, step=1, key='ingreso_qty_input')
            
        observacion = st.text_area("Observación", value=f"{tipo_mov} manual de stock.", key='ingreso_obs_input')
            
        submitted = st.form_submit_button(f"✅ Registrar {tipo_mov}", type="primary", use_container_width=True)

        if submitted:
            final_receta_id = st.session_state.get('trans_receta_id')
            final_envase_id = st.session_state.get('trans_envase_id')

            if not final_envase_id:
                st.error("Debe seleccionar un envase.")
            else:
                # Llamamos a la nueva lógica que permite Egreso
                success, message = registrar_movimiento_stock_transaccional(
                    final_receta_id, final_envase_id, cliente_id, cantidad_input, observacion.strip(), tipo_mov
                )
                
                if success:
                    st.success(message)
                    st.cache_data.clear() 
                    st.rerun()
                else:
                    st.error(message)

if __name__ == "__main__":
    app_stock_ingreso()