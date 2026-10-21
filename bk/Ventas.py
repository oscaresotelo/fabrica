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

# =================================================================================================
# FUNCIÓN DE UTILIDAD PARA MANEJO ROBUSTO DE NULOS (st-aggrid)
# =================================================================================================
def safe_str(val):
    """
    Convierte el valor a cadena, tratando NaN/None/cadenas 'None'/'nan' como '__NA__' 
    para asegurar la coincidencia en el filtrado de pandas vs. AgGrid.
    """
    # 1. Chequeo de valores nulos de pandas (NaN, None)
    if pd.isna(val) or val is None:
        return '__NA__'
        
    # 2. Chequeo de representaciones de cadena de valores nulos
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
    # Usamos try/except para manejar errores específicos de base de datos
    try:
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df
    except sqlite3.Error as e:
        conn.close()
        st.error(f"Error de base de datos al ejecutar consulta: {e}")
        st.code(query)
        # Devolver un DataFrame vacío en caso de error
        return pd.DataFrame()

# =================================================================================================
# FUNCIÓN set_precio (y otras funciones de DB)
# =================================================================================================
def set_precio(cliente_id, producto_id, envase_id, nuevo_precio):
    """Actualiza el precio de un producto envasado para un cliente, garantizando unicidad en fecha_desde."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Usamos solo la fecha para finalizar el registro anterior (fecha_hasta)
    fecha_hoy_solo_dia = datetime.now().strftime("%Y-%m-%d")
    # 2. Usamos fecha y hora completa para el nuevo registro (fecha_desde), resolviendo el error UNIQUE
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

# --- FUNCIÓN registrar_venta (Utiliza el cursor de la transacción principal) ---
def registrar_venta(cursor, stock_id, cantidad_vender, observacion, destino, numero_comprobante):
    """Registra una venta de stock y los movimientos asociados, y actualiza el stock, utilizando el cursor de la transacción principal."""
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
        # Lógica para Stock Regular (no Bekim)
        cantidad_actual = stock_info["cantidad"]
        if cantidad_vender > cantidad_actual:
            # Se levanta la excepción para que la función llamadora maneje el rollback
            raise Exception(f"No hay suficiente stock para vender {cantidad_vender} envases. Stock actual: {cantidad_actual}")
    
        nueva_cantidad = cantidad_actual - cantidad_vender
        if abs(nueva_cantidad) < 1e-6:
            nueva_cantidad = 0
            
        # Ejecuta la actualización en la base de datos
        cursor.execute("""
            UPDATE stock_productos_envasados
            SET cantidad = ?
            WHERE id = ?
        """, (nueva_cantidad, stock_id))
        
    # Si no se encontró en stock_productos_envasados, busca en producciones (Bekim)
    else:
        # Caso Bekim: El stock_id es el id de la tabla producciones
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

        # Cantidad actual en TAMBORES (unidades vendibles)
        cantidad_tambores_actual = round(cantidad_litros_actual / CAPACIDAD_TAMBOR)
        
        # Validación: cantidad_vender es la cantidad de tambores
        if cantidad_vender > cantidad_tambores_actual:
            raise Exception(f"No hay suficiente stock para vender {cantidad_vender} tambores. Stock actual de tambores: {cantidad_tambores_actual}")
        
        # Reducción de litros en la tabla producciones
        litros_a_reducir = cantidad_vender * CAPACIDAD_TAMBOR
        nueva_cantidad_litros = cantidad_litros_actual - litros_a_reducir
        
        if nueva_cantidad_litros < 0 and abs(nueva_cantidad_litros) > 1e-6:
             raise Exception("Error en el cálculo de litros a reducir. La cantidad en stock se volvería negativa.")
        
        # Reducir la cantidad de litros de la producción
        cursor.execute(
            "UPDATE producciones SET cantidad_real_litros = ? WHERE id = ?", 
            (nueva_cantidad_litros, stock_id)
        )
        
        # Si se agotó el lote, cambiar el estado
        if abs(nueva_cantidad_litros) < 1e-6: # Usar tolerancia de flotante
            cursor.execute("UPDATE producciones SET estado = 'vendido' WHERE id = ?", (stock_id,))

    # Registrar el movimiento de salida para ambos casos
    cursor.execute("""
        INSERT INTO movimientos_productos_envasados
        (stock_id, fecha, cantidad, tipo_movimiento, destino, observacion, numero_comprobante)
        VALUES (?, ?, ?, 'Egreso', ?, ?, ?)
    """, (stock_id, fecha_hoy, cantidad_vender, destino, observacion, numero_comprobante))
    
def get_stock_df(cotizacion_dolar, bekim_price_mode):
    """Obtiene un DataFrame con el stock de productos envasados disponible, uniendo producciones y stock_productos_envasados.
       Calcula el precio en ARS para Bekim usando la cotización del dólar y el modo de precio.
    """
    bekim_id = 8
    
    # --- Determinar el multiplicador basado en el modo de precio ---
    if bekim_price_mode == 'Precio en USD por Litro':
        # Si el precio en la DB es por litro, multiplicamos por 200 para obtener el precio del tambor
        price_multiplier = 200.0 
    else: # 'Precio en USD por Tambor (200L)'
        # Si el precio en la DB ya es por tambor, el multiplicador es 1
        price_multiplier = 1.0
    # -------------------------------------------------------------
    
    # Consulta para el Cliente 8 (Bekim). Usa CTE para calcular el precio base y luego el precio en ARS.
    query_bekim = f"""
    WITH StockPrecio AS (
        -- 1. Selecciona los datos base, y el precio USD base.
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
            -- SUBQUERY: Obtener el precio unitario (USD/litro o USD/Tambor)
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
            prod.estado = 'producido' 
            AND prod.cantidad_real_litros > 0 
            AND pp.cliente_id = {bekim_id} -- Filtro fijo para cliente 8
    )
    -- 2. Consulta final que utiliza el precio base para calcular el precio total en ARS
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
        -- Cantidad de tambores de 200L disponibles
        ROUND(cantidad_real_litros / 200.0) AS cantidad, 
        producto_id,
        producto,
        linea,
        precio_usd_base,
        -- Columna auxiliar para el precio unitario por TAMBOR (200L) en ARS
        (precio_usd_base * {price_multiplier} * ?) AS precio_total_ars_por_tambor -- Usa el multiplicador variable
    FROM
        StockPrecio
    """
    
    # Consulta para otros clientes (usa stock_productos_envasados).
    query_otros = """
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
        NULL AS precio_total_ars_por_tambor -- Columna placeholder para consistencia
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
        spe.cantidad > 0 AND (spe.cliente_id IS NULL OR spe.cliente_id != ?)
    """
    
    # Solo pasamos la cotización como parámetro para la consulta de Bekim (query_bekim)
    df_bekim = fetch_df(query_bekim, [cotizacion_dolar])
    # Pasamos el bekim_id como parámetro para excluirlo en la consulta de otros clientes (query_otros)
    df_otros = fetch_df(query_otros, [bekim_id])
    
    # Si alguna consulta falló, fetch_df devuelve un DF vacío y lo manejamos aquí
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
    query += """
    ORDER BY c.nombre, p.nombre, e.descripcion
    """
    return fetch_df(query, params)

def get_ventas_con_detalles():
    """
    Devuelve un DataFrame con el historial completo de ventas,
    incluyendo detalles del cliente, revendedor y producto envasado.
    """
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
        d.stock_id,
        
        -- Uso de COALESCE para obtener los detalles de producto y lote de la fuente de stock correcta
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
    
    -- Joins para stock_productos_envasados (stock regular)
    LEFT JOIN stock_productos_envasados s ON d.stock_id = s.id
    LEFT JOIN recetas r_s ON s.receta_id = r_s.id
    LEFT JOIN envases e_s ON s.envase_id = e_s.id
    
    -- Joins para producciones (stock de Bekim)
    LEFT JOIN producciones prod ON d.stock_id = prod.id 
    LEFT JOIN pedidos_produccion pp ON prod.pedido_id = pp.id
    LEFT JOIN recetas r_prod ON pp.receta_id = r_prod.id
    -- Se requiere el join a productos para determinar el envase de la receta para el cliente de la producción
    LEFT JOIN productos pr_prod ON pr_prod.id_receta = r_prod.id AND pr_prod.cliente_id = pp.cliente_id
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
        -- Se utiliza la lógica de COALESCE para traer la info de stock_productos_envasados o producciones (Bekim)
        COALESCE(r_s.nombre, r_prod.nombre) AS producto_nombre,
        COALESCE(e_s.descripcion, e_prod.descripcion) AS envase_descripcion,
        COALESCE(s.lote, prod.lote) AS lote,
        l.nombre AS linea_nombre
    FROM detalle_venta AS dv
    
    -- Joins para stock_productos_envasados (s)
    LEFT JOIN stock_productos_envasados AS s ON dv.stock_id = s.id
    LEFT JOIN recetas AS r_s ON s.receta_id = r_s.id
    LEFT JOIN envases AS e_s ON s.envase_id = e_s.id
    LEFT JOIN productos AS p_s ON r_s.id = p_s.id_receta AND e_s.id = p_s.envase_id
    LEFT JOIN lineas AS l_s ON p_s.linea_id = l_s.id
    
    -- Joins para producciones (prod/Bekim)
    LEFT JOIN producciones AS prod ON dv.stock_id = prod.id
    LEFT JOIN pedidos_produccion AS pp ON prod.pedido_id = pp.id
    LEFT JOIN recetas AS r_prod ON pp.receta_id = r_prod.id
    LEFT JOIN productos AS p_prod ON r_prod.id = p_prod.id_receta AND p_prod.cliente_id = pp.cliente_id
    LEFT JOIN envases AS e_prod ON p_prod.envase_id = e_prod.id
    LEFT JOIN lineas AS l_prod ON p_prod.linea_id = l_prod.id

    -- Se selecciona la línea priorizando stock_productos_envasados
    LEFT JOIN lineas AS l ON COALESCE(l_s.id, l_prod.id) = l.id
    
    WHERE dv.venta_id = ?;
    """
    return fetch_df(query, (venta_id,))

