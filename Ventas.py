import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import io
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

import base64
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle , Paragraph
from io import BytesIO
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer
from reportlab.lib.pagesizes import A4, landscape

# =================================================================================================
# FUNCIÓN DE UTILIDAD PARA MANEJO ROBUSTO DE NULOS (st-aggrid)
# =================================================================================================
def safe_str(val):
    """
    Convierte el valor a cadena, tratando NaN/None/cadenas 'None'/'nan' como '__NA__' 
    para asegurar la coincidencia en el filtrado de pandas vs. AgGrid.
    """
    if pd.isna(val) or val is None:
        return '__NA__'
        
    val_str = str(val).strip()
    if val_str.lower() in ('none', 'nan', ''):
        return '__NA__'
        
    return val_str

# =================================================================================================
# LÓGICA DE BASE DE DATOS Y CONEXIÓN
# =================================================================================================
DB_PATH = "minerva.db"

def get_connection():
    """Establece la conexión a la base de datos SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_df(query, params=()):
    """Ejecuta una consulta SQL y devuelve un DataFrame de pandas, manejando errores."""
    conn = get_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df
    except sqlite3.Error as e:
        conn.close()
        st.error(f"Error de base de datos al ejecutar consulta: {e}")
        st.code(query)
        return pd.DataFrame()

# =================================================================================================
# FUNCIÓN set_precio (y otras funciones de DB)
# =================================================================================================
def set_precio(cliente_id, producto_id, envase_id, nuevo_precio):
    """Actualiza el precio de un producto envasado para un cliente, garantizando unicidad en fecha_desde."""
    conn = get_connection()
    cursor = conn.cursor()
    
    fecha_hoy_solo_dia = datetime.now().strftime("%Y-%m-%d")
    fecha_y_hora_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
    
    # 1. Finalizar el precio anterior
    cursor.execute("""
        UPDATE precios_productos_envasados
        SET fecha_hasta = ?
        WHERE cliente_id = ? AND producto_id = ? AND envase_id = ?
          AND (fecha_hasta IS NULL OR fecha_hasta > ?)
    """, (fecha_hoy_solo_dia, cliente_id, producto_id, envase_id, fecha_hoy_solo_dia))
    
    # 2. Insertar el nuevo precio
    cursor.execute("""
        INSERT INTO precios_productos_envasados
        (cliente_id, producto_id, envase_id, precio_unitario, fecha_desde)
        VALUES (?, ?, ?, ?, ?)
    """, (cliente_id, producto_id, envase_id, nuevo_precio, fecha_y_hora_actual))
    
    conn.commit()
    conn.close()

def obtener_precio(cliente_id, producto_id, envase_id):
    """Obtiene el precio unitario actual de un producto para un cliente."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT precio_unitario
        FROM precios_productos_envasados
        WHERE cliente_id = ? AND producto_id = ? AND envase_id = ?
          AND (fecha_hasta IS NULL OR fecha_hasta > date('now'))
        ORDER BY fecha_desde DESC
        LIMIT 1
    """, (cliente_id, producto_id, envase_id))
    row = cursor.fetchone()
    conn.close()
    return row["precio_unitario"] if row else None

# --- FUNCIÓN registrar_venta (Soporta stock negativo/insuficiente de forma robusta) ---
def registrar_venta(cursor, stock_id, cantidad_vender, observacion, destino, numero_comprobante):
    """Registra una venta de stock y los movimientos asociados, y actualiza el stock (permite stock negativo)."""
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    bekim_id = 8
    
    # Intenta obtener información del stock_productos_envasados
    cursor.execute("""
        SELECT
            spe.cantidad,
            spe.cliente_id,
            spe.receta_id,
            spe.envase_id,
            spe.lote
        FROM stock_productos_envasados spe
        WHERE spe.id = ?
    """, (stock_id,))
    stock_info = cursor.fetchone()

    if stock_info:
        # Lógica para Stock Regular (Se permite stock negativo)
        cantidad_actual = stock_info["cantidad"]
        nueva_cantidad = cantidad_actual - cantidad_vender
        
        # Ejecuta la actualización en la base de datos (incluso si queda negativo)
        cursor.execute("""
            UPDATE stock_productos_envasados
            SET cantidad = ?
            WHERE id = ?
        """, (nueva_cantidad, stock_id))
        
    # Si no se encontró en stock_productos_envasados, busca en producciones (Bekim)
    else:
        cursor.execute("""
            SELECT
                prod.cantidad_real_litros AS cantidad_litros,
                pp.cliente_id
            FROM producciones prod
            JOIN pedidos_produccion pp ON prod.pedido_id = pp.id
            WHERE prod.id = ? AND pp.cliente_id = ?
        """, (stock_id, bekim_id))
        bekim_info = cursor.fetchone()

        if bekim_info is None:
            raise Exception("No existe el registro de stock o pedido de producción seleccionado.")

        cantidad_litros_actual = bekim_info["cantidad_litros"] 
        CAPACIDAD_TAMBOR = 200.0 # Se asume el tambor Bekim de 200L
        
        # Reducción de litros en la tabla producciones (permitiendo litros negativos)
        litros_a_reducir = cantidad_vender * CAPACIDAD_TAMBOR
        nueva_cantidad_litros = cantidad_litros_actual - litros_a_reducir
        
        # Reducir la cantidad de litros de la producción
        cursor.execute(
            "UPDATE producciones SET cantidad_real_litros = ? WHERE id = ?", 
            (nueva_cantidad_litros, stock_id)
        )
        
        # Si se agotó o es menor a cero el lote, cambiar el estado
        if nueva_cantidad_litros <= 1e-6:
            cursor.execute("UPDATE producciones SET estado = 'vendido' WHERE id = ?", (stock_id,))

    # Registrar el movimiento de salida para ambos casos
    cursor.execute("""
        INSERT INTO movimientos_productos_envasados
        (stock_id, fecha, cantidad, tipo_movimiento, destino, observacion, numero_comprobante)
        VALUES (?, ?, ?, 'Egreso', ?, ?, ?)
    """, (stock_id, fecha_hoy, cantidad_vender, destino, observacion, numero_comprobante))
    
def get_stock_df(cotizacion_dolar, bekim_price_mode, mostrar_sin_stock=False):
    """Obtiene un DataFrame con el stock de productos envasados disponible.
       Si mostrar_sin_stock es True, incluye registros con stock menor o igual a cero.
    """
    bekim_id = 8
    
    if bekim_price_mode == 'Precio en USD por Litro':
        price_multiplier = 200.0 
    else:
        price_multiplier = 1.0
    
    # Filtro dinámico de cantidad para Bekim
    condicion_bekim = "" if mostrar_sin_stock else "AND prod.cantidad_real_litros > 0 AND prod.estado = 'producido'"
    
    query_bekim = f"""
    WITH StockPrecio AS (
        SELECT
            prod.id AS stock_id,
            pp.cliente_id,
            c.nombre AS cliente,
            pp.receta_id,
            r.nombre AS receta,
            pr.envase_id,
            e.descripcion AS envase,
            e.capacidad_litros AS capacidad_litros,
            prod.lote,
            prod.cantidad_real_litros,
            pr.id AS producto_id,
            pr.nombre AS producto,
            l.nombre AS linea,
            (
                SELECT ppe.precio_unitario 
                FROM precios_productos_envasados ppe 
                WHERE ppe.cliente_id = {bekim_id} 
                  AND ppe.producto_id = pr.id 
                  AND ppe.envase_id = pr.envase_id
                  AND (ppe.fecha_hasta IS NULL OR ppe.fecha_hasta > DATE('now'))
                ORDER BY ppe.fecha_desde DESC LIMIT 1
            ) AS precio_usd_base
        FROM
            producciones prod
        JOIN pedidos_produccion pp ON prod.pedido_id = pp.id
        JOIN recetas r ON pp.receta_id = r.id
        JOIN productos pr ON pr.id_receta = r.id AND pr.cliente_id = pp.cliente_id
        JOIN envases e ON pr.envase_id = e.id
        LEFT JOIN clientes c ON pp.cliente_id = c.id
        LEFT JOIN lineas l ON pr.linea_id = l.id
        WHERE
            pp.cliente_id = {bekim_id}
            {condicion_bekim}
    )
    SELECT
        stock_id,
        cliente_id,
        cliente,
        receta_id,
        receta,
        envase_id,
        envase,
        capacidad_litros,
        lote,
        ROUND(cantidad_real_litros / 200.0) AS cantidad, 
        producto_id,
        producto,
        linea,
        precio_usd_base,
        (precio_usd_base * {price_multiplier} * ?) AS precio_total_ars_por_tambor
    FROM
        StockPrecio
    """
    
    # Filtro dinámico de cantidad para otros clientes
    condicion_otros = "" if mostrar_sin_stock else "spe.cantidad > 0 AND"
    
    query_otros = f"""
    SELECT
        spe.id AS stock_id,
        spe.cliente_id,
        c.nombre AS cliente,
        spe.receta_id,
        r.nombre AS receta,
        spe.envase_id,
        e.descripcion AS envase,
        e.capacidad_litros AS capacidad_litros,
        spe.lote AS lote,
        spe.cantidad AS cantidad,
        pr.id AS producto_id,
        pr.nombre AS producto,
        l.nombre AS linea,
        NULL AS precio_total_ars_por_tambor
    FROM
        stock_productos_envasados spe
    LEFT JOIN
        clientes c ON spe.cliente_id = c.id
    JOIN
        recetas r ON spe.receta_id = r.id
    JOIN
        envases e ON spe.envase_id = e.id
    JOIN
        productos pr ON pr.id_receta = r.id AND pr.envase_id = e.id AND (pr.cliente_id = spe.cliente_id OR pr.cliente_id IS NULL)
    JOIN
        lineas l ON pr.linea_id = l.id
    WHERE
        {condicion_otros} (spe.cliente_id IS NULL OR spe.cliente_id != ?)
    """
    
    df_bekim = fetch_df(query_bekim, [cotizacion_dolar])
    df_otros = fetch_df(query_otros, [bekim_id])
    
    if df_bekim.empty and df_otros.empty:
        return pd.DataFrame()
        
    df_stock = pd.concat([df_bekim, df_otros], ignore_index=True)
    return df_stock

def get_precios_filtrados(cliente_id=None, producto_id=None):
    """Obtiene los precios de productos envasados con filtros opcionales."""
    params = []
    query = """
    SELECT DISTINCT
        c.id AS cliente_id,
        p.id AS producto_id,
        e.id AS envase_id,
        c.nombre AS cliente,
        p.nombre AS producto,
        e.descripcion AS envase,
        COALESCE((
            SELECT pp.precio_unitario
            FROM precios_productos_envasados pp
            WHERE pp.cliente_id = c.id
              AND pp.producto_id = p.id
              AND pp.envase_id = e.id
              AND (pp.fecha_hasta IS NULL OR pp.fecha_hasta > DATE('now'))
            ORDER BY pp.fecha_desde DESC
            LIMIT 1
        ), 0) AS precio_unitario
    FROM clientes c
    JOIN productos p ON p.cliente_id = c.id
    JOIN recetas r ON p.id_receta = r.id
    JOIN envases e ON p.envase_id = e.id 
    WHERE p.id_receta = r.id 
    """
    if cliente_id is not None and cliente_id != 'Todos':
        query += " AND c.id = ?"
        params.append(cliente_id)
    if producto_id is not None and producto_id != 'Todos':
        query += " AND p.id = ?"
        params.append(producto_id)
    query += " ORDER BY c.nombre, p.nombre, e.descripcion"
    return fetch_df(query, params)

def get_ventas_con_detalles():
    """Devuelve un DataFrame con el historial completo de ventas."""
    query = """
    SELECT
        v.id AS venta_id,                
        v.numero_comprobante,
        v.fecha_venta,
        v.total_venta,
        v.observacion,
        v.estado_venta,
        d.cantidad,
        d.precio_unitario,
        (d.cantidad * d.precio_unitario) AS subtotal_linea,
        d.stock_id,
        COALESCE(r_s.nombre, r_prod.nombre) AS producto_nombre,
        COALESCE(e_s.descripcion, e_prod.descripcion) AS envase_descripcion,
        COALESCE(s.lote, prod.lote) AS lote,
        c.id AS cliente_id,
        c.nombre AS cliente_nombre,
        c.contacto AS cliente_contacto,
        rev.id AS revendedor_id,
        rev.nombre AS revendedor_nombre,
        rev.contacto AS revendedor_contacto,
        rev.descuento AS revendedor_descuento
    FROM ventas v
    JOIN detalle_venta d ON v.id = d.venta_id
    LEFT JOIN stock_productos_envasados s ON d.stock_id = s.id
    LEFT JOIN recetas r_s ON s.receta_id = r_s.id
    LEFT JOIN envases e_s ON s.envase_id = e_s.id
    LEFT JOIN producciones prod ON d.stock_id = prod.id 
    LEFT JOIN pedidos_produccion pp ON prod.pedido_id = pp.id
    LEFT JOIN recetas r_prod ON pp.receta_id = r_prod.id
    LEFT JOIN productos pr_prod ON pr_prod.id = (
        SELECT id FROM productos
        WHERE id_receta = r_prod.id AND cliente_id = pp.cliente_id
        LIMIT 1
    )
    LEFT JOIN envases e_prod ON pr_prod.envase_id = e_prod.id
    LEFT JOIN clientes c ON v.cliente_id = c.id
    LEFT JOIN revendedores rev ON v.revendedor_id = rev.id
    ORDER BY v.fecha_venta DESC
    """
    try:
        df = fetch_df(query)
        df['fecha_venta'] = pd.to_datetime(df['fecha_venta'])
        return df
    except Exception as e:
        st.error(f"Error al obtener el historial de ventas: {e}")
        return pd.DataFrame()
        
def get_detalle_venta(venta_id):
    """Obtiene el detalle de los productos de una venta específica."""
    query = """
    SELECT
        dv.cantidad,
        dv.precio_unitario,
        dv.subtotal,
        COALESCE(r_s.nombre, r_prod.nombre) AS producto_nombre,
        COALESCE(e_s.descripcion, e_prod.descripcion) AS envase_descripcion,
        COALESCE(s.lote, prod.lote) AS lote,
        l.nombre AS linea_nombre
    FROM detalle_venta AS dv
    LEFT JOIN stock_productos_envasados AS s ON dv.stock_id = s.id
    LEFT JOIN recetas AS r_s ON s.receta_id = r_s.id
    LEFT JOIN envases AS e_s ON s.envase_id = e_s.id
    LEFT JOIN productos AS p_s ON p_s.id = (
        SELECT id FROM productos
        WHERE id_receta = r_s.id AND envase_id = e_s.id
        LIMIT 1
    )
    LEFT JOIN lineas AS l_s ON p_s.linea_id = l_s.id
    LEFT JOIN producciones AS prod ON dv.stock_id = prod.id
    LEFT JOIN pedidos_produccion AS pp ON prod.pedido_id = pp.id
    LEFT JOIN recetas AS r_prod ON pp.receta_id = r_prod.id
    LEFT JOIN productos AS p_prod ON p_prod.id = (
        SELECT id FROM productos
        WHERE id_receta = r_prod.id AND cliente_id = pp.cliente_id
        LIMIT 1
    )
    LEFT JOIN envases e_prod ON p_prod.envase_id = e_prod.id
    LEFT JOIN lineas AS l_prod ON p_prod.linea_id = l_prod.id
    LEFT JOIN lineas AS l ON COALESCE(l_s.id, l_prod.id) = l.id
    WHERE dv.venta_id = ?;
    """
    return fetch_df(query, (venta_id,))

def reactivar_venta_y_descontar_stock(venta_id):
    """
    Reactiva una venta anulada y descuenta el stock (permite stock negativo).
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    bekim_id = 8
    CAPACIDAD_TAMBOR = 200.0

    try:
        conn.execute("BEGIN TRANSACTION")

        detalle = cursor.execute(
            "SELECT stock_id, cantidad FROM detalle_venta WHERE venta_id = ?", (venta_id,)
        ).fetchall()

        if not detalle:
            st.error("❌ No se encontraron detalles para esta venta.")
            conn.rollback()
            return False

        fecha_hoy = datetime.now().strftime("%Y-%m-%d")

        for item in detalle:
            stock_id = item["stock_id"]
            cantidad = item["cantidad"]

            row_spe = cursor.execute(
                "SELECT cantidad FROM stock_productos_envasados WHERE id = ?", (stock_id,)
            ).fetchone()

            if row_spe:
                # Advertencia visual pero se procede
                if row_spe["cantidad"] < cantidad:
                    st.warning(f"⚠️ Stock insuficiente al reactivar (ID Stock: {stock_id}). "
                               f"Disponible: {row_spe['cantidad']}, requerido: {cantidad}. El stock quedará negativo.")
                cursor.execute(
                    "UPDATE stock_productos_envasados SET cantidad = cantidad - ? WHERE id = ?",
                    (cantidad, stock_id)
                )
            else:
                row_prod = cursor.execute("""
                    SELECT prod.cantidad_real_litros,
                           (SELECT cliente_id FROM pedidos_produccion WHERE id = prod.pedido_id) AS cliente_id
                    FROM producciones prod WHERE id = ?
                """, (stock_id,)).fetchone()

                if row_prod and row_prod["cliente_id"] == bekim_id:
                    litros_necesarios = cantidad * CAPACIDAD_TAMBOR
                    if row_prod["cantidad_real_litros"] < litros_necesarios:
                        tambores_disp = round(row_prod["cantidad_real_litros"] / CAPACIDAD_TAMBOR)
                        st.warning(f"⚠️ Stock Bekim insuficiente al reactivar. "
                                   f"Disponible: {tambores_disp} tambores, requerido: {cantidad}. Quedará negativo.")
                    nueva_cant = row_prod["cantidad_real_litros"] - litros_necesarios
                    cursor.execute(
                        "UPDATE producciones SET cantidad_real_litros = ?, estado = 'producido' WHERE id = ?",
                        (nueva_cant, stock_id)
                    )
                    if nueva_cant <= 0:
                        cursor.execute(
                            "UPDATE producciones SET estado = 'vendido' WHERE id = ?", (stock_id,)
                        )
                else:
                    st.error(f"❌ No se encontró stock para stock_id={stock_id}.")
                    conn.rollback()
                    return False

            cursor.execute("""
                INSERT INTO movimientos_productos_envasados
                    (stock_id, tipo_movimiento, cantidad, fecha, observacion)
                VALUES (?, 'Egreso', ?, ?, 'Reactivación de venta anulada')
            """, (stock_id, cantidad, fecha_hoy))

        cursor.execute("UPDATE ventas SET estado_venta = 'activa' WHERE id = ?", (venta_id,))
        conn.commit()
        st.success("✅ Venta reactivada y stock actualizado correctamente.")
        return True

    except sqlite3.Error as e:
        conn.rollback()
        st.error(f"❌ Error al reactivar la venta: {e}")
        return False
    finally:
        conn.close()

