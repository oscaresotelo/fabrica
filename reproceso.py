import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from io import BytesIO

DB_FILE = "minerva.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_data(query, params=()):
    with get_connection() as conn:
        df = pd.read_sql_query(query, conn, params=params)
    return df

def obtener_stock_productos_envasados():
    query = """
    SELECT 
        spe.id,
        c.nombre AS cliente,
        r.nombre AS receta,
        e.descripcion AS envase,
        spe.lote,
        spe.cantidad
    FROM stock_productos_envasados spe
    JOIN clientes c ON spe.cliente_id = c.id
    JOIN recetas r ON spe.receta_id = r.id
    JOIN envases e ON spe.envase_id = e.id
    WHERE spe.cantidad > 0
    ORDER BY c.nombre, r.nombre, e.descripcion, spe.lote
    """
    df = fetch_data(query)
    return df

def obtener_producciones_pendientes():
    query = """
    SELECT 
        p.id as produccion_id,
        p.lote,
        r.nombre AS receta
    FROM producciones p
    JOIN pedidos_produccion pp ON p.pedido_id = pp.id
    JOIN recetas r ON pp.receta_id = r.id
    WHERE p.estado = 'producido'
    """
    df = fetch_data(query)
    return df

def registrar_reproceso(fecha, stock_id, cantidad, produccion_id, observacion):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Obtener info del stock
        cursor.execute("SELECT * FROM stock_productos_envasados WHERE id = ?", (stock_id,))
        stock_info = cursor.fetchone()
        if stock_info is None:
            raise ValueError(f"No existe stock con ID {stock_id}")
        # Verificar si la cantidad de stock a regresar existe
        if stock_info['cantidad'] < cantidad:
             raise ValueError(f"No hay suficiente stock disponible para reprocesar. Stock disponible: {stock_info['cantidad']}")
        # Insertar reproceso
        cursor.execute("""
                INSERT INTO reprocesos_productos_envasados (fecha, stock_id, cantidad, produccion_id, observacion)
                VALUES (?, ?, ?, ?, ?)
            """, (fecha, stock_id, cantidad, produccion_id, observacion))

        # restar stock
        stock_actual = stock_info['cantidad']
        nuevo_stock = stock_actual - cantidad
        if nuevo_stock < 0:
            nuevo_stock = 0  # Evitar stock negativo
        cursor.execute("UPDATE stock_productos_envasados SET cantidad = ? WHERE id = ?", (nuevo_stock, stock_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        st.error(f"Error al registrar el reproceso: {e}")
        return False
    finally:
        conn.close()
    st.success("Reproceso registrado exitosamente.")
    return True


def modulo_reproceso_productos():
    st.title("🔄 Reproceso de Productos Envasados")
    productos_df = obtener_stock_productos_envasados()
    if productos_df.empty:
        st.info("No hay productos envasados disponibles para reprocesar.")
    else:
        productos_str = productos_df.apply(
            lambda r: f"Producto: {r['receta']} | Cliente: {r['cliente']} | Envase: {r['envase']} | Lote: {r['lote']} | Cantidad: {r['cantidad']}",
            axis=1
        ).tolist()

        productos_id_map = {
        f"Producto: {r['receta']} | Cliente: {r['cliente']} | Envase: {r['envase']} | Lote: {r['lote']} | Cantidad: {r['cantidad']}": r['id']
        for i, r in productos_df.iterrows()
        }

        selected_stock_string = st.selectbox("Seleccionar producto envasado para reprocesar", options=list(productos_id_map.keys()))
        stock_id = productos_id_map[selected_stock_string]
        stock_seleccionado = productos_df[productos_df['id'] == stock_id].iloc[0]

        st.info(f"Producto seleccionado: {stock_seleccionado['receta']} (Cliente: {stock_seleccionado['cliente']}, Envase: {stock_seleccionado['envase']}, Lote: {stock_seleccionado['lote']}).")
        cantidad_maxima_reproceso = stock_seleccionado["cantidad"]
        st.info(f"Cantidad máxima a reprocesar de este lote: {cantidad_maxima_reproceso} unidades.")

        cantidad_reproceso = st.number_input(
            "Cantidad a reprocesar",
            min_value=1,
            max_value=int(cantidad_maxima_reproceso),
            value=1,
            step=1
        )
        if cantidad_reproceso > 0:
                producciones_df = obtener_producciones_pendientes()
                producciones_display = producciones_df.apply(
                    lambda x: f"{x['receta']} (Lote: {x['lote']})", axis=1
                ).tolist()

        produccion_seleccionada = st.selectbox(
            "Seleccionar producción para reincorporar",
            options=producciones_display
        )

        id_produccion_seleccionada = producciones_df.loc[producciones_df.apply(
                lambda x: f"{x['receta']} (Lote: {x['lote']})" == produccion_seleccionada, axis=1
            ).idxmax(), "produccion_id"]
        observacion = st.text_area("Observaciones sobre el reproceso (opcional)")
        if st.button("Confirmar reproceso"):
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if registrar_reproceso(fecha, stock_id, cantidad_reproceso, id_produccion_seleccionada, observacion):
                st.success("Reproceso registrado con éxito.")
modulo_reproceso_productos()