def anular_venta_y_revertir_stock(venta_id):
    """
    Anula una venta y revierte la cantidad de productos al stock o producciones (caso Bekim).
    Esta función maneja su propia conexión y transacción.
    """
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

            # Verificamos si el stock_id existe en stock_productos_envasados
            cursor.execute("SELECT id, cliente_id FROM stock_productos_envasados WHERE id = ?", (stock_id,))
            existe_stock_row = cursor.fetchone()

            if existe_stock_row:
                # Revertir stock en stock_productos_envasados
                cursor.execute(
                    "UPDATE stock_productos_envasados SET cantidad = cantidad + ? WHERE id = ?",
                    (cantidad_vendida, stock_id),
                )
            else:
                # Caso Bekim: revertimos estado en producciones
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
                    # Caso Bekim: Revertimos litros y estado
                    litros_a_revertir = cantidad_vendida * CAPACIDAD_TAMBOR
                    nueva_cantidad_litros = produccion['cantidad_real_litros'] + litros_a_revertir
                    
                    cursor.execute(
                        "UPDATE producciones SET cantidad_real_litros = ?, estado = 'producido' WHERE id = ?", 
                        (nueva_cantidad_litros, stock_id)
                    )
                elif produccion:
                    st.warning(f"Stock ID {stock_id} no encontrado en stock_productos_envasados ni como Bekim. Omitiendo reversión de stock.")
                    continue


            # Registrar movimiento de ingreso para ambos casos
            cursor.execute(
                """
                INSERT INTO movimientos_productos_envasados
                    (stock_id, tipo_movimiento, cantidad, fecha, observacion)
                VALUES (?, 'Ingreso', ?, ?, ?)
                """,
                (stock_id, cantidad_vendida, fecha_hoy, observacion),
            )

        # Marcar la venta como anulada
        cursor.execute("UPDATE ventas SET estado_venta = 'anulada' WHERE id = ?", (venta_id,))

        conn.commit()
        st.success("✅ Venta anulada y stock/producción restablecidos exitosamente.")

    except sqlite3.Error as e:
        st.error(f"❌ Ocurrió un error al anular la venta: {e}")
        conn.rollback()
    finally:
        conn.close()