def get_ventas_con_detalles_por_venta(venta_id):
    """Devuelve un DataFrame para una venta específica."""
    query = """
    SELECT
        v.fecha_venta,
        v.total_venta,
        v.numero_comprobante,
        dv.cantidad,
        dv.precio_unitario,
        (dv.cantidad * dv.precio_unitario) AS subtotal_linea,
        COALESCE(r_s.nombre, r_prod.nombre)            AS producto_nombre,
        COALESCE(e_s.descripcion, e_prod.descripcion)  AS envase_descripcion,
        COALESCE(s.lote, prod.lote)                    AS lote
    FROM ventas v
    JOIN detalle_venta dv ON dv.venta_id = v.id
    LEFT JOIN stock_productos_envasados s  ON dv.stock_id = s.id
    LEFT JOIN recetas r_s    ON s.receta_id  = r_s.id
    LEFT JOIN envases e_s    ON s.envase_id  = e_s.id
    LEFT JOIN producciones prod ON dv.stock_id = prod.id
    LEFT JOIN pedidos_produccion pp ON prod.pedido_id = pp.id
    LEFT JOIN recetas r_prod ON pp.receta_id = r_prod.id
    LEFT JOIN productos pr_prod ON pr_prod.id = (
        SELECT id FROM productos
        WHERE id_receta = r_prod.id AND cliente_id = pp.cliente_id
        LIMIT 1
    )
    LEFT JOIN envases e_prod ON pr_prod.envase_id = e_prod.id
    WHERE v.id = ?
    """
    return fetch_df(query, (venta_id,))

def anular_venta_y_revertir_stock(venta_id):
    """Anula una venta y revierte la cantidad de productos al stock original."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    bekim_id = 8
    CAPACIDAD_TAMBOR = 200.0

    try:
        conn.execute("BEGIN TRANSACTION")

        detalle_venta_query = "SELECT stock_id, cantidad FROM detalle_venta WHERE venta_id = ?"
        detalle_venta = cursor.execute(detalle_venta_query, (venta_id,)).fetchall()

        if not detalle_venta:
            st.error("❌ No se encontraron detalles para la venta seleccionada. No se puede anular.")
            conn.rollback()
            return

        fecha_hoy = datetime.now().strftime("%Y-%m-%d")
        observacion = f"Anulación de venta ID: {venta_id}"

        for item in detalle_venta:
            stock_id = item["stock_id"]
            cantidad_vendida = item["cantidad"]

            cursor.execute("SELECT id, cliente_id FROM stock_productos_envasados WHERE id = ?", (stock_id,))
            existe_stock_row = cursor.fetchone()

            if existe_stock_row:
                cursor.execute(
                    "UPDATE stock_productos_envasados SET cantidad = cantidad + ? WHERE id = ?",
                    (cantidad_vendida, stock_id),
                )
            else:
                cursor.execute("""
                    SELECT 
                        id, 
                        cantidad_real_litros, 
                        (SELECT cliente_id FROM pedidos_produccion pp WHERE pp.id = prod.pedido_id) as cliente_id 
                    FROM producciones prod 
                    WHERE id = ?
                """, (stock_id,))
                produccion = cursor.fetchone()
                
                if produccion and produccion['cliente_id'] == bekim_id:
                    litros_a_revertir = cantidad_vendida * CAPACIDAD_TAMBOR
                    nueva_cantidad_litros = produccion['cantidad_real_litros'] + litros_a_revertir
                    
                    cursor.execute(
                        "UPDATE producciones SET cantidad_real_litros = ?, estado = 'producido' WHERE id = ?", 
                        (nueva_cantidad_litros, stock_id)
                    )
                elif produccion:
                    st.warning(f"Stock ID {stock_id} no encontrado. Omitiendo reversión.")
                    continue

            cursor.execute(
                """
                INSERT INTO movimientos_productos_envasados
                    (stock_id, tipo_movimiento, cantidad, fecha, observacion)
                VALUES (?, 'Ingreso', ?, ?, ?)
                """,
                (stock_id, cantidad_vendida, fecha_hoy, observacion),
            )

        cursor.execute("UPDATE ventas SET estado_venta = 'anulada' WHERE id = ?", (venta_id,))
        conn.commit()
        st.success("✅ Venta anulada y stock/producción restablecidos exitosamente.")

    except sqlite3.Error as e:
        st.error(f"❌ Ocurrió un error al anular la venta: {e}")
        conn.rollback()
    finally:
        conn.close()

def get_next_comprobante_number():
    """Obtiene el próximo número de comprobante basado en la DB."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT COALESCE(MAX(CAST(numero_comprobante AS INTEGER)), 0) FROM ventas"
    cursor.execute(query)
    max_comp = cursor.fetchone()[0]
    conn.close()
    
    try:
        max_id = int(max_comp)
    except (TypeError, ValueError):
        max_id = 0
        
    return max_id, max_id + 1