def get_next_comprobante_number():
    """
    Obtiene el próximo número de comprobante basado en el último ID de la tabla de ventas,
    asegurando la comparación NUMÉRICA (CAST).
    
    Retorna: Una tupla (max_id_encontrado, siguiente_numero)
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # CORRECCIÓN CLAVE: Usar MAX(CAST(...)) para forzar la comparación numérica y COALESCE a 0 si es NULL.
    query = "SELECT COALESCE(MAX(CAST(numero_comprobante AS INTEGER)), 0) FROM ventas"
    
    cursor.execute(query)
    max_comp = cursor.fetchone()[0]
    conn.close()
    
    try:
        max_id = int(max_comp)
    except (TypeError, ValueError):
        # En caso de error inesperado, usar 0
        max_id = 0
        
    # Retorna el máximo encontrado y el siguiente número
    return max_id, max_id + 1

# =================================================================================================
# LÓGICA DE GENERACIÓN DE PDF CON REPORTLAB
# =================================================================================================

def generar_comprobante_pdf(comprobante_data):

    conn = get_connection()

    venta_id = comprobante_data["venta_id"]

    query = """
    SELECT
        dv.cantidad,
        dv.precio_unitario,
        dv.subtotal,
        COALESCE(r_s.nombre, r_p.nombre) AS producto_nombre,
        e.descripcion AS envase
    FROM detalle_venta dv

    LEFT JOIN stock_productos_envasados sp
        ON dv.stock_id = sp.id
    LEFT JOIN recetas r_s
        ON sp.receta_id = r_s.id
    LEFT JOIN envases e
        ON sp.envase_id = e.id

    LEFT JOIN producciones p
        ON dv.stock_id = p.id
    LEFT JOIN pedidos_produccion pp
        ON p.pedido_id = pp.id
    LEFT JOIN recetas r_p
        ON pp.receta_id = r_p.id

    WHERE dv.venta_id = ?
    """

    carrito_df = pd.read_sql_query(query, conn, params=(venta_id,))
    conn.close()

    # =========================
    # AGRUPAR PRODUCTO + ENVASE
    # =========================
    if "envase" not in carrito_df.columns:
        carrito_df["envase"] = ""

    carrito_df = carrito_df.groupby(
        ["producto_nombre","envase","precio_unitario"],
        dropna=False
    ).agg(
        cantidad=("cantidad","sum"),
        subtotal=("subtotal","sum")
    ).reset_index()

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
        allowSplitting=1
    )

    elements = []

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    titulo = styles["Heading2"]

    elements.append(Paragraph("Comprobante de Venta", titulo))
    elements.append(Spacer(1,12))

    elements.append(Paragraph(f"Número de Comprobante: {comprobante_data['numero_factura']}", normal))
    elements.append(Paragraph(f"Cliente: {comprobante_data['cliente_nombre']}", normal))
    elements.append(Paragraph(f"Dirección: {comprobante_data['cliente_contacto']}", normal))

    descuento_porcentaje = comprobante_data.get("descuento",0)

    if descuento_porcentaje > 0:
        elements.append(Paragraph(f"Descuento: {descuento_porcentaje}%", normal))

    elements.append(Paragraph(f"Fecha: {comprobante_data['fecha_salida']}", normal))
    elements.append(Spacer(1,20))

    data_table = [["Cantidad","Descripción","Precio Unitario","Total"]]

    # agregar productos al comprobante
    for _, row in carrito_df.iterrows():

        descripcion = str(row["producto_nombre"])

        if row["envase"]:
            descripcion = f"{descripcion} ({row['envase']})"

        data_table.append([
            f"{int(row['cantidad'])}",
            descripcion,
            f"${row['precio_unitario']:,.2f}",
            f"${row['subtotal']:,.2f}"
        ])

    # calcular subtotal desde la base
    subtotal_venta = carrito_df["subtotal"].sum()

    data_table.append(["","","Subtotal:",f"${subtotal_venta:,.2f}"])

    if descuento_porcentaje > 0:

        descuento_aplicado = subtotal_venta * (descuento_porcentaje/100)

        data_table.append([
            "",
            "",
            f"Descuento ({descuento_porcentaje}%):",
            f"-${descuento_aplicado:,.2f}"
        ])

        total_final = subtotal_venta - descuento_aplicado

    else:

        total_final = subtotal_venta

    data_table.append([
        "",
        "",
        "TOTAL (Final):",
        f"${total_final:,.2f}"
    ])

    table = Table(
        data_table,
        colWidths=[2.5*cm,9*cm,3.5*cm,3.5*cm],
        repeatRows=1,
        splitByRow=True
    )

    table.setStyle(TableStyle([

        ("BACKGROUND",(0,0),(-1,0),colors.grey),
        ("TEXTCOLOR",(0,0),(-1,0),colors.whitesmoke),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),

        ("ALIGN",(2,1),(-1,-1),"RIGHT"),

        ("GRID",(0,0),(-1,-1),1,colors.black),

        ("BACKGROUND",(2,-1),(-1,-1),colors.lightgrey),
        ("FONTNAME",(2,-1),(-1,-1),"Helvetica-Bold")

    ]))

    elements.append(table)

    doc.build(elements)

    buffer.seek(0)

    return buffer
        
def generar_orden_empaquetado_pdf(comprobante_data):

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    elements = []

    styles = getSampleStyleSheet()
    titulo = styles["Heading2"]
    normal = styles["Normal"]

    elements.append(Paragraph("Orden de Empaquetado", titulo))
    elements.append(Spacer(1,12))

    elements.append(Paragraph(f"Número de Comprobante: {comprobante_data['numero_factura']}", normal))
    elements.append(Paragraph(f"Cliente: {comprobante_data['cliente_nombre']}", normal))
    elements.append(Paragraph(f"Fecha: {comprobante_data['fecha_salida']}", normal))

    elements.append(Spacer(1,20))

    carrito_df = comprobante_data['carrito_df']

    RECETA_COL = 'producto_nombre' if 'producto_nombre' in carrito_df.columns else 'receta_nombre'
    envase_col = 'envase_descripcion' if 'envase_descripcion' in carrito_df.columns else 'envase'

    df_grouped_orden = carrito_df.groupby(
        [RECETA_COL, envase_col],
        dropna=False
    ).agg(
        cantidad=('cantidad', 'sum')
    ).reset_index()

    normal_style = styles['Normal']
    normal_style.fontSize = 10
    normal_style.leading = 12

    data_table = [['Cantidad', 'Producto (Receta)', 'Envase']]

    for _, row in df_grouped_orden.iterrows():

        data_table.append([
            f"{int(row['cantidad'])}",
            Paragraph(str(row[RECETA_COL]), normal_style),
            Paragraph(str(row[envase_col]), normal_style)
        ])

    table = Table(
        data_table,
        colWidths=[2.5*cm,7*cm,7*cm],
        repeatRows=1,
        splitByRow=True
    )

    table.setStyle(TableStyle([

        ('BACKGROUND',(0,0),(-1,0),colors.grey),
        ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),

        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),

        ('ALIGN',(0,0),(-1,-1),'LEFT'),
        ('VALIGN',(0,0),(-1,-1),'TOP'),

        ('GRID',(0,0),(-1,-1),1,colors.black),

        ('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),6),
        ('BOTTOMPADDING',(0,0),(-1,-1),6),

    ]))

    elements.append(table)

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

def ventas():
    st.title("💲 Gestión y Venta de Productos Envasados")

    clientes = fetch_df("SELECT id, nombre, contacto FROM clientes ORDER BY nombre")
    if clientes.empty:
        st.warning("No hay clientes registrados en la base de datos.")
        return

    tab1, tab2, tab3 = st.tabs(["💲 Gestión de Precios", "🛒 Venta de Productos Envasados", "📊 Historial y Comprobantes"])

    # Inicializar la cotización del dólar en session state
    if 'cotizacion_dolar' not in st.session_state:
        st.session_state.cotizacion_dolar = 1000.0 # Valor por defecto inicial
    if 'bekim_price_mode' not in st.session_state:
        st.session_state.bekim_price_mode = 'Precio en USD por Litro' # Valor por defecto inicial

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
        
        # --- Input para la cotización del dólar ---
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
        
        # --- CONFIGURACIÓN DE PRECIO BEKIM ---
        st.session_state.bekim_price_mode = st.radio(
            "Modalidad de Precio para Cliente 8 (Bekim) en la base de datos:",
            ['Precio en USD por Litro', 'Precio en USD por Tambor (200L)'],
            key='bekim_price_mode_radio',
            help="Seleccione cómo está cargado el 'precio_unitario' para Bekim en la tabla de precios."
        )

        # --- LLAMADA MODIFICADA: Pasar la cotización del dólar y el modo de precio ---
        df_stock_full = get_stock_df(cotizacion_dolar_actual, st.session_state.bekim_price_mode)
        
        if df_stock_full.empty:
            st.warning("No hay stock disponible para la venta.")
            
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

        # --- NUEVA LÓGICA PARA MOSTRAR EL TOTAL DE ENVASES DEL PRODUCTO SELECCIONADO ---
        if producto_filtro_stock != "Todos":
            # Se usa el df_stock_full (original) para sumar todos los lotes sin otros filtros.
            # La columna 'cantidad' en df_stock_full ya representa la cantidad de envases/tambores.
            df_producto_total = df_stock_full[df_stock_full["producto"] == producto_filtro_stock]
            total_envases = df_producto_total["cantidad"].sum()
            
            # Mostrar el total usando st.metric
            st.metric(
                label=f"Total Stock para {producto_filtro_stock}", 
                value=f"📦 {int(total_envases)} Envases/Tambores"
            )
        # -----------------------------------------------------------------------------------


        df_stock = df_stock_full.copy()
        if cliente_filtro_stock_display != "Todos":
            # Filtrar por la columna 'cliente_display' que maneja el 'Sin asignar'
            df_stock = df_stock[df_stock["cliente_display"] == cliente_filtro_stock_display]
        if producto_filtro_stock != "Todos":
            df_stock = df_stock[df_stock["producto"] == producto_filtro_stock]
        if envase_filtro_stock != "Todos":
            df_stock = df_stock[df_stock["envase"] == envase_filtro_stock]

        if df_stock.empty:
            st.warning("No hay stock disponible para los filtros seleccionados.")

        df_stock["Litros"] = (df_stock["cantidad"] * df_stock["capacidad_litros"]).round(2)
        df_stock["Envases"] = df_stock["cantidad"].astype(int)
        
        # Columns used for display and AgGrid selection
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
                    # --- INICIO DE LA CORRECCIÓN ROBUSTA DE MATCHING (safe_str) ---
                    fila_cliente = safe_str(fila.get("cliente"))
                    fila_producto = safe_str(fila.get("producto"))
                    fila_envase = safe_str(fila.get("envase"))
                    fila_linea = safe_str(fila.get("linea"))
                    fila_lote = safe_str(fila.get("lote"))
                    
                    # Aplicar la estandarización a las columnas de df_stock en tiempo de ejecución
                    match_condition = (
                        (df_stock["cliente"].apply(safe_str) == fila_cliente) &
                        (df_stock["producto"].apply(safe_str) == fila_producto) &
                        (df_stock["envase"].apply(safe_str) == fila_envase) &
                        (df_stock["linea"].apply(safe_str) == fila_linea) &
                        (df_stock["lote"].apply(safe_str) == fila_lote)
                    )
                    
                    # Aplicar la condición
                    stock_info_match = df_stock[match_condition]
                    
                    # --- FIN DE LA CORRECCIÓN ROBUSTA DE MATCHING ---
                    
                    if stock_info_match.empty:
                        st.error(f"Error: No se encontró la información completa del stock para {fila['producto']} - {fila['envase']} (Lote: {fila['lote']}). Omita la selección.")
                        valid_input = False
                        continue
                        
                    stock_info = stock_info_match.iloc[0]
                    cantidad_en_carrito = 0
                    for item in st.session_state.carrito:
                        if item["stock_id"] == stock_info["stock_id"] and item["lote"] == stock_info["lote"]:
                            cantidad_en_carrito = item["cantidad"]
                            break
                    max_disponible = int(stock_info["Envases"]) - cantidad_en_carrito
                    if max_disponible <= 0:
                        st.warning(f"No hay stock disponible adicional para {fila['producto']} - {fila['envase']} (Lote {fila['lote']}) ya en carrito.")
                        cantidad_input = 0
                    else:
                        cantidad_input = st.number_input(
                            label=f"Cantidad a vender: {fila['producto']} | Envase: {fila['envase']} | Lote: {fila['lote']} (Disp.={max_disponible})",
                            min_value=1,
                            max_value=max_disponible,
                            value=1,
                            step=1,
                            key=f"cantidad_{i}"
                        )
                    if cantidad_input == 0 and max_disponible > 0:
                        valid_input = False
                    cantidades.append(cantidad_input)
                agregar = st.form_submit_button("Agregar al carrito")
                if agregar:
                    if not valid_input:
                        st.error("Corrija las cantidades antes de agregar al carrito. Hay productos sin stock disponible o con errores de coincidencia.")
                    else:
                        for i, fila in enumerate(selected_rows):
                            # Se repite la lógica de match (asegurando el safe_str)
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
                                continue # No debería pasar si valid_input fue True, pero es una protección
                                
                            stock_info = stock_info_match.iloc[0]
                            stock_id = int(stock_info["stock_id"])
                            cliente_id = int(stock_info["cliente_id"]) if pd.notna(stock_info["cliente_id"]) else None
                            producto_id = int(stock_info["producto_id"])
                            envase_id = int(stock_info["envase_id"])
                            lote = stock_info["lote"]
                            linea = stock_info["linea"]
                            receta_id = stock_info["receta_id"]
                            
                            precio = None
                            
                            # --- LÓGICA DE PRECIO PARA CLIENTE 8 Y OTROS ---
                            if cliente_id == bekim_id:
                                # Para Cliente 8, el precio unitario es el precio total en ARS por tambor (ya convertido)
                                precio = stock_info["precio_total_ars_por_tambor"] 
                                
                                if pd.isna(precio) or precio <= 0:
                                    st.warning(f"No se pudo calcular el precio en ARS para {fila['producto']} - {fila['envase']} (Lote {fila['lote']}) con la cotización actual. Asegúrese de que el precio unitario USD esté cargado en la tabla de precios.")
                                    continue
                            else:
                                # Para otros clientes, usar la tabla de precios
                                if cliente_id is None:
                                    st.warning(f"No se puede agregar {fila['producto']} - {fila['envase']} (Lote {fila['lote']}) al carrito porque no tiene un cliente asignado para determinar el precio.")
                                    continue
                                precio = obtener_precio(cliente_id, producto_id, envase_id)
                                if precio is None or precio <= 0:
                                    st.warning(f"No hay precio definido para {fila['producto']} - {fila['envase']} para el cliente {fila['cliente']}. No se agregó al carrito.")
                                    continue
                            # ---------------------------------------------------
                            
                            item_existente = None
                            for item in st.session_state.carrito:
                                # Se debe considerar el precio unitario en el matching para el carrito!
                                if item["stock_id"] == stock_id and item["lote"] == lote and item["precio_unitario"] == precio:
                                    item_existente = item
                                    break
                            
                            if item_existente:
                                nueva_cant = item_existente["cantidad"] + cantidades[i]
                                if nueva_cant <= int(stock_info["Envases"]):
                                    item_existente["cantidad"] = nueva_cant
                                else:
                                    st.warning(f"No se puede agregar más de {int(stock_info['Envases'])} envases para {fila['producto']} - {fila['envase']} (lote {lote}).")
                            else:
                                # AÑADIR LA RECETA AL CARRITO PARA EL PDF
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
                                    "receta_nombre": stock_info["receta"], # <--- CORRECCIÓN APLICADA AQUÍ
                                })
                        st.success("Productos agregados al carrito con éxito.")

        st.subheader("🛒 Carrito de ventas actual")
        if st.session_state.carrito:
            carrito_df = pd.DataFrame(st.session_state.carrito)
            
            # NUEVO: Calcular el total del ítem para mostrarlo en la tabla
            carrito_df["Total Item"] = (carrito_df["precio_unitario"] * carrito_df["cantidad"]).round(2)
            
            # Formato y Edición del Carrito (se incluye "Total Item")
            # Se incluye 'receta_nombre' para que se muestre en el carrito, aunque se puede quitar si no se desea ver.
            cols_display = ["cliente", "receta_nombre", "envase", "linea", "lote", "cantidad", "precio_unitario", "Total Item"]
            # Se usa .get() con fallback para evitar errores si la columna aún no existe en el carrito cargado de una sesión vieja.
            cols_to_display = [col for col in cols_display if col in carrito_df.columns]

            carrito_df_display = carrito_df[cols_to_display].copy()
            
            # CAMBIO CLAVE: Permite la edición del precio unitario y muestra el total del item
            edited_df = st.data_editor(
                carrito_df_display,
                column_config={
                    "receta_nombre": "Receta",
                    "precio_unitario": st.column_config.NumberColumn(
                        "Precio Unitario (Modificable)",
                        min_value=0.01,
                        format="%.2f"
                    ),
                    # NUEVO: Columna Total Item (Solo lectura, para visualización)
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

            # Actualizar el carrito en session_state y calcular totales
            if "carrito_editor" in st.session_state and isinstance(st.session_state.carrito_editor, pd.DataFrame):
                # Usar el DataFrame editado para el cálculo, manteniendo los metadatos
                # El índice i del edited_df se corresponde con el índice del st.session_state.carrito
                for i, row in edited_df.iterrows():
                    st.session_state.carrito[i]["precio_unitario"] = row["precio_unitario"]

            # Recalcular el total después de la edición
            carrito_df_final = pd.DataFrame(st.session_state.carrito)
            carrito_df_final["total"] = carrito_df_final["precio_unitario"] * carrito_df_final["cantidad"]
            total_carrito = carrito_df_final["total"].sum()
            
            st.metric("Total acumulado de la venta (Subtotal)", f"${total_carrito:,.2f}")
            
            st.subheader("Administrar carrito")
            
            # Lógica para eliminar un producto (se mantiene)
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
                    st.success("Elemento eliminado del carrito. Recargando...")
                    st.rerun()
            else:
                st.info("El carrito está vacío.")


            st.subheader("Datos para finalizar la venta")
            
            # --- LLAMADA CORREGIDA PARA OBTENER EL NÚMERO DE COMPROBANTE ---
            max_comp_found, next_comprobante = get_next_comprobante_number()
            
            # --- MENSAJE DE DIAGNÓSTICO (Ayuda a ver qué número está recuperando la DB) ---
            st.markdown(f"**Diagnóstico de Comprobante:** Máximo encontrado en DB: `{max_comp_found}`")
            st.info(f"El número de comprobante para esta venta será: **{next_comprobante}**")
            # -------------------------------------------------------------------------------


            revendedores_df = fetch_df("SELECT id, nombre, contacto, descuento FROM revendedores")
            revendedor_id_map = {row['nombre']: row['id'] for index, row in revendedores_df.iterrows()}
            revendedor_nombre = st.selectbox("Seleccione el revendedor:", list(revendedor_id_map.keys()), key="revendedor_final_venta")
            revendedor_id = revendedor_id_map.get(revendedor_nombre)
            
            # Obtener el descuento predefinido
            revendedor_descuento_predefinido = 0.0
            if revendedor_id:
                revendedor_descuento_predefinido = revendedores_df[revendedores_df['id'] == revendedor_id]['descuento'].iloc[0]
            
            # Usar un campo de entrada para el descuento
            descuento_a_aplicar = st.number_input(
                "Porcentaje de descuento a aplicar (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(revendedor_descuento_predefinido),
                step=0.01,
                format="%.2f"
            )

            # El subtotal ya fue calculado con los precios modificados
            subtotal_venta = total_carrito
            
            total_con_descuento = subtotal_venta * (1 - descuento_a_aplicar / 100)
            
            st.metric("Total de la venta con descuento (Calculado)", f"${total_con_descuento:,.2f}")
            
            # Mantenido: Campo para el Importe final manual
            total_final_manual = st.number_input(
                "💰 **Importe FINAL a facturar/comprobante (Opcional):** Si se ingresa, este valor anula el total calculado.",
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.2f",
                key="total_final_manual"
            )
            
            # Lógica para determinar el total real a usar
            total_final_aplicado = total_con_descuento
            if total_final_manual > 0:
                total_final_aplicado = total_final_manual
                st.info(f"Se utilizará el importe manual de **${total_final_aplicado:,.2f}** como el Total Final de la venta y comprobante.")
            else:
                 st.info(f"Se utilizará el importe calculado de **${total_final_aplicado:,.2f}** como el Total Final de la venta y comprobante.")


            monto_pago = st.number_input("💵 Monto de dinero recibido:", min_value=0.0, format="%.2f")
            observacion_general = st.text_area("Observaciones generales para toda la venta (opcional)")
            
            if st.button("Finalizar venta"):
                if not revendedor_id:
                    st.error("Debe seleccionar un revendedor para finalizar la venta.")
                else:
                    # Se abre una única conexión para toda la transacción
                    conn = get_connection()
                    try:
                        cursor = conn.cursor()
                        
                        # 1. INSERT INTO ventas
                        cursor.execute("""
                            INSERT INTO ventas (fecha_venta, cliente_id, revendedor_id, observacion, numero_comprobante, total_venta)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (date.today().strftime("%Y-%m-%d"), revendedor_id, revendedor_id, observacion_general, next_comprobante, total_final_aplicado))
                        venta_id = cursor.lastrowid
                        
                        # Usamos carrito_df_final que tiene los precios unitarios actualizados
                        for index, item in carrito_df_final.iterrows():
                            subtotal_item = item["total"] # Usamos el total calculado con el precio modificado
                            
                            # 2. INSERT INTO detalle_venta
                            # Aseguramos que el precio_unitario guardado en detalle_venta sea el modificado
                            cursor.execute("""
                                INSERT INTO detalle_venta (venta_id, stock_id, cantidad, precio_unitario, subtotal)
                                VALUES (?, ?, ?, ?, ?)
                            """, (venta_id, item["stock_id"], item["cantidad"], item["precio_unitario"], subtotal_item))
                            
                            # 3. Registro de salida y actualización de stock
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
                        
                        # COMMIT final para todas las operaciones
                        conn.commit()
                        st.success("🎉 Venta registrada con éxito!")

                        revendedor_info = revendedores_df[revendedores_df['id'] == revendedor_id].iloc[0]
                        
                        # Pasa el DF final con los precios/totales correctos
                        comprobante_data = {
                            "venta_id": venta_id,
                            "cliente_nombre": revendedor_info["nombre"],
                            "cliente_contacto": revendedor_info["contacto"],
                            "numero_factura": next_comprobante,
                            #"carrito_df": carrito_df_final.copy(), # Pasa el DF con los precios editados
                            "fecha_salida": datetime.now().strftime('%d/%m/%Y %H:%M'),
                            "descuento": descuento_a_aplicar,
                            "total_final_calculado": total_con_descuento,
                            "total_final_aplicado": total_final_aplicado
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

        # --- Filtro por revendedor ---
        df_revendedores_historial = df_historial_completo[['revendedor_id', 'revendedor_nombre']].drop_duplicates().sort_values('revendedor_nombre')
        df_revendedores_historial['revendedor_nombre'] = df_revendedores_historial['revendedor_nombre'].fillna('Revendedor sin nombre').replace('', 'Revendedor sin nombre')
        revendedores_nombres = ['Todos'] + df_revendedores_historial['revendedor_nombre'].tolist()
        revendedor_id_map = dict(zip(df_revendedores_historial['revendedor_nombre'], df_revendedores_historial['revendedor_id']))

        st.write("---")
        st.subheader("Filtrar y Seleccionar Comprobante")
        
        # --- FILTROS ---
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
            # Nuevo filtro por estado de venta
            estado_filtro = st.selectbox(
                "Filtrar por Estado",
                ['Todos', 'activa', 'anulada'],
                key="estado_historial_filtro"
            )

        cliente_historial_filtro = st.selectbox("Filtrar por Revendedor", revendedores_nombres, key="cliente_historial_filtro")
        
        # --- APLICAR FILTROS INICIALES ---
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

        # --- Resumen por comprobante incluyendo venta_id ---
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
        
        # --- APLICAR FILTROS DE FECHA Y ESTADO ---
        df_resumen['fecha_venta_dt'] = pd.to_datetime(df_resumen['fecha_venta'])
        df_filtrado = df_resumen[df_resumen['fecha_venta_dt'].dt.date.between(fecha_inicio, fecha_fin)]
        
        if estado_filtro != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['estado_venta'] == estado_filtro]
        # ---------------------------------------------
        
        if df_filtrado.empty:
            st.warning("No se encontraron comprobantes con los filtros aplicados.")
            return

        # --- Grid para selección ---
        gb = GridOptionsBuilder.from_dataframe(df_filtrado)
        gb.configure_column("numero_comprobante", header_name="Nº Comprobante", min_width=150)
        gb.configure_column("revendedor_nombre", header_name="Nombre del Revendedor", min_width=200)
        gb.configure_column("fecha_venta", header_name="Fecha de Venta", min_width=150)
        gb.configure_column("total_venta", header_name="Total ($)", min_width=100)
        gb.configure_column("revendedor_contacto", hide=True)
        gb.configure_column("venta_id", hide=True)
        gb.configure_column("fecha_venta_dt", hide=True)
        gb.configure_column("revendedor_descuento", hide=True) # El descuento no es relevante en la tabla
        # Se asegura el formato correcto de la regla CSS para el estado
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

        # --- Lógica de selección y anulación (con corrección de DataFrame) ---
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
                # Se utiliza el campo 'revendedor_descuento' del df_historial_completo
                descuento_aplicado = selected_row.get('revendedor_descuento', 0)


                st.write(f"**Cliente:** {cliente_nombre}")
                st.write(f"**Fecha:** {fecha_venta}")
                st.write(f"**Estado de la Venta:** {estado_venta.capitalize()}")
                if descuento_aplicado > 0:
                    st.write(f"**Descuento predefinido:** {descuento_aplicado}%")

                df_mostrar = df_comp[['producto_nombre', 'envase_descripcion', 'lote', 'cantidad', 'precio_unitario']].copy()
                df_mostrar['Subtotal'] = df_mostrar['cantidad'] * df_mostrar['precio_unitario']
                subtotal_venta_comp = df_mostrar['Subtotal'].sum()
                
                st.dataframe(df_mostrar.rename(columns={
                    'producto_nombre': 'Receta',
                    'envase_descripcion': 'Envase',
                    'cantidad': 'Cantidad',
                    'precio_unitario': 'Precio Unitario'
                }), use_container_width=True)

                total_final_aplicado_db = df_comp['total_venta'].iloc[0]
                st.metric("Total de la Venta (Registrado)", f"${total_final_aplicado_db:,.2f}")

                col_btn1, col_btn2, col_btn3 = st.columns(3)

                with col_btn1:
                    if estado_venta == 'activa' and venta_id:
                        if st.button(f"Anular Venta Nº {numero_comp}"):
                            anular_venta_y_revertir_stock(venta_id)
                            st.rerun()
                    else:
                        st.info("Esta venta ya ha sido anulada.")

                with col_btn2:
                    # Se usa el total guardado en DB para el PDF (total_final_aplicado_db)
                    comprobante_data = {
                        "venta_id": venta_id,
                        "cliente_nombre": cliente_nombre,
                        "cliente_contacto": cliente_contacto,
                        "numero_factura": numero_comp,
                        #"carrito_df": df_comp.copy(),
                        "fecha_salida": fecha_venta,
                        "descuento": descuento_aplicado,
                        "total_final_aplicado_db": total_final_aplicado_db # Nuevo campo para re-generación
                    }
                    pdf_comprobante = generar_comprobante_pdf(comprobante_data)
                    st.download_button(
                        label="Generar PDF Comprobante",
                        data=pdf_comprobante.getvalue(),
                        file_name=f"comprobante_venta_{numero_comp}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

                with col_btn3:
                    comprobante_data_orden = {
                        "cliente_nombre": cliente_nombre,
                        "cliente_contacto": cliente_contacto,
                        "numero_factura": numero_comp,
                        "carrito_df": df_comp.copy(),
                        "fecha_salida": fecha_venta
                    }
                    pdf_orden_empaquetado = generar_orden_empaquetado_pdf(comprobante_data_orden)
                    st.download_button(
                        label="Generar PDF Orden",
                        data=pdf_orden_empaquetado.getvalue(),
                        file_name=f"orden_empaquetado_{numero_comp}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
        else:
            st.info("Seleccione un comprobante de la tabla para ver sus detalles y descargar los PDFs.")
            
def main():
    st.set_page_config(layout="wide")
    ventas()

if __name__ == "__main__":
    main()