# =================================================================================================
# LÓGICA DE GENERACIÓN DE PDF CON REPORTLAB
# =================================================================================================
def generar_comprobante_pdf(comprobante_data):
    """Genera un comprobante de venta elegante y profesional en formato vertical (A4)."""
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from io import BytesIO

    conn = get_connection()
    venta_id = comprobante_data["venta_id"]

    query = """
    SELECT
        dv.cantidad,
        dv.precio_unitario,
        (dv.cantidad * dv.precio_unitario) AS subtotal,
        COALESCE(r_s.nombre, r_p.nombre) AS producto_nombre,
        COALESCE(e_s.descripcion, e_prod.descripcion) AS envase
    FROM detalle_venta dv
    LEFT JOIN stock_productos_envasados sp ON dv.stock_id = sp.id
    LEFT JOIN recetas r_s ON sp.receta_id = r_s.id
    LEFT JOIN envases e_s ON sp.envase_id = e_s.id
    LEFT JOIN producciones p ON dv.stock_id = p.id
    LEFT JOIN pedidos_produccion pp ON p.pedido_id = pp.id
    LEFT JOIN recetas r_p ON pp.receta_id = r_p.id
    LEFT JOIN productos pr_prod ON pr_prod.id = (
        SELECT id FROM productos
        WHERE id_receta = r_p.id AND cliente_id = pp.cliente_id
        LIMIT 1
    )
    LEFT JOIN envases e_prod ON pr_prod.envase_id = e_prod.id
    WHERE dv.venta_id = ?
    """

    carrito_df = pd.read_sql_query(query, conn, params=(venta_id,))
    conn.close()

    if "envase" not in carrito_df.columns:
        carrito_df["envase"] = ""

    # Agrupar ítems idénticos para evitar redundancia visual
    carrito_df = carrito_df.groupby(
        ["producto_nombre","envase","precio_unitario"],
        dropna=False
    ).agg(
        cantidad=("cantidad","sum"),
        subtotal=("subtotal","sum")
    ).reset_index()

    buffer = BytesIO()
    
    # Documento en formato vertical (Portrait)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm,
        allowSplitting=1
    )

    elements = []
    styles = getSampleStyleSheet()

    estilo_empresa_titulo = ParagraphStyle(
        'com_empresa_titulo',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=15,
        textColor=colors.HexColor('#1a1a2e')
    )
    estilo_empresa_detalles = ParagraphStyle(
        'com_empresa_det',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#555555')
    )
    estilo_titulo_documento = ParagraphStyle(
        'com_doc_titulo',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=18,
        alignment=TA_RIGHT,
        textColor=colors.HexColor('#1a1a2e')
    )
    estilo_meta_documento = ParagraphStyle(
        'com_doc_meta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        alignment=TA_RIGHT,
        textColor=colors.HexColor('#333333')
    )
    estilo_seccion_header = ParagraphStyle(
        'com_sec_head',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=colors.HexColor('#1a1a2e')
    )
    estilo_seccion_info = ParagraphStyle(
        'com_sec_info',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#333333')
    )
    estilo_celda = ParagraphStyle(
        'com_celda',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#333333')
    )
    estilo_celda_negrita = ParagraphStyle(
        'com_celda_bold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#1a1a2e')
    )
    estilo_header_tabla = ParagraphStyle(
        'com_header_tabla',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        alignment=TA_CENTER,
        textColor=colors.white
    )

    # Bloque de datos de la empresa (Izquierda)
    col_empresa_info = [
        Paragraph("FÁBRICA DE PRODUCTOS CAPILARES", estilo_empresa_titulo),
        Spacer(1, 4),
        Paragraph("Elaboración de productos de cosmetica capilar", estilo_empresa_detalles),
        Paragraph("San Miguel de Tucumán, Argentina", estilo_empresa_detalles),
        #Paragraph("Email: administracion@minerva.com", estilo_empresa_detalles),
    ]

    # Formatear fecha del comprobante de forma limpia
    fecha_raw = comprobante_data.get('fecha_salida', '')
    try:
        if hasattr(fecha_raw, 'strftime'):
            fecha_fmt = fecha_raw.strftime('%d/%m/%Y %H:%M')
        else:
            fecha_fmt = pd.to_datetime(str(fecha_raw)).strftime('%d/%m/%Y %H:%M')
    except Exception:
        fecha_fmt = str(fecha_raw)

    nro_comp = str(comprobante_data.get('numero_factura', '')).zfill(5)

    # Bloque de datos del documento (Derecha)
    col_comprobante_meta = [
        Paragraph("COMPROBANTE DE VENTA", estilo_titulo_documento),
        Spacer(1, 6),
        Paragraph(f"<b>Nº de Factura:</b> 0001-{nro_comp}", estilo_meta_documento),
        Paragraph(f"<b>Fecha de Salida:</b> {fecha_fmt}", estilo_meta_documento),
    ]

    # Tabla Header principal (9.5 cm + 8.5 cm = 18.0 cm de espacio de impresión disponible)
    header_table = Table([[col_empresa_info, col_comprobante_meta]], colWidths=[9.5*cm, 8.5*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    elements.append(header_table)

    # Línea decorativa divisoria en azul profundo
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1a1a2e'), spaceBefore=2, spaceAfter=12))

    # Caja informativa para datos del Cliente
    nombre_cliente = str(comprobante_data['cliente_nombre']).upper()
    contacto_cliente = str(comprobante_data['cliente_contacto']).upper() if comprobante_data['cliente_contacto'] else 'SIN ESPECIFICAR'

    col_facturado_a = [
        Paragraph("", estilo_seccion_header),
        Spacer(1, 4),
        Paragraph(f"<b>Cliente / Razón Social:</b> {nombre_cliente}", estilo_seccion_info),
        Paragraph(f"<b>Contacto / Dirección:</b> {contacto_cliente}", estilo_seccion_info),
    ]

    client_box_data = [[col_facturado_a, ""]]
    client_box_table = Table(client_box_data, colWidths=[12.0*cm, 6.0*cm])
    client_box_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8f9fc')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#e1e4eb')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elements.append(client_box_table)
    elements.append(Spacer(1, 15))

    # Tabla de items (Cantidad: 2.0 cm, Descripción: 10.0 cm, Precio Unit: 3.0 cm, Subtotal: 3.0 cm = 18.0 cm)
    data_table = [[
        Paragraph("Cant.", estilo_header_tabla),
        Paragraph("Descripción del Producto", estilo_header_tabla),
        Paragraph("Precio Unitario", estilo_header_tabla),
        Paragraph("Subtotal", estilo_header_tabla)
    ]]

    for _, row in carrito_df.iterrows():
        descripcion = str(row["producto_nombre"]).upper()
        if row["envase"]:
            descripcion = f"{descripcion} ({str(row['envase']).upper()})"

        data_table.append([
            Paragraph(f"{int(row['cantidad'])}", ParagraphStyle('qty', parent=estilo_celda, alignment=TA_CENTER)),
            Paragraph(descripcion, estilo_celda),
            Paragraph(f"${row['precio_unitario']:,.2f}", ParagraphStyle('punit', parent=estilo_celda, alignment=TA_RIGHT)),
            Paragraph(f"${row['subtotal']:,.2f}", ParagraphStyle('subt', parent=estilo_celda, alignment=TA_RIGHT))
        ])

    subtotal_venta = carrito_df["subtotal"].sum()
    total_final = float(comprobante_data.get("total_final_aplicado_db") or subtotal_venta)

    # Estilos del bloque inferior de cuentas y totales
    estilo_totales_label = ParagraphStyle('tot_lbl', parent=estilo_celda_negrita, alignment=TA_RIGHT)
    estilo_totales_val = ParagraphStyle('tot_val', parent=estilo_celda, alignment=TA_RIGHT)
    estilo_total_final_lbl = ParagraphStyle('tot_fnl_lbl', parent=estilo_celda_negrita, alignment=TA_RIGHT, fontSize=10, textColor=colors.HexColor('#1a1a2e'))
    estilo_total_final_val = ParagraphStyle('tot_fnl_val', parent=estilo_celda_negrita, alignment=TA_RIGHT, fontSize=11, textColor=colors.HexColor('#c0392b'))

    # Fila: Subtotal
    data_table.append([
        "", "",
        Paragraph("SUBTOTAL:", estilo_totales_label),
        Paragraph(f"${subtotal_venta:,.2f}", estilo_totales_val)
    ])

    # Fila: Descuento aplicable (si existiese)
    diferencia = subtotal_venta - total_final
    descuento_porcentaje = comprobante_data.get("descuento", 0)
    if diferencia > 0.01:
        if descuento_porcentaje > 0:
            label_desc = f"DESCUENTO ({descuento_porcentaje}%):"
        else:
            pct_calculado = (diferencia / subtotal_venta * 100) if subtotal_venta else 0
            label_desc = f"DESCUENTO ({pct_calculado:.1f}%):"
        data_table.append([
            "", "",
            Paragraph(label_desc, estilo_totales_label),
            Paragraph(f"-${diferencia:,.2f}", estilo_totales_val)
        ])

    # Fila: Total Final Destacado
    data_table.append([
        "", "",
        Paragraph("TOTAL FINAL:", estilo_total_final_lbl),
        Paragraph(f"${total_final:,.2f}", estilo_total_final_val)
    ])

    # Construir y aplicar estilos a la tabla
    table = Table(
        data_table,
        colWidths=[2.0*cm, 10.0*cm, 3.0*cm, 3.0*cm],
        repeatRows=1,
        splitByRow=True
    )

    t_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]

    # Filas de ítems alternas (efecto cebra)
    n_items = len(carrito_df)
    for idx in range(1, n_items + 1):
        bg_color = colors.HexColor('#f8f9fc') if idx % 2 == 0 else colors.white
        t_style.append(("BACKGROUND", (0, idx), (-1, idx), bg_color))
        t_style.append(("LINEBELOW", (0, idx), (-1, idx), 0.5, colors.HexColor('#e1e4eb')))

    # Estructura del bloque inferior de totales
    total_rows_start = n_items + 1
    t_style.append(("SPAN", (0, total_rows_start), (1, -1)))
    t_style.append(("BACKGROUND", (2, total_rows_start), (-1, -1), colors.HexColor('#f4f6fa')))
    t_style.append(("BOX", (2, total_rows_start), (-1, -1), 1, colors.HexColor('#e1e4eb')))
    t_style.append(("INNERGRID", (2, total_rows_start), (-1, -1), 0.5, colors.HexColor('#e1e4eb')))
    t_style.append(("LINEABOVE", (2, -1), (-1, -1), 1.2, colors.HexColor('#1a1a2e')))

    table.setStyle(TableStyle(t_style))
    elements.append(table)

    elements.append(Spacer(1, 30))
    estilo_nota_titulo = ParagraphStyle('nota_tit', parent=estilo_celda_negrita, fontSize=8, textColor=colors.HexColor('#555555'))
    estilo_nota_cuerpo = ParagraphStyle('nota_corp', parent=estilo_celda, fontSize=7.5, textColor=colors.HexColor('#777777'))

    elements.append(Paragraph("<b>INFORMACIÓN DE FACTURACIÓN & CONDICIONES:</b>", estilo_nota_titulo))
    elements.append(Paragraph("• El pago debe realizarse dentro de los plazos establecidos según su convenio comercial.", estilo_nota_cuerpo))
    elements.append(Paragraph("• Si efectúa transferencias bancarias, por favor remita el comprobante adjunto indicando el Número de Factura.", estilo_nota_cuerpo))
    elements.append(Spacer(1, 15))
    elements.append(Paragraph("<i>Gracias por elegir la excelencia y calidad de nuestra gama de productos capilares.</i>", ParagraphStyle('gracias', parent=estilo_celda, alignment=TA_CENTER, fontSize=8.5, textColor=colors.HexColor('#555555'))))

    doc.build(elements)
    buffer.seek(0)
    return buffer
        
def generar_orden_empaquetado_pdf(comprobante_data):
    from reportlab.platypus import HRFlowable
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm
    )

    elements = []
    styles = getSampleStyleSheet()

    estilo_empresa = ParagraphStyle(
        'empresa', fontSize=9, leading=11, alignment=TA_CENTER,
        textColor=colors.HexColor('#555555')
    )
    estilo_titulo_remito = ParagraphStyle(
        'titulo_remito', fontSize=18, leading=22, alignment=TA_CENTER,
        fontName='Helvetica-Bold', textColor=colors.HexColor('#1a1a2e')
    )
    estilo_numero = ParagraphStyle(
        'numero', fontSize=11, leading=14, alignment=TA_CENTER,
        fontName='Helvetica-Bold', textColor=colors.HexColor('#c0392b')
    )
    estilo_label = ParagraphStyle(
        'label', fontSize=8, leading=10, alignment=TA_LEFT,
        fontName='Helvetica-Bold', textColor=colors.HexColor('#555555')
    )
    estilo_valor = ParagraphStyle(
        'valor', fontSize=10, leading=13, alignment=TA_LEFT,
        fontName='Helvetica-Bold', textColor=colors.HexColor('#1a1a2e')
    )
    estilo_header_tabla = ParagraphStyle(
        'header_tabla', fontSize=8, leading=10, alignment=TA_CENTER,
        fontName='Helvetica-Bold', textColor=colors.white
    )
    estilo_celda = ParagraphStyle(
        'celda', fontSize=9, leading=11, alignment=TA_LEFT,
        fontName='Helvetica'
    )
    estilo_celda_centro = ParagraphStyle(
        'celda_centro', fontSize=9, leading=11, alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    estilo_pie = ParagraphStyle(
        'pie', fontSize=7, leading=9, alignment=TA_CENTER,
        textColor=colors.HexColor('#888888'), fontName='Helvetica-Oblique'
    )
    estilo_firma_sub = ParagraphStyle(
        'firma_sub', fontSize=7, leading=9, alignment=TA_CENTER,
        fontName='Helvetica', textColor=colors.HexColor('#555555')
    )

    fecha_raw = comprobante_data.get('fecha_salida', '')
    try:
        if hasattr(fecha_raw, 'strftime'):
            fecha_fmt = fecha_raw.strftime('%d/%m/%Y')
        else:
            fecha_fmt = pd.to_datetime(str(fecha_raw)).strftime('%d/%m/%Y')
    except Exception:
        fecha_fmt = str(fecha_raw)

    numero_remito = str(comprobante_data.get('numero_factura', '')).zfill(5)
    cliente_nombre = str(comprobante_data.get('cliente_nombre', '')).upper()
    cliente_contacto = str(comprobante_data.get('cliente_contacto', '')).upper()

    col_empresa = [
        Paragraph("FÁBRICA DE PRODUCTOS CAPILARES", ParagraphStyle(
            'emp_bold', fontSize=11, leading=14, alignment=TA_LEFT,
            fontName='Helvetica-Bold', textColor=colors.HexColor('#1a1a2e')
        )),
        Spacer(1, 4),
        Paragraph("Elaboración de productos de higiene y cosmética", estilo_empresa),
        Paragraph("San Miguel de Tucumán, Argentina", estilo_empresa),
    ]
    col_remito = [
        Paragraph("REMITO INTERNO DE DESPACHO", estilo_titulo_remito),
        Spacer(1, 4),
        Paragraph(f"REMITO 000-{numero_remito}", estilo_numero),
        Spacer(1, 4),
        Paragraph(f"Fecha de Despacho: {fecha_fmt}", ParagraphStyle(
            'fecha', fontSize=9, leading=11, alignment=TA_CENTER,
            fontName='Helvetica', textColor=colors.HexColor('#333333')
        )),
    ]

    header_table_data = [[col_empresa, col_remito]]
    header_table = Table(header_table_data, colWidths=[8*cm, 10*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor('#1a1a2e')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (-1, 0), (-1, 0), 0),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f4ff')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1a1a2e')),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 10))

    dest_data = [
        [
            Paragraph("CLIENTE / DESTINATARIO", estilo_label),
            Paragraph("DIRECCIÓN DE ENTREGA", estilo_label),
            Paragraph("PROVINCIA / CIUDAD", estilo_label),
        ],
        [
            Paragraph(cliente_nombre, estilo_valor),
            Paragraph(cliente_contacto, estilo_valor),
            Paragraph("TUC / SAN MIGUEL DE TUCUMÁN", estilo_valor),
        ]
    ]
    dest_table = Table(dest_data, colWidths=[6*cm, 7.5*cm, 4.5*cm])
    dest_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1a1a2e')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#aaaaaa')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dce8f7')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(dest_table)
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("  DETALLE DE MERCADERÍA", ParagraphStyle(
        'sec_merc', fontSize=9, leading=12, alignment=TA_LEFT,
        fontName='Helvetica-Bold', textColor=colors.white,
        backColor=colors.HexColor('#1a1a2e'), leftIndent=0
    )))
    elements.append(Spacer(1, 4))

    carrito_df = comprobante_data['carrito_df']
    RECETA_COL = 'producto_nombre' if 'producto_nombre' in carrito_df.columns else 'receta_nombre'
    envase_col = 'envase_descripcion' if 'envase_descripcion' in carrito_df.columns else 'envase'

    df_grouped = carrito_df.groupby(
        [RECETA_COL, envase_col],
        dropna=False
    ).agg(
        cantidad=('cantidad', 'sum')
    ).reset_index()

    data_table = [[
        Paragraph("Cód. Producto", estilo_header_tabla),
        Paragraph("Descripción", estilo_header_tabla),
        Paragraph("Presentación", estilo_header_tabla),
        Paragraph("Cant. Unidades", estilo_header_tabla),
        Paragraph("BULTOS", estilo_header_tabla),
    ]]

    for i, row in df_grouped.iterrows():
        nombre_prod = str(row[RECETA_COL])
        envase_val = str(row[envase_col]) if row[envase_col] else ''
        cantidad = int(row['cantidad'])
        data_table.append([
            Paragraph(f"{i+1:03d}", estilo_celda_centro),
            Paragraph(nombre_prod.upper(), estilo_celda),
            Paragraph(envase_val.upper(), estilo_celda),
            Paragraph(str(cantidad), estilo_celda_centro),
            Paragraph("", estilo_celda_centro),  
        ])

    total_unidades = int(df_grouped['cantidad'].sum())
    data_table.append([
        Paragraph("", estilo_celda),
        Paragraph("", estilo_celda),
        Paragraph("TOTAL", ParagraphStyle('tot', fontSize=9, fontName='Helvetica-Bold', alignment=TA_RIGHT)),
        Paragraph(str(total_unidades), ParagraphStyle('tot_val', fontSize=9, fontName='Helvetica-Bold', alignment=TA_CENTER)),
        Paragraph("", estilo_celda),
    ])

    prod_table = Table(
        data_table,
        colWidths=[2*cm, 7.5*cm, 3.5*cm, 3*cm, 2*cm],
        repeatRows=1,
        splitByRow=True
    )

    n_filas = len(data_table)
    prod_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e6b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        *[('BACKGROUND', (0, r), (-1, r), colors.HexColor('#f7f9ff') if r % 2 == 0 else colors.white)
          for r in range(1, n_filas - 1)],
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dce8f7')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#aaaaaa')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1a1a2e')),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (4, 1), (4, n_filas - 2), colors.HexColor('#fffbe6')),
    ]))
    elements.append(prod_table)
    elements.append(Spacer(1, 10))

    condicion_data = [[
        Paragraph(
            "CONDICIÓN DE SALIDA DE LA MERCADERÍA    "
            "☐ BUEN ESTADO    ☐ CON OBSERVACIONES    ☐ TAMBOR ABOLLADO    ☐ ENVASE ROTO",
            ParagraphStyle('cond', fontSize=8, leading=11, fontName='Helvetica',
                           textColor=colors.HexColor('#1a1a2e'))
        )
    ], [
        Paragraph(
            "Observaciones: ___________________________________________________________________________"
            "____________________________",
            ParagraphStyle('obs', fontSize=8, leading=11, fontName='Helvetica',
                           textColor=colors.HexColor('#555555'))
        )
    ]]
    cond_table = Table(condicion_data, colWidths=[18*cm])
    cond_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1a1a2e')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fff8e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(cond_table)
    elements.append(Spacer(1, 10))

    def bloque_firma(titulo_firma, subtitulo):
        return [
            Paragraph(titulo_firma, ParagraphStyle(
                'firma_tit', fontSize=8, fontName='Helvetica-Bold',
                alignment=TA_CENTER, textColor=colors.HexColor('#1a1a2e')
            )),
            Spacer(1, 22),
            Paragraph("_" * 30, ParagraphStyle('linea_f', fontSize=8, alignment=TA_CENTER, textColor=colors.HexColor('#333333'))),
            Paragraph(subtitulo, estilo_firma_sub),
            Spacer(1, 8),
            Paragraph("Fecha: ___/___/______", estilo_firma_sub),
        ]

    firmas_data = [[
        bloque_firma("RESPONSABLE DE DESPACHO", "Nombre y Firma"),
        bloque_firma("TRANSPORTISTA", "Empresa / Nombre"),
        bloque_firma("RECIBIDO CONFORME", "Nombre y Aclaración"),
    ]]
    firmas_table = Table(firmas_data, colWidths=[6*cm, 6*cm, 6*cm])
    firmas_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1a1a2e')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#aaaaaa')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f4ff')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(firmas_table)
    elements.append(Spacer(1, 8))

    elements.append(Paragraph(
        "Este documento acredita el despacho en tiempo y forma y el buen estado de la mercadería al momento de su salida.",
        estilo_pie
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer

def mostrar_boton_descarga_pdf(pdf_buffer, nombre_archivo):
    """Muestra un botón de descarga para un PDF generado."""
    st.download_button(
        label=f"⬇️ Descargar {nombre_archivo}",
        data=pdf_buffer,
        file_name=f"{nombre_archivo}.pdf",
        mime="application/pdf",
    )

def _revertir_stock_linea(cursor, stock_id, cantidad, bekim_id=8, CAPACIDAD_TAMBOR=200.0):
    """Devuelve stock al origen sin restricción de límites."""
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT id FROM stock_productos_envasados WHERE id = ?", (stock_id,))
    es_regular = cursor.fetchone() is not None

    if es_regular:
        cursor.execute(
            "UPDATE stock_productos_envasados SET cantidad = cantidad + ? WHERE id = ?",
            (cantidad, stock_id)
        )
    else:
        cursor.execute("""
            SELECT prod.cantidad_real_litros,
                   (SELECT cliente_id FROM pedidos_produccion WHERE id = prod.pedido_id) AS cliente_id
            FROM producciones prod WHERE id = ?
        """, (stock_id,))
        row = cursor.fetchone()
        if row and row["cliente_id"] == bekim_id:
            nueva_cant_litros = row["cantidad_real_litros"] + cantidad * CAPACIDAD_TAMBOR
            cursor.execute(
                "UPDATE producciones SET cantidad_real_litros = ?, estado = 'producido' WHERE id = ?",
                (nueva_cant_litros, stock_id)
            )
        else:
            raise Exception(f"No se pudo revertir stock para stock_id={stock_id}")

    cursor.execute("""
        INSERT INTO movimientos_productos_envasados
            (stock_id, tipo_movimiento, cantidad, fecha, observacion)
        VALUES (?, 'Ingreso', ?, ?, 'Reversión por edición de factura')
    """, (stock_id, cantidad, fecha_hoy))

def _descontar_stock_linea(cursor, stock_id, cantidad, numero_comprobante, bekim_id=8, CAPACIDAD_TAMBOR=200.0):
    """Descuenta stock sin bloquear la transacción si no hay stock suficiente."""
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT cantidad FROM stock_productos_envasados WHERE id = ?", (stock_id,))
    row_regular = cursor.fetchone()

    if row_regular:
        cursor.execute(
            "UPDATE stock_productos_envasados SET cantidad = cantidad - ? WHERE id = ?",
            (cantidad, stock_id)
        )
    else:
        cursor.execute("""
            SELECT prod.cantidad_real_litros,
                   (SELECT cliente_id FROM pedidos_produccion WHERE id = prod.pedido_id) AS cliente_id
            FROM producciones prod WHERE id = ?
        """, (stock_id,))
        row_bekim = cursor.fetchone()
        if row_bekim and row_bekim["cliente_id"] == bekim_id:
            nueva_cant = row_bekim["cantidad_real_litros"] - cantidad * CAPACIDAD_TAMBOR
            cursor.execute(
                "UPDATE producciones SET cantidad_real_litros = ? WHERE id = ?",
                (nueva_cant, stock_id)
            )
            if nueva_cant <= 0:
                cursor.execute("UPDATE producciones SET estado = 'vendido' WHERE id = ?", (stock_id,))
        else:
            raise Exception(f"No se encontró el stock para stock_id={stock_id}")

    cursor.execute("""
        INSERT INTO movimientos_productos_envasados
            (stock_id, tipo_movimiento, cantidad, fecha, observacion, numero_comprobante)
        VALUES (?, 'Egreso', ?, ?, 'Venta por edición de factura', ?)
    """, (stock_id, cantidad, fecha_hoy, numero_comprobante))


def editar_factura(venta_id, numero_comp, cotizacion_dolar, bekim_price_mode):
    """
    Editor completo de una factura activa usando st.data_editor.
    Se eliminó la restricción rígida de stock al modificar cantidades.
    """
    bekim_id = 8
    ss_key        = f"edit_lineas_{venta_id}"     
    ss_orig_key   = f"edit_orig_{venta_id}"       

    st.write("---")
    st.subheader(f"✏️ Editar Comprobante Nº {numero_comp}")

    conn = get_connection()
    venta_row = conn.execute("""
        SELECT v.fecha_venta, v.total_venta,
               COALESCE(rev.descuento, 0) AS descuento_pct,
               COALESCE(rev.nombre, '') AS revendedor_nombre
        FROM ventas v
        LEFT JOIN revendedores rev ON v.revendedor_id = rev.id
        WHERE v.id = ?
    """, (venta_id,)).fetchone()
    conn.close()
    if not venta_row:
        st.error("No se encontró la venta.")
        return
    fecha_actual       = pd.to_datetime(venta_row["fecha_venta"]).date()
    descuento_pct_rev  = float(venta_row["descuento_pct"] or 0)
    revendedor_nombre  = venta_row["revendedor_nombre"]

    detalle_query = """
        SELECT
            dv.id AS detalle_id,
            dv.stock_id,
            dv.cantidad,
            dv.precio_unitario,
            COALESCE(r_s.nombre, r_prod.nombre)            AS producto_nombre,
            COALESCE(e_s.descripcion, e_prod.descripcion)  AS envase_descripcion
        FROM detalle_venta dv
        LEFT JOIN stock_productos_envasados sp ON dv.stock_id = sp.id
        LEFT JOIN recetas r_s    ON sp.receta_id = r_s.id
        LEFT JOIN envases  e_s   ON sp.envase_id = e_s.id
        LEFT JOIN producciones prod ON dv.stock_id = prod.id
        LEFT JOIN pedidos_produccion pp ON prod.pedido_id = pp.id
        LEFT JOIN recetas r_prod ON pp.receta_id = r_prod.id
        LEFT JOIN productos p_prod ON p_prod.id = (
            SELECT id FROM productos
            WHERE id_receta = r_prod.id AND cliente_id = pp.cliente_id
            LIMIT 1
        )
        LEFT JOIN envases e_prod ON p_prod.envase_id = e_prod.id
        WHERE dv.venta_id = ?
    """
    df_detalle_db = fetch_df(detalle_query, (venta_id,))
    if df_detalle_db.empty:
        st.error("No se encontraron líneas de detalle.")
        return
    df_detalle_db = df_detalle_db.drop_duplicates(subset=["detalle_id"]).reset_index(drop=True)

    if ss_key not in st.session_state:
        st.session_state[ss_orig_key] = df_detalle_db.to_dict(orient="records")
        rows = []
        for r in df_detalle_db.to_dict(orient="records"):
            rows.append({
                "Eliminar": False,
                "Producto": r["producto_nombre"],
                "Envase":   r["envase_descripcion"],
                "Cantidad": int(r["cantidad"]),
                "Precio Unitario": float(r["precio_unitario"]),
                "_detalle_id": int(r["detalle_id"]),
                "_stock_id":   int(r["stock_id"]),
                "_es_nueva":   False,
            })
        st.session_state[ss_key] = rows

    lineas = st.session_state[ss_key]

    st.markdown("### 📋 Líneas de la factura")
    st.caption("Modifique las cantidades sin límites rígidos de stock. Se permite stock negativo.")

    df_edit = pd.DataFrame(lineas)
    cols_visibles = ["Eliminar", "Producto", "Envase", "Cantidad", "Precio Unitario"]

    edited = st.data_editor(
        df_edit[cols_visibles],
        column_config={
            "Eliminar": st.column_config.CheckboxColumn("🗑️ Eliminar", default=False),
            "Producto": st.column_config.TextColumn("Producto", disabled=True),
            "Envase":   st.column_config.TextColumn("Envase",   disabled=True),
            "Cantidad": st.column_config.NumberColumn("Cantidad", min_value=1, step=1), # Sin límite superior
            "Precio Unitario": st.column_config.NumberColumn("Precio Unit.", min_value=0.01, format="%.2f"),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key=f"data_editor_{venta_id}",
    )

    for i, row in edited.iterrows():
        lineas[i]["Eliminar"]        = bool(row["Eliminar"])
        lineas[i]["Cantidad"]        = int(row["Cantidad"])
        lineas[i]["Precio Unitario"] = float(row["Precio Unitario"])

    subtotal_live = sum(
        l["Cantidad"] * l["Precio Unitario"]
        for l in lineas if not l["Eliminar"]
    )
    st.metric("Subtotal (líneas activas)", f"${subtotal_live:,.2f}")

    # --- AGREGAR DESDE STOCK DENTRO DEL EDITOR (Permite agregar incluso sin stock) ---
    st.markdown("### ➕ Agregar producto del stock")

    query_stock_limpio = """
    SELECT
        spe.id          AS stock_id,
        spe.cliente_id,
        c.nombre        AS cliente,
        spe.receta_id,
        spe.envase_id,
        spe.lote,
        spe.cantidad    AS cantidad_real,
        r.nombre        AS receta,
        e.descripcion   AS envase,
        pr.id           AS producto_id,
        pr.nombre       AS producto
    FROM stock_productos_envasados spe
    LEFT JOIN clientes  c  ON spe.cliente_id = c.id
    JOIN  recetas       r  ON spe.receta_id  = r.id
    JOIN  envases       e  ON spe.envase_id  = e.id
    JOIN  productos     pr ON pr.id_receta   = r.id
                          AND pr.envase_id   = e.id
                          AND (pr.cliente_id = spe.cliente_id OR pr.cliente_id IS NULL)

    UNION ALL

    SELECT
        prod.id         AS stock_id,
        pp.cliente_id,
        c.nombre        AS cliente,
        pp.receta_id,
        pr.envase_id,
        prod.lote,
        ROUND(prod.cantidad_real_litros / 200.0) AS cantidad_real,
        r.nombre        AS receta,
        e.descripcion   AS envase,
        pr.id           AS producto_id,
        pr.nombre       AS producto
    FROM producciones prod
    JOIN pedidos_produccion pp ON prod.pedido_id = pp.id
    JOIN recetas            r  ON pp.receta_id   = r.id
    JOIN productos          pr ON pr.id_receta   = r.id AND pr.cliente_id = pp.cliente_id
    JOIN envases            e  ON pr.envase_id   = e.id
    LEFT JOIN clientes      c  ON pp.cliente_id  = c.id
    WHERE prod.estado = 'producido'
      AND pp.cliente_id = 8
    """
    df_stock_limpio = fetch_df(query_stock_limpio)

    if df_stock_limpio.empty:
        st.info("No hay registros de productos en stock.")
    else:
        stock_ids_en_tabla = {int(l["_stock_id"]) for l in lineas if not l["Eliminar"]}
        df_para_agregar = df_stock_limpio[
            ~df_stock_limpio["stock_id"].isin(stock_ids_en_tabla)
        ].copy()

        if df_para_agregar.empty:
            st.info("Todo el stock disponible ya está incluido.")
        else:
            df_para_agregar["_label"] = (
                df_para_agregar["cliente"].fillna("Sin cliente")
                + " | " + df_para_agregar["producto"]
                + " | " + df_para_agregar["envase"]
                + " | Lote: " + df_para_agregar["lote"].astype(str)
                + " | Disp: " + df_para_agregar["cantidad_real"].astype(int).astype(str)
            )

            label_map = dict(zip(df_para_agregar["_label"], df_para_agregar["stock_id"]))

            label_sel = st.selectbox(
                "Producto a agregar",
                list(label_map.keys()),
                key=f"add_sel_{venta_id}"
            )
            stock_id_sel = label_map[label_sel]
            fila_stock   = df_para_agregar[df_para_agregar["stock_id"] == stock_id_sel].iloc[0]
            disp_max     = int(fila_stock["cantidad_real"])

            st.caption(f"Stock disponible de este lote: **{disp_max}** (Puedes solicitar más si lo requieres)")

            with st.form(key=f"form_agregar_{venta_id}"):
                cant_add = st.number_input(
                    f"Cantidad a agregar",
                    min_value=1,
                    value=1,
                    step=1
                )
                agregar_submitted = st.form_submit_button("➕ Agregar al comprobante")

            if agregar_submitted:
                if cant_add > disp_max:
                    st.warning(f"⚠️ Cantidad ({cant_add}) supera el stock disponible ({disp_max}). Se registrará stock negativo.")
                
                cli_id  = int(fila_stock["cliente_id"]) if pd.notna(fila_stock["cliente_id"]) else None
                prod_id = int(fila_stock["producto_id"])
                env_id  = int(fila_stock["envase_id"])
                precio_add = (
                    float(obtener_precio(bekim_id, prod_id, env_id) or 0) * (200.0 if bekim_price_mode == 'Precio en USD por Litro' else 1.0) * cotizacion_dolar
                    if cli_id == bekim_id
                    else (obtener_precio(cli_id, prod_id, env_id) or 0.0)
                )
                lineas.append({
                    "Eliminar":        False,
                    "Producto":        str(fila_stock["producto"]),
                    "Envase":          str(fila_stock["envase"]),
                    "Cantidad":        int(cant_add),
                    "Precio Unitario": float(precio_add),
                    "_detalle_id":     None,
                    "_stock_id":       int(fila_stock["stock_id"]),
                    "_es_nueva":       True,
                })
                st.rerun()

    st.markdown("### 💰 Confirmar cambios")

    col_fecha, col_desc = st.columns(2)
    with col_fecha:
        nueva_fecha = st.date_input("Fecha de la venta", value=fecha_actual, key=f"edit_fecha_{venta_id}")
    with col_desc:
        descuento_edit = st.number_input(
            f"Descuento % (revendedor: {revendedor_nombre})",
            min_value=0.0, max_value=100.0,
            value=descuento_pct_rev,
            step=0.01, format="%.2f",
            key=f"edit_desc_{venta_id}"
        )

    total_con_descuento = subtotal_live * (1 - descuento_edit / 100)

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.metric("Subtotal (líneas activas)", f"${subtotal_live:,.2f}")
    with col_m2:
        if descuento_edit > 0:
            st.metric(
                f"Total con {descuento_edit:.1f}% de descuento",
                f"${total_con_descuento:,.2f}",
                delta=f"-${subtotal_live - total_con_descuento:,.2f}"
            )
        else:
            st.metric("Total", f"${total_con_descuento:,.2f}")

    total_manual = st.number_input(
        "Total final manual (0 = usar total con descuento)",
        min_value=0.0, value=0.0, step=0.01, format="%.2f",
        key=f"edit_total_man_{venta_id}"
    )
    total_a_guardar = total_manual if total_manual > 0 else total_con_descuento

    lineas_activas = [l for l in lineas if not l["Eliminar"]]
    if not lineas_activas:
        st.warning("⚠️ Todas las líneas están marcadas para eliminar. Debe quedar al menos una, o anulá la venta.")

    col_guardar, col_cancelar = st.columns(2)
    with col_guardar:
        guardar = st.button("💾 Guardar todos los cambios", key=f"guardar_edit_{venta_id}",
                            type="primary", disabled=(len(lineas_activas) == 0))
    with col_cancelar:
        if st.button("❌ Cancelar edición", key=f"cancelar_edit_{venta_id}"):
            for k in [ss_key, ss_orig_key, "editar_venta_id", "editar_numero_comp"]:
                st.session_state.pop(k, None)
            st.rerun()

    if guardar:
        editor_state = st.session_state.get(f"data_editor_{venta_id}", {})
        edited_rows  = editor_state.get("edited_rows", {})
        for str_idx, cambios in edited_rows.items():
            idx = int(str_idx)
            if idx < len(lineas):
                if "Eliminar"        in cambios: lineas[idx]["Eliminar"]        = bool(cambios["Eliminar"])
                if "Cantidad"        in cambios: lineas[idx]["Cantidad"]        = int(cambios["Cantidad"])
                if "Precio Unitario" in cambios: lineas[idx]["Precio Unitario"] = float(cambios["Precio Unitario"])

        lineas_activas_final = [l for l in lineas if not l["Eliminar"]]
        subtotal_final = sum(l["Cantidad"] * l["Precio Unitario"] for l in lineas_activas_final)

        desc_key = f"edit_desc_{venta_id}"
        descuento_final = float(st.session_state.get(desc_key, descuento_pct_rev))
        total_man_key   = f"edit_total_man_{venta_id}"
        total_man_final = float(st.session_state.get(total_man_key, 0))

        total_calculado = subtotal_final * (1 - descuento_final / 100)
        total_a_guardar_final = total_man_final if total_man_final > 0 else total_calculado

        originales = {int(r["detalle_id"]): r for r in st.session_state[ss_orig_key]}

        conn = get_connection()
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN TRANSACTION")

            detalle_ids_activos = {
                int(l["_detalle_id"]) for l in lineas_activas_final
                if l["_detalle_id"] is not None
            }

            # 1. Revertir eliminados
            for det_id, orig in originales.items():
                if det_id not in detalle_ids_activos:
                    _revertir_stock_linea(cursor, int(orig["stock_id"]), float(orig["cantidad"]))
                    cursor.execute("DELETE FROM detalle_venta WHERE id = ?", (det_id,))

            # 2. Modificaciones
            for linea in lineas_activas_final:
                if linea["_detalle_id"] is None:
                    continue
                det_id       = int(linea["_detalle_id"])
                orig         = originales[det_id]
                cant_orig    = float(orig["cantidad"])
                cant_nueva   = float(linea["Cantidad"])
                precio_nuevo = float(linea["Precio Unitario"])
                delta = cant_nueva - cant_orig
                if delta > 0:
                    _descontar_stock_linea(cursor, int(linea["_stock_id"]), delta, numero_comp)
                elif delta < 0:
                    _revertir_stock_linea(cursor, int(linea["_stock_id"]), abs(delta))
                nuevo_sub = round(cant_nueva * precio_nuevo, 2)
                cursor.execute(
                    "UPDATE detalle_venta SET cantidad=?, precio_unitario=?, subtotal=? WHERE id=?",
                    (cant_nueva, precio_nuevo, nuevo_sub, det_id)
                )

            # 3. Líneas nuevas
            for linea in lineas_activas_final:
                if linea["_detalle_id"] is not None:
                    continue
                cant_nueva   = float(linea["Cantidad"])
                precio_nuevo = float(linea["Precio Unitario"])
                _descontar_stock_linea(cursor, int(linea["_stock_id"]), cant_nueva, numero_comp)
                cursor.execute(
                    "INSERT INTO detalle_venta (venta_id, stock_id, cantidad, precio_unitario, subtotal) VALUES (?,?,?,?,?)",
                    (venta_id, int(linea["_stock_id"]), cant_nueva, precio_nuevo, round(cant_nueva * precio_nuevo, 2))
                )

            # 4. Actualizar total de la cabecera
            cursor.execute(
                "UPDATE ventas SET fecha_venta=?, total_venta=? WHERE id=?",
                (nueva_fecha.strftime("%Y-%m-%d"), round(total_a_guardar_final, 2), venta_id)
            )

            conn.commit()
            st.success(f"✅ Comprobante Nº {numero_comp} modificado. Total: ${total_a_guardar_final:,.2f}")
            for k in [ss_key, ss_orig_key, "editar_venta_id", "editar_numero_comp"]:
                st.session_state.pop(k, None)
            st.rerun()

        except Exception as e:
            conn.rollback()
            st.error(f"❌ Error al guardar modificaciones: {e}")
        finally:
            conn.close()


def ventas():
    st.title("💲 Gestión y Venta de Productos Envasados")

    clientes = fetch_df("SELECT id, nombre, contacto FROM clientes ORDER BY nombre")
    if clientes.empty:
        st.warning("No hay clientes registrados en la base de datos.")
        return

    tab1, tab2, tab3 = st.tabs(["💲 Gestión de Precios", "🛒 Venta de Productos Envasados", "📊 Historial y Comprobantes"])

    if 'cotizacion_dolar' not in st.session_state:
        st.session_state.cotizacion_dolar = 1000.0 
    if 'bekim_price_mode' not in st.session_state:
        st.session_state.bekim_price_mode = 'Precio en USD por Litro' 

    with tab1:
        st.header("💲 Gestión de Precios")

        clientes_opts = ['Todos'] + clientes['nombre'].tolist()
        cliente_filtro = st.selectbox("Filtrar por Marcas", clientes_opts, key="filtro_cliente_precios")
        productos_query = "SELECT id, nombre FROM productos"
        productos_params = []
        if cliente_filtro != 'Todos':
            cliente_id_temp = int(clientes[clientes['nombre'] == cliente_filtro]['id'].values[0])
            productos_query += " WHERE cliente_id = ?"
            productos_params.append(cliente_id_temp)
        productos_query += " ORDER BY nombre"
        productos = fetch_df(productos_query, productos_params)
        productos_opts = ['Todos'] + productos['nombre'].tolist()
        producto_filtro = st.selectbox("Filtrar por Producto", productos_opts, key="filtro_producto_precios")
        cliente_id = None
        producto_id = None
        if cliente_filtro != 'Todos':
            cliente_id = int(clientes[clientes['nombre'] == cliente_filtro]['id'].values[0])
        if producto_filtro != 'Todos':
            producto_id = int(productos[productos['nombre'] == producto_filtro]['id'].values[0])
        df_precios = get_precios_filtrados(cliente_id, producto_id)
        if df_precios.empty:
            st.warning("No hay combinaciones de productos/clientes/envases cargadas para este filtro.")
        else:
            gb = GridOptionsBuilder.from_dataframe(df_precios[["cliente", "producto", "envase", "precio_unitario"]])
            gb.configure_selection(selection_mode="single", use_checkbox=True)
            gb.configure_pagination(enabled=True)
            grid_options = gb.build()
            grid_response = AgGrid(
                df_precios[["cliente", "producto", "envase", "precio_unitario"]],
                gridOptions=grid_options,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                theme="streamlit",
                height=400,
                allow_unsafe_jscode=True,
                key="precios_grid"
            )
            selected = grid_response.get("selected_rows")
            if selected is not None and not selected.empty:
                sel_row = selected.iloc[0].to_dict()
                st.info(f"Editar precio para: {sel_row['cliente']} | {sel_row['producto']} | {sel_row['envase']}")
                nuevo_precio = st.number_input("Nuevo precio unitario", min_value=0.0, step=0.01, value=float(sel_row["precio_unitario"]))
                if st.button("Guardar precio"):
                    idx = df_precios[
                        (df_precios["cliente"] == sel_row["cliente"]) &
                        (df_precios["producto"] == sel_row["producto"]) &
                        (df_precios["envase"] == sel_row["envase"])
                    ].index[0]
                    set_precio(
                        int(df_precios.loc[idx, "cliente_id"]),
                        int(df_precios.loc[idx, "producto_id"]),
                        int(df_precios.loc[idx, "envase_id"]),
                        nuevo_precio
                    )
                    st.success("Precio guardado correctamente. Recargue la página para ver el cambio.")

    with tab2:
        st.header("🛒 Venta de Productos Envasados")
        
        st.subheader("Configuración de Venta")
        
        # --- CHECKBOX CLAVE: VENDER SIN STOCK ---
        mostrar_sin_stock = st.checkbox(
            "🔍 Permitir vender sin stock (Mostrar productos con stock cero o negativo)", 
            value=False,
            help="Al marcar esta opción, se mostrarán todos los productos de la base de datos permitiendo realizar ventas aunque el stock actual no sea suficiente."
        )
        
        st.session_state.cotizacion_dolar = st.number_input(
            "Ingrese Cotización USD a ARS para Cliente 8 (Ej: 1000.00)",
            min_value=1.0, 
            value=st.session_state.cotizacion_dolar, 
            step=0.01,
            format="%.2f",
            key="cotizacion_dolar_input"
        )
        cotizacion_dolar_actual = st.session_state.cotizacion_dolar
        st.info(f"La venta de productos del Cliente 8 se convertirá a Pesos usando la cotización: **${cotizacion_dolar_actual:,.2f}**")
        
        st.session_state.bekim_price_mode = st.radio(
            "Modalidad de Precio para Cliente 8 (Bekim) en la base de datos:",
            ['Precio en USD por Litro', 'Precio en USD por Tambor (200L)'],
            key='bekim_price_mode_radio',
            help="Seleccione cómo está cargado el 'precio_unitario' para Bekim en la tabla de precios."
        )

        # Se pasa el nuevo parámetro mostrar_sin_stock
        df_stock_full = get_stock_df(cotizacion_dolar_actual, st.session_state.bekim_price_mode, mostrar_sin_stock)
        
        if df_stock_full.empty:
            st.warning("No hay stock registrado en el sistema.")
            df_stock_full = pd.DataFrame()
            
        if not df_stock_full.empty:
            df_stock_full['cliente_display'] = df_stock_full['cliente'].fillna('Sin asignar')
            clientes_stock = ["Todos"] + sorted(df_stock_full["cliente_display"].unique())
            productos_stock = ["Todos"] + sorted(df_stock_full["producto"].dropna().unique())
            envases_stock = ["Todos"] + sorted(df_stock_full["envase"].dropna().unique())

            col1, col2, col3 = st.columns(3)
            with col1:
                cliente_filtro_stock_display = st.selectbox("Filtrar Marcas", clientes_stock, key="cliente_venta_filtro")
            with col2:
                producto_filtro_stock = st.selectbox("Filtrar Producto", productos_stock, key="producto_venta_filtro")
            with col3:
                envase_filtro_stock = st.selectbox("Filtrar Envase", envases_stock, key="envase_venta_filtro")

            if producto_filtro_stock != "Todos":
                df_producto_total = df_stock_full[df_stock_full["producto"] == producto_filtro_stock]
                total_envases = df_producto_total["cantidad"].sum()
                st.metric(
                    label=f"Total Stock Registrado para {producto_filtro_stock}", 
                    value=f"📦 {int(total_envases)} Envases/Tambores"
                )

            df_stock = df_stock_full.copy()
            if cliente_filtro_stock_display != "Todos":
                df_stock = df_stock[df_stock["cliente_display"] == cliente_filtro_stock_display]
            if producto_filtro_stock != "Todos":
                df_stock = df_stock[df_stock["producto"] == producto_filtro_stock]
            if envase_filtro_stock != "Todos":
                df_stock = df_stock[df_stock["envase"] == envase_filtro_stock]

            df_stock["Litros"] = (df_stock["cantidad"] * df_stock["capacidad_litros"]).round(2)
            df_stock["Envases"] = df_stock["cantidad"].astype(int)
            
            mostrar_cols = ["cliente", "producto", "envase", "linea", "lote", "Envases", "Litros"]

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_stock[mostrar_cols].to_excel(writer, index=False, sheet_name="Stock")
            st.download_button(
                label="⬇️ Exportar stock a Excel",
                data=buffer.getvalue(),
                file_name=f"stock_envasado_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            gb = GridOptionsBuilder.from_dataframe(df_stock[mostrar_cols])
            gb.configure_selection(selection_mode="multiple", use_checkbox=True)
            gb.configure_pagination(enabled=True)
            grid_options = gb.build()
            
            grid_response = AgGrid(
                df_stock[mostrar_cols],
                gridOptions=grid_options,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                theme="streamlit",
                height=400,
                allow_unsafe_jscode=True,
                key="stock_venta_grid"
            )
            
            selected_rows = grid_response.get("selected_rows")
            if selected_rows is None:
                selected_rows = []
            elif isinstance(selected_rows, pd.DataFrame):
                selected_rows = selected_rows.to_dict(orient="records")

            if "carrito" not in st.session_state:
                st.session_state.carrito = []

            st.subheader("Agregar productos seleccionados al carrito")
            bekim_id = 8
            if selected_rows:
                with st.form("form_agregar_carrito"):
                    st.write(f"Productos seleccionados: {len(selected_rows)}")
                    cantidades = []
                    valid_input = True
                    for i, fila in enumerate(selected_rows):
                        fila_cliente = safe_str(fila.get("cliente"))
                        fila_producto = safe_str(fila.get("producto"))
                        fila_envase = safe_str(fila.get("envase"))
                        fila_linea = safe_str(fila.get("linea"))
                        fila_lote = safe_str(fila.get("lote"))
                        
                        match_condition = (
                            (df_stock["cliente"].apply(safe_str) == fila_cliente) &
                            (df_stock["producto"].apply(safe_str) == fila_producto) &
                            (df_stock["envase"].apply(safe_str) == fila_envase) &
                            (df_stock["linea"].apply(safe_str) == fila_linea) &
                            (df_stock["lote"].apply(safe_str) == fila_lote)
                        )
                        
                        stock_info_match = df_stock[match_condition]
                        
                        if stock_info_match.empty:
                            st.error(f"Error: No se encontró la coincidencia para {fila['producto']} Lote: {fila['lote']}.")
                            valid_input = False
                            continue
                            
                        stock_info = stock_info_match.iloc[0]
                        cantidad_en_carrito = 0
                        for item in st.session_state.carrito:
                            if item["stock_id"] == stock_info["stock_id"] and item["lote"] == stock_info["lote"]:
                                cantidad_en_carrito = item["cantidad"]
                                break
                        
                        max_disponible = int(stock_info["Envases"]) - cantidad_en_carrito
                        
                        # --- MODIFICADO: YA NO SE LIMITA CON max_value SI SE SUPERA EL DISPONIBLE ---
                        if max_disponible <= 0:
                            st.warning(f"⚠️ ¡Stock Insuficiente o en Cero! El stock actual de {fila['producto']} es {max_disponible}. El sistema registrará stock negativo.")
                            cantidad_input = st.number_input(
                                label=f"Cantidad a vender: {fila['producto']} | Lote: {fila['lote']} (SIN STOCK - Se generará negativo)",
                                min_value=1,
                                value=1,
                                step=1,
                                key=f"cantidad_{i}"
                            )
                        else:
                            cantidad_input = st.number_input(
                                label=f"Cantidad a vender: {fila['producto']} | Lote: {fila['lote']} (Disponible={max_disponible})",
                                min_value=1,
                                value=1,
                                step=1,
                                key=f"cantidad_{i}"
                            )
                            if cantidad_input > max_disponible:
                                st.warning(f"⚠️ Estás solicitando {cantidad_input} unidades, superando el stock disponible ({max_disponible}). El stock final quedará en negativo.")
                        
                        cantidades.append(cantidad_input)
                        
                    agregar = st.form_submit_button("Agregar al carrito")
                    if agregar:
                        if not valid_input:
                            st.error("Por favor corrija las incoherencias antes de continuar.")
                        else:
                            for i, fila in enumerate(selected_rows):
                                fila_cliente = safe_str(fila.get("cliente"))
                                fila_producto = safe_str(fila.get("producto"))
                                fila_envase = safe_str(fila.get("envase"))
                                fila_linea = safe_str(fila.get("linea"))
                                fila_lote = safe_str(fila.get("lote"))
                                
                                match_condition = (
                                    (df_stock["cliente"].apply(safe_str) == fila_cliente) &
                                    (df_stock["producto"].apply(safe_str) == fila_producto) &
                                    (df_stock["envase"].apply(safe_str) == fila_envase) &
                                    (df_stock["linea"].apply(safe_str) == fila_linea) &
                                    (df_stock["lote"].apply(safe_str) == fila_lote)
                                )
                                stock_info_match = df_stock[match_condition]
                                
                                if stock_info_match.empty:
                                    continue
                                    
                                stock_info = stock_info_match.iloc[0]
                                stock_id = int(stock_info["stock_id"])
                                cliente_id = int(stock_info["cliente_id"]) if pd.notna(stock_info["cliente_id"]) else None
                                producto_id = int(stock_info["producto_id"])
                                envase_id = int(stock_info["envase_id"])
                                lote = stock_info["lote"]
                                linea = stock_info["linea"]
                                receta_id = stock_info["receta_id"]
                                
                                precio = None
                                
                                if cliente_id == bekim_id:
                                    precio = stock_info["precio_total_ars_por_tambor"] 
                                    if pd.isna(precio) or precio <= 0:
                                        st.warning(f"No se pudo determinar el precio ARS para Bekim. Cargue un precio base USD.")
                                        continue
                                else:
                                    if cliente_id is None:
                                        st.warning(f"No se puede agregar el producto porque no tiene marca asignada.")
                                        continue
                                    precio = obtener_precio(cliente_id, producto_id, envase_id)
                                    if precio is None or precio <= 0:
                                        st.warning(f"No hay precio definido para {fila['producto']} - {fila['envase']}. Se utilizará $0.00 temporalmente.")
                                        precio = 0.0
                                
                                item_existente = None
                                for item in st.session_state.carrito:
                                    if item["stock_id"] == stock_id and item["lote"] == lote and item["precio_unitario"] == precio:
                                        item_existente = item
                                        break
                                
                                if item_existente:
                                    item_existente["cantidad"] += cantidades[i]
                                else:
                                    st.session_state.carrito.append({
                                        "stock_id": stock_id,
                                        "cliente_id": cliente_id,
                                        "cliente": fila["cliente"],
                                        "producto_id": producto_id,
                                        "producto": fila["producto"],
                                        "envase_id": envase_id,
                                        "envase": fila["envase"],
                                        "linea": linea,
                                        "lote": lote,
                                        "cantidad": cantidades[i],
                                        "precio_unitario": precio,
                                        "receta_id": receta_id,
                                        "receta_nombre": stock_info["receta"], 
                                    })
                            st.success("Carrito actualizado correctamente.")
                            st.rerun()

        st.subheader("🛒 Carrito de ventas actual")
        if st.session_state.carrito:
            carrito_df = pd.DataFrame(st.session_state.carrito)
            carrito_df["Total Item"] = (carrito_df["precio_unitario"] * carrito_df["cantidad"]).round(2)
            
            cols_display = ["cliente", "receta_nombre", "envase", "linea", "lote", "cantidad", "precio_unitario", "Total Item"]
            cols_to_display = [col for col in cols_display if col in carrito_df.columns]

            carrito_df_display = carrito_df[cols_to_display].copy()
            
            edited_df = st.data_editor(
                carrito_df_display,
                column_config={
                    "receta_nombre": "Receta",
                    "precio_unitario": st.column_config.NumberColumn(
                        "Precio Unitario (Modificable)",
                        min_value=0.01,
                        format="%.2f"
                    ),
                    "Total Item": st.column_config.NumberColumn(
                        "Total Item",
                        disabled=True, 
                        format="%.2f"
                    )
                },
                hide_index=True,
                use_container_width=True,
                key="carrito_editor"
            )

            if "carrito_editor" in st.session_state and isinstance(st.session_state.carrito_editor, pd.DataFrame):
                for i, row in edited_df.iterrows():
                    st.session_state.carrito[i]["precio_unitario"] = row["precio_unitario"]

            carrito_df_final = pd.DataFrame(st.session_state.carrito)
            carrito_df_final["total"] = carrito_df_final["precio_unitario"] * carrito_df_final["cantidad"]
            total_carrito = carrito_df_final["total"].sum()
            
            st.metric("Total acumulado de la venta (Subtotal)", f"${total_carrito:,.2f}")
            
            st.subheader("Administrar carrito")
            
            indices_para_eliminar = {f"{i} - {item.get('receta_nombre', item.get('producto', 'Producto'))} ({item.get('envase', 'Envase')})": i for i, item in enumerate(st.session_state.carrito)}
            
            if indices_para_eliminar:
                item_seleccionado_key = st.selectbox(
                    "Seleccione el producto a eliminar del carrito:",
                    list(indices_para_eliminar.keys()),
                    key="elim_select"
                )
                if st.button("Eliminar elemento del carrito"):
                    eliminar_index = indices_para_eliminar[item_seleccionado_key]
                    st.session_state.carrito.pop(eliminar_index)
                    st.success("Elemento eliminado con éxito.")
                    st.rerun()
            else:
                st.info("El carrito está vacío.")

            st.subheader("Datos para finalizar la venta")
            
            max_comp_found, next_comprobante = get_next_comprobante_number()
            st.markdown(f"**Diagnóstico de Comprobante:** Máximo encontrado en DB: `{max_comp_found}`")
            st.info(f"El número de comprobante para esta venta será: **{next_comprobante}**")

            revendedores_df = fetch_df("SELECT id, nombre, contacto, descuento FROM revendedores")
            revendedor_id_map = {row['nombre']: row['id'] for index, row in revendedores_df.iterrows()}
            revendedor_nombre = st.selectbox("Seleccione el revendedor:", list(revendedor_id_map.keys()), key="revendedor_final_venta")
            revendedor_id = revendedor_id_map.get(revendedor_nombre)
            
            revendedor_descuento_predefinido = 0.0
            if revendedor_id:
                revendedor_descuento_predefinido = revendedores_df[revendedores_df['id'] == revendedor_id]['descuento'].iloc[0]
            
            descuento_a_aplicar = st.number_input(
                "Porcentaje de descuento a aplicar (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(revendedor_descuento_predefinido),
                step=0.01,
                format="%.2f"
            )

            subtotal_venta = total_carrito
            total_con_descuento = subtotal_venta * (1 - descuento_a_aplicar / 100)
            st.metric("Total de la venta con descuento (Calculado)", f"${total_con_descuento:,.2f}")
            
            total_final_manual = st.number_input(
                "💰 **Importe FINAL a facturar/comprobante (Opcional):**",
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.2f",
                key="total_final_manual"
            )
            
            total_final_aplicado = total_con_descuento
            if total_final_manual > 0:
                total_final_aplicado = total_final_manual
                st.info(f"Se utilizará el importe manual de **${total_final_aplicado:,.2f}** como el Total Final.")
            else:
                 st.info(f"Se utilizará el importe calculado de **${total_final_aplicado:,.2f}** como el Total Final.")

            monto_pago = st.number_input("💵 Monto de dinero recibido:", min_value=0.0, format="%.2f")
            observacion_general = st.text_area("Observaciones generales para toda la venta (opcional)")
            
            if st.button("Finalizar venta"):
                if not revendedor_id:
                    st.error("Debe seleccionar un revendedor para finalizar la venta.")
                else:
                    conn = get_connection()
                    try:
                        cursor = conn.cursor()
                        
                        # 1. INSERT INTO ventas
                        cursor.execute("""
                            INSERT INTO ventas (fecha_venta, cliente_id, revendedor_id, observacion, numero_comprobante, total_venta)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (date.today().strftime("%Y-%m-%d"), revendedor_id, revendedor_id, observacion_general, next_comprobante, total_final_aplicado))
                        venta_id = cursor.lastrowid
                        
                        # Usamos carrito_df_final
                        for index, item in carrito_df_final.iterrows():
                            subtotal_item = item["total"]
                            
                            # 2. INSERT INTO detalle_venta
                            cursor.execute("""
                                INSERT INTO detalle_venta (venta_id, stock_id, cantidad, precio_unitario, subtotal)
                                VALUES (?, ?, ?, ?, ?)
                            """, (venta_id, item["stock_id"], item["cantidad"], item["precio_unitario"], subtotal_item))
                            
                            # 3. Registro de salida y actualización de stock (Permite actualización con stock negativo)
                            registrar_venta(
                                cursor, 
                                stock_id=item["stock_id"], 
                                cantidad_vender=item["cantidad"], 
                                observacion=observacion_general, 
                                destino="Venta a Revendedor",
                                numero_comprobante=next_comprobante
                            )

                        # 4. INSERT INTO pagos_comprobantes
                        if monto_pago > 0:
                            cursor.execute("""
                                INSERT INTO pagos_comprobantes (venta_id, importe_pagado, fecha_pago)
                                VALUES (?, ?, ?)
                            """, (venta_id, monto_pago, date.today().strftime("%Y-%m-%d")))
                        
                        conn.commit()
                        st.success("🎉 Venta registrada con éxito!")

                        revendedor_info = revendedores_df[revendedores_df['id'] == revendedor_id].iloc[0]
                        
                        # FIXED KEYERROR: Agregamos 'carrito_df_final' al diccionario comprobante_data
                        comprobante_data = {
                            "venta_id": venta_id,
                            "cliente_nombre": revendedor_info["nombre"],
                            "cliente_contacto": revendedor_info["contacto"],
                            "numero_factura": next_comprobante,
                            "fecha_salida": datetime.now().strftime('%d/%m/%Y %H:%M'),
                            "descuento": descuento_a_aplicar,
                            "total_final_aplicado_db": float(total_final_aplicado),
                            "carrito_df": carrito_df_final,  # <--- Solución al KeyError
                        }
                        st.subheader("✅ Venta finalizada. Descargue sus comprobantes:")
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            pdf_comprobante = generar_comprobante_pdf(comprobante_data)
                            mostrar_boton_descarga_pdf(pdf_comprobante, f"comprobante_venta_{next_comprobante}")
                        with col_btn2:
                            pdf_orden = generar_orden_empaquetado_pdf(comprobante_data)
                            mostrar_boton_descarga_pdf(pdf_orden, f"orden_empaquetado_{next_comprobante}")
                        
                        st.session_state.carrito = []
                        if st.button("Limpiar y Volver a Venta"):
                            st.rerun()

                    except Exception as e:
                        conn.rollback()
                        st.error(f"Ocurrió un error al registrar la venta: {e}")
                        st.exception(e)
                    finally:
                        conn.close()
        else:
            st.info("El carrito está vacío. Seleccione productos de la tabla de stock para agregar.")
    
    with tab3:
        st.header("📊 Historial y Comprobantes de Venta")
        df_historial_completo = get_ventas_con_detalles()

        if df_historial_completo.empty:
            st.warning("No hay historial de ventas para mostrar.")
            return

        df_revendedores_historial = df_historial_completo[['revendedor_id', 'revendedor_nombre']].drop_duplicates().sort_values('revendedor_nombre')
        df_revendedores_historial['revendedor_nombre'] = df_revendedores_historial['revendedor_nombre'].fillna('Revendedor sin nombre').replace('', 'Revendedor sin nombre')
        revendedores_nombres = ['Todos'] + df_revendedores_historial['revendedor_nombre'].tolist()
        revendedor_id_map = dict(zip(df_revendedores_historial['revendedor_nombre'], df_revendedores_historial['revendedor_id']))

        st.write("---")
        st.subheader("Filtrar y Seleccionar Comprobante")
        
        col_filtros_1, col_filtros_2, col_filtros_3 = st.columns(3)
        with col_filtros_1:
            fecha_inicio = st.date_input(
                "Fecha de inicio",
                value=pd.to_datetime(df_historial_completo['fecha_venta']).min().date(),
                key="fecha_inicio_historial"
            )
        with col_filtros_2:
            fecha_fin = st.date_input(
                "Fecha de fin",
                value=pd.to_datetime(df_historial_completo['fecha_venta']).max().date(),
                key="fecha_fin_historial"
            )
        with col_filtros_3:
            estado_filtro = st.selectbox(
                "Filtrar por Estado",
                ['Todos', 'activa', 'anulada'],
                key="estado_historial_filtro"
            )

        cliente_historial_filtro = st.selectbox("Filtrar por Revendedor", revendedores_nombres, key="cliente_historial_filtro")
        
        df_filtrado_por_revendedor = df_historial_completo.copy()
        if cliente_historial_filtro != 'Todos':
            revendedor_id_seleccionado = revendedor_id_map.get(cliente_historial_filtro)
            if revendedor_id_seleccionado is not None:
                df_filtrado_por_revendedor = df_historial_completo[df_historial_completo['revendedor_id'] == revendedor_id_seleccionado]
            else:
                st.warning(f"No se encontró el ID para el revendedor: {cliente_historial_filtro}")
                df_filtrado_por_revendedor = pd.DataFrame()

        if df_filtrado_por_revendedor.empty:
            st.warning("No se encontraron comprobantes con los filtros de revendedor aplicados.")
            return

        df_resumen = df_filtrado_por_revendedor.groupby(
            ['numero_comprobante', 'revendedor_nombre', 'revendedor_contacto', 'fecha_venta', 'total_venta', 'estado_venta', 'revendedor_descuento'],
            as_index=False
        ).agg({
            'venta_id': 'first',
            'revendedor_nombre': 'first',
            'revendedor_contacto': 'first',
            'fecha_venta': 'first',
            'total_venta': 'first',
            'estado_venta': 'first',
            'revendedor_descuento': 'first'
        })
        
        df_resumen['fecha_venta_dt'] = pd.to_datetime(df_resumen['fecha_venta'])
        df_filtrado = df_resumen[df_resumen['fecha_venta_dt'].dt.date.between(fecha_inicio, fecha_fin)]
        
        if estado_filtro != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['estado_venta'] == estado_filtro]
        
        if df_filtrado.empty:
            st.warning("No se encontraron comprobantes con los filtros aplicados.")
            return

        gb = GridOptionsBuilder.from_dataframe(df_filtrado)
        gb.configure_column("numero_comprobante", header_name="Nº Comprobante", min_width=150)
        gb.configure_column("revendedor_nombre", header_name="Nombre del Revendedor", min_width=200)
        gb.configure_column("fecha_venta", header_name="Fecha de Venta", min_width=150)
        gb.configure_column("total_venta", header_name="Total ($)", min_width=100)
        gb.configure_column("revendedor_contacto", hide=True)
        gb.configure_column("venta_id", hide=True)
        gb.configure_column("fecha_venta_dt", hide=True)
        gb.configure_column("revendedor_descuento", hide=True) 
        gb.configure_column("estado_venta", header_name="Estado", min_width=100, cellClassRules={'anulada': 'data.estado_venta === "anulada"', 'activa': 'data.estado_venta === "activa"'})
        gb.configure_selection("single", use_checkbox=True)
        gb.configure_pagination(enabled=True, paginationAutoPageSize=False, paginationPageSize=10)
        grid_options = gb.build()

        grid_response = AgGrid(
            df_filtrado,
            gridOptions=grid_options,
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            fit_columns_on_grid_load=True,
            theme="streamlit",
            height=250,
            allow_unsafe_jscode=True,
            key="historial_aggrid"
        )

        selected_rows_data = grid_response.get('selected_rows')

        if isinstance(selected_rows_data, pd.DataFrame):
            selected_rows = selected_rows_data.to_dict(orient='records')
        elif selected_rows_data is None:
            selected_rows = []
        else:
            selected_rows = selected_rows_data

        if selected_rows:
            selected_row = selected_rows[0]
            venta_id = selected_row.get('venta_id')
            numero_comp = selected_row.get('numero_comprobante')
            estado_venta = selected_row.get('estado_venta')

            st.write("---")
            st.subheader(f"Detalles del Comprobante Nº {numero_comp}")

            df_comp = df_historial_completo[df_historial_completo['numero_comprobante'] == numero_comp].copy()
            if df_comp.empty:
                st.warning("No se pudieron cargar los detalles de esta venta.")
            else:
                cliente_nombre = df_comp['revendedor_nombre'].iloc[0] or "Revendedor sin nombre"
                cliente_contacto = df_comp['revendedor_contacto'].iloc[0] or "Sin contacto"
                fecha_venta = df_comp['fecha_venta'].iloc[0]
                descuento_aplicado = float(selected_row.get('revendedor_descuento') or 0)

                st.write(f"**Cliente:** {cliente_nombre}")
                st.write(f"**Fecha:** {fecha_venta}")
                st.write(f"**Estado de la Venta:** {estado_venta.capitalize()}")
                if descuento_aplicado > 0:
                    st.write(f"**Descuento predefinido:** {descuento_aplicado}%")

                df_mostrar = df_comp[['producto_nombre', 'envase_descripcion', 'lote', 'cantidad', 'precio_unitario', 'subtotal_linea']].copy()
                df_mostrar = df_mostrar.rename(columns={'subtotal_linea': 'Subtotal'})
                
                st.dataframe(df_mostrar.rename(columns={
                    'producto_nombre': 'Receta',
                    'envase_descripcion': 'Envase',
                    'cantidad': 'Cantidad',
                    'precio_unitario': 'Precio Unitario'
                }), use_container_width=True)

                total_final_aplicado_db = df_comp['total_venta'].iloc[0]
                st.metric("Total de la Venta (Registrado)", f"${total_final_aplicado_db:,.2f}")

                col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)

                with col_btn1:
                    if estado_venta == 'activa' and venta_id:
                        if st.button(f"🚫 Anular Venta Nº {numero_comp}", key=f"btn_anular_{venta_id}"):
                            anular_venta_y_revertir_stock(venta_id)
                            st.rerun()
                    else:
                        st.warning("⚠️ Esta venta está anulada.")
                        if st.button(f"♻️ Reactivar Venta Nº {numero_comp}", key=f"btn_reactivar_{venta_id}"):
                            if reactivar_venta_y_descontar_stock(venta_id):
                                st.rerun()

                with col_btn4:
                    if estado_venta == 'activa' and venta_id:
                        if st.button(f"✏️ Editar Factura", key=f"btn_editar_{venta_id}"):
                            st.session_state['editar_venta_id'] = venta_id
                            st.session_state['editar_numero_comp'] = numero_comp

                with col_btn2:
                    try:
                        _conn_pdf = get_connection()
                        _v = _conn_pdf.execute(
                            "SELECT fecha_venta, total_venta FROM ventas WHERE id = ?", (venta_id,)
                        ).fetchone()
                        _conn_pdf.close()
                        comprobante_data = {
                            "venta_id": venta_id,
                            "cliente_nombre": cliente_nombre,
                            "cliente_contacto": cliente_contacto,
                            "numero_factura": numero_comp,
                            "fecha_salida": _v["fecha_venta"] if _v else fecha_venta,
                            "descuento": descuento_aplicado,
                            "total_final_aplicado_db": float(_v["total_venta"]) if _v else total_final_aplicado_db,
                        }
                        pdf_comprobante = generar_comprobante_pdf(comprobante_data)
                        st.download_button(
                            label="📄 PDF Comprobante",
                            data=pdf_comprobante.getvalue(),
                            file_name=f"comprobante_venta_{numero_comp}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                    except Exception as e:
                        st.error(f"Error PDF Comprobante: {e}")

                with col_btn3:
                    try:
                        _df_orden = get_ventas_con_detalles_por_venta(venta_id)
                        if _df_orden.empty:
                            st.warning("Sin datos para la orden.")
                        else:
                            comprobante_data_orden = {
                                "cliente_nombre": cliente_nombre,
                                "cliente_contacto": cliente_contacto,
                                "numero_factura": numero_comp,
                                "carrito_df": _df_orden,
                                "fecha_salida": _df_orden["fecha_venta"].iloc[0],
                            }
                            pdf_orden_empaquetado = generar_orden_empaquetado_pdf(comprobante_data_orden)
                            st.download_button(
                                label="📦 PDF Orden",
                                data=pdf_orden_empaquetado.getvalue(),
                                file_name=f"orden_empaquetado_{numero_comp}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                    except Exception as e:
                        st.error(f"Error PDF Orden: {e}")
                
                if (st.session_state.get('editar_venta_id') == venta_id and
                        st.session_state.get('editar_numero_comp') == numero_comp):
                    editar_factura(venta_id, numero_comp, st.session_state.get('cotizacion_dolar', 1000.0), st.session_state.get('bekim_price_mode', 'Precio en USD por Litro'))

        else:
            st.info("Seleccione un comprobante de la tabla para ver sus detalles y descargar los PDFs.")
            
def main():
    st.set_page_config(layout="wide")
    ventas()

if __name__ == "__main__":
    main()