import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime

# ==============================================================================
# FUNCIÓN CORREGIDA: Costo de Producción Mensual (USA AVG(precio_unitario))
# ==============================================================================
def reporte_costo_produccion():
    st.subheader("Reporte de Costo de Producción por Mes (Materia Prima Estimado en USD)")
    conn = sqlite3.connect('minerva.db')

    # 1. Obtener meses disponibles para el filtro
    meses_df = pd.read_sql_query("SELECT DISTINCT strftime('%Y-%m', fecha) AS mes FROM producciones ORDER BY mes DESC", conn)
    meses_disponibles = meses_df['mes'].tolist()

    if not meses_disponibles:
        st.info("No hay registros de producción para generar el reporte.")
        conn.close()
        return

    # 2. Filtrar por mes
    mes_seleccionado = st.selectbox("Seleccionar Mes (YYYY-MM)", meses_disponibles)
    
    # 3. Consulta SQL con la NUEVA LÓGICA DE COSTO
    query = f"""
    -- 1. Costo Promedio Unitario de cada Materia Prima (SOLO USD)
    -- *** LÓGICA CORREGIDA: Usa el promedio del precio_unitario para evitar errores de cantidad/total ***
    WITH CostoPromedioMP AS (
        SELECT
            materia_prima_id,
            -- Calcula el costo promedio usando el precio unitario de las compras en USD
            AVG(CASE
                WHEN moneda = 'USD' THEN precio_unitario
                ELSE NULL
            END) AS CostoUnitarioPromedio_USD
        FROM compras_materia_prima
        GROUP BY materia_prima_id
        -- Solo incluimos MP con al menos un precio en USD
        HAVING AVG(CASE WHEN moneda = 'USD' THEN precio_unitario ELSE NULL END) IS NOT NULL
    ),
    -- 2. Costo Total de Materia Prima por Unidad Base (Litro) de cada Receta
    CostoRecetaPorUnidad AS (
        SELECT
            cri.receta_id,
            -- Cálculo: Cantidad de MP en receta * Costo Unitario de MP
            SUM(cri.cantidad * cmp.CostoUnitarioPromedio_USD) 
            / 200.0 AS Costo_MP_Por_Litro 
            -- NORMALIZACIÓN: Dividimos por los 200.0 LITROS de producto final
        FROM
            receta_ingredientes cri
        JOIN
            CostoPromedioMP cmp ON cri.materia_prima_id = cmp.materia_prima_id
        GROUP BY
            cri.receta_id
    )
    -- 3. Agregación de Producción por Mes y Receta con el Costo Calculado
    SELECT
        strftime('%Y-%m', p.fecha) AS Mes_Produccion,
        r.nombre AS Producto,
        SUM(p.cantidad_real_litros) AS Litros_Totales_Producidos,
        -- Costo Total Estimado: Litros Producidos * Costo_MP_Por_Litro
        SUM(p.cantidad_real_litros * crl.Costo_MP_Por_Litro) AS Costo_Total_MP_Estimado
    FROM
        producciones p
    JOIN
        pedidos_produccion pp ON p.pedido_id = pp.id
        LEFT JOIN clientes c ON pp.cliente_id = c.id
        LEFT JOIN recetas r ON pp.receta_id = r.id
    JOIN
        CostoRecetaPorUnidad crl ON r.id = crl.receta_id
    WHERE
        Mes_Produccion = ?
    GROUP BY
        Mes_Produccion, Producto
    ORDER BY
        Litros_Totales_Producidos DESC;
    """

    # Ejecutar la consulta con el mes seleccionado
    df = pd.read_sql_query(query, conn, params=[mes_seleccionado])
    conn.close()

    # 4. Formateo y Visualización de datos
    if df.empty:
        st.info(f"No hay datos de producción o costos asociados (compras de MP en USD) para el mes de {mes_seleccionado}.")
        return

    df['Costo_Total_MP_Estimado'] = df['Costo_Total_MP_Estimado'].round(2)
    
    st.markdown("---")
    st.markdown("#### Detalle de Producción Mensual por Receta (en USD)")
    st.dataframe(df.style.format({
        'Litros_Totales_Producidos': '{:,.2f} L'.format,
        'Costo_Total_MP_Estimado': 'U$S {:,.2f}'.format
    }), use_container_width=True)
    
    # 5. Descarga
    st.download_button(
        "Descargar CSV del Reporte", 
        df.to_csv(index=False).encode('utf-8'), 
        f"costo_produccion_usd_{mes_seleccionado}.csv", 
        "text/csv"
    )

    # 6. Gráfico
    total_costo_mes = df['Costo_Total_MP_Estimado'].sum()
    st.markdown(f"### 💸 Costo Total Estimado de MP del Mes ({mes_seleccionado}) en USD: **U$S {total_costo_mes:,.2f}**")
    
    fig = px.bar(
        df, 
        x='Producto', 
        y='Costo_Total_MP_Estimado',
        color='Litros_Totales_Producidos',
        title=f"Costo Total de Materia Prima por Receta en {mes_seleccionado} (USD)",
        labels={
            'Costo_Total_MP_Estimado': 'Costo Total MP Estimado (U$S)',
            'Litros_Totales_Producidos': 'Litros Producidos'
        },
        height=500
    )
    st.plotly_chart(fig, use_container_width=True)


# ==============================================================================
# REPORTES EXISTENTES (Se mantienen sin cambios)
# ==============================================================================

def reporte_compras_materia_prima():
    st.subheader("Reporte de Compras de Materia Prima")
    conn = sqlite3.connect('minerva.db')
    proveedores = pd.read_sql_query("SELECT nombre FROM proveedores ORDER BY nombre", conn)
    materias = pd.read_sql_query("SELECT nombre FROM materias_primas ORDER BY nombre", conn)
    col1, col2, col3 = st.columns(3)
    with col1:
        proveedor = st.selectbox("Proveedor", ["Todos"] + proveedores['nombre'].tolist())
    with col2:
        materia = st.selectbox("Materia Prima", ["Todos"] + materias['nombre'].tolist())
    with col3:
        fecha_ini = st.date_input("Desde", pd.to_datetime("2025-01-01"))
        fecha_fin = st.date_input("Hasta", pd.to_datetime("today"))
    query = """
        SELECT c.fecha, p.nombre AS proveedor, m.nombre AS materia_prima,
               c.cantidad, c.precio_unitario, c.costo_total, c.moneda, c.cotizacion_usd, c.numero_comprobante
        FROM compras_materia_prima c
        JOIN proveedores p ON c.proveedor_id = p.id
        JOIN materias_primas m ON c.materia_prima_id = m.id
        WHERE date(c.fecha) BETWEEN ? AND ?
    """
    params = [str(fecha_ini), str(fecha_fin)]
    if proveedor != "Todos":
        query += " AND p.nombre = ?"
        params.append(proveedor)
    if materia != "Todos":
        query += " AND m.nombre = ?"
        params.append(materia)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    st.dataframe(df)
    st.download_button("Descargar CSV", df.to_csv(index=False).encode('utf-8'), "compras_materia_prima.csv", "text/csv")
    if not df.empty:
        df['fecha'] = pd.to_datetime(df['fecha'])
        df['mes'] = df['fecha'].dt.to_period('M').astype(str)
        resumen = df.groupby('mes')['costo_total'].sum().reset_index()
        fig = px.bar(resumen, x='mes', y='costo_total', title="Total Comprado por Mes", labels={'mes': 'Mes', 'costo_total': 'Total ($)'})
        st.plotly_chart(fig, use_container_width=True)
        resumen_prov = df.groupby('proveedor')['costo_total'].sum().reset_index()
        fig2 = px.pie(resumen_prov, values='costo_total', names='proveedor', title="Distribución de Compras por Proveedor")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No hay datos para los filtros seleccionados.")

def reporte_compras_envases():
    st.subheader("Reporte de Compras de Envases")
    conn = sqlite3.connect('minerva.db')
    proveedores = pd.read_sql_query("SELECT nombre FROM proveedores ORDER BY nombre", conn)
    envases = pd.read_sql_query("SELECT descripcion FROM envases ORDER BY descripcion", conn)
    col1, col2, col3 = st.columns(3)
    with col1:
        proveedor = st.selectbox("Proveedor", ["Todos"] + proveedores['nombre'].tolist(), key='prov_env')
    with col2:
        envase = st.selectbox("Envase", ["Todos"] + envases['descripcion'].tolist(), key='env_env')
    with col3:
        fecha_ini = st.date_input("Desde", pd.to_datetime("2025-01-01"), key='fecha_env_ini')
        fecha_fin = st.date_input("Hasta", pd.to_datetime("today"), key='fecha_env_fin')
    query = """
        SELECT e.fecha_ingreso, p.nombre AS proveedor, v.descripcion AS envase,
               e.cantidad_ingresada, e.precio_unitario, e.numero_comprobante
        FROM entradas_envases e
        JOIN proveedores p ON e.proveedor_id = p.id
        JOIN envases v ON e.envase_id = v.id
        WHERE date(e.fecha_ingreso) BETWEEN ? AND ?
    """
    params = [str(fecha_ini), str(fecha_fin)]
    if proveedor != "Todos":
        query += " AND p.nombre = ?"
        params.append(proveedor)
    if envase != "Todos":
        query += " AND v.descripcion = ?"
        params.append(envase)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    st.dataframe(df)
    st.download_button("Descargar CSV", df.to_csv(index=False).encode('utf-8'), "compras_envases.csv", "text/csv")
    if not df.empty:
        df['fecha_ingreso'] = pd.to_datetime(df['fecha_ingreso'])
        df['mes'] = df['fecha_ingreso'].dt.to_period('M').astype(str)
        resumen = df.groupby('mes')['cantidad_ingresada'].sum().reset_index()
        fig = px.bar(resumen, x='mes', y='cantidad_ingresada', title="Cantidad de Envases Comprados por Mes", labels={'mes': 'Mes', 'cantidad_ingresada': 'Cantidad'})
        st.plotly_chart(fig, use_container_width=True)
        resumen_env = df.groupby('envase')['cantidad_ingresada'].sum().reset_index()
        fig2 = px.pie(resumen_env, values='cantidad_ingresada', names='envase', title="Distribución de Compras por Tipo de Envase")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No hay datos para los filtros seleccionados.")

def reporte_stock_materias_primas():
    st.subheader("Reporte de Stock de Materias Primas")
    conn = sqlite3.connect('minerva.db')
    df = pd.read_sql_query("""
        SELECT m.nombre AS materia_prima, s.cantidad_actual, m.unidad
        FROM stock_materias_primas s
        JOIN materias_primas m ON s.materia_prima_id = m.id
        ORDER BY m.nombre
    """, conn)
    conn.close()
    st.dataframe(df)
    st.download_button("Descargar CSV", df.to_csv(index=False).encode('utf-8'), "stock_materias_primas.csv", "text/csv")
    if not df.empty:
        fig = px.bar(df, x='materia_prima', y='cantidad_actual', title="Stock Actual de Materias Primas", labels={'materia_prima': 'Materia Prima', 'cantidad_actual': 'Stock'})
        st.plotly_chart(fig, use_container_width=True)

def reporte_stock_envases():
    st.subheader("Reporte de Stock de Envases por Cliente")
    conn = sqlite3.connect('minerva.db')
    df = pd.read_sql_query("""
        SELECT c.nombre AS cliente, v.descripcion AS envase, s.cantidad
        FROM stock_envases_clientes s
        JOIN clientes c ON s.cliente_id = c.id
        JOIN envases v ON s.envase_id = v.id
        ORDER BY c.nombre, v.descripcion
    """, conn)
    conn.close()
    st.dataframe(df)
    st.download_button("Descargar CSV", df.to_csv(index=False).encode('utf-8'), "stock_envases_clientes.csv", "text/csv")
    if not df.empty:
        fig = px.bar(df, x='envase', y='cantidad', color='cliente', title="Stock Actual de Envases por Cliente", labels={'envase': 'Envase', 'cantidad': 'Stock'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay datos de stock de envases por cliente.")

def reporte_movimientos_materia_prima():
    st.subheader("Movimientos de Materia Prima")
    conn = sqlite3.connect('minerva.db')
    materias = pd.read_sql_query("SELECT nombre FROM materias_primas ORDER BY nombre", conn)
    materia = st.selectbox("Materia Prima", ["Todos"] + materias['nombre'].tolist(), key='mov_mp')
    query = """
        SELECT m.nombre AS materia_prima, mm.fecha, mm.lote, mm.cantidad, mm.tipo_movimiento, mm.destino
        FROM movimientos_materia_prima mm
        JOIN materias_primas m ON mm.materia_prima_id = m.id
    """
    params = []
    if materia != "Todos":
        query += " WHERE m.nombre = ?"
        params.append(materia)
    query += " ORDER BY mm.fecha DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    st.dataframe(df)
    st.download_button("Descargar CSV", df.to_csv(index=False).encode('utf-8'), "movimientos_materia_prima.csv", "text/csv")
def reporte_movimientos_envases():
    st.subheader("Movimientos de Envases")
    conn = sqlite3.connect('minerva.db')
    envases = pd.read_sql_query("SELECT descripcion FROM envases ORDER BY descripcion", conn)
    envase = st.selectbox("Envase", ["Todos"] + envases['descripcion'].tolist(), key='mov_env')
    query = """
        SELECT v.descripcion AS envase, me.fecha, me.cantidad, me.tipo_movimiento, me.observacion
        FROM movimientos_envases me
        JOIN envases v ON me.envase_id = v.id
    """
    params = []
    if envase != "Todos":
        query += " WHERE v.descripcion = ?"
        params.append(envase)
    query += " ORDER BY me.fecha DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    st.dataframe(df)
    st.download_button("Descargar CSV", df.to_csv(index=False).encode('utf-8'), "movimientos_envases.csv", "text/csv")

def reporte_produccion():
    st.subheader("Reporte de Producción")
    conn = sqlite3.connect('minerva.db')
    clientes = pd.read_sql_query("SELECT nombre FROM clientes ORDER BY nombre", conn)
    recetas = pd.read_sql_query("SELECT nombre FROM recetas ORDER BY nombre", conn)
    col1, col2 = st.columns(2)
    with col1:
        cliente = st.selectbox("Cliente", ["Todos"] + clientes['nombre'].tolist(), key='prod_cli')
    with col2:
        receta = st.selectbox("Receta", ["Todos"] + recetas['nombre'].tolist(), key='prod_rec')
    query = """
        SELECT pr.lote, pr.fecha, c.nombre AS cliente, r.nombre AS receta, pr.cantidad_litros, pr.estado
        FROM producciones pr
        JOIN pedidos_produccion pp ON pr.pedido_id = pp.id
        LEFT JOIN clientes c ON pp.cliente_id = c.id
        LEFT JOIN recetas r ON pp.receta_id = r.id
        WHERE 1=1
    """
    params = []
    if cliente != "Todos":
        query += " AND c.nombre = ?"
        params.append(cliente)
    if receta != "Todos":
        query += " AND r.nombre = ?"
        params.append(receta)
    query += " ORDER BY pr.fecha DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    st.dataframe(df)
    st.download_button("Descargar CSV", df.to_csv(index=False).encode('utf-8'), "produccion.csv", "text/csv")
    if not df.empty:
        df['fecha'] = pd.to_datetime(df['fecha'])
        df['mes'] = df['fecha'].dt.to_period('M').astype(str)
        resumen = df.groupby('mes')['cantidad_litros'].sum().reset_index()
        fig = px.bar(resumen, x='mes', y='cantidad_litros', title="Litros Producidos por Mes", labels={'mes': 'Mes', 'cantidad_litros': 'Litros'})
        st.plotly_chart(fig, use_container_width=True)

def reporte_envasado():
    st.subheader("Reporte de Órdenes de Envasado")
    conn = sqlite3.connect('minerva.db')
    envases = pd.read_sql_query("SELECT descripcion FROM envases ORDER BY descripcion", conn)
    envase = st.selectbox("Envase", ["Todos"] + envases['descripcion'].tolist(), key='rep_envase')
    query = """
        SELECT oe.fecha, pr.lote, pc.id AS producto_cliente_id, v.descripcion AS envase, oe.cantidad_unidades, oe.estado
        FROM ordenes_envasado oe
        JOIN producciones pr ON oe.produccion_id = pr.id
        JOIN productos_clientes pc ON oe.producto_cliente_id = pc.id
        JOIN envases v ON oe.envase_id = v.id
    """
    params = []
    if envase != "Todos":
        query += " WHERE v.descripcion = ?"
        params.append(envase)
    query += " ORDER BY oe.fecha DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    st.dataframe(df)
    st.download_button("Descargar CSV", df.to_csv(index=False).encode('utf-8'), "ordenes_envasado.csv", "text/csv")

def reporte_ventas():
    st.subheader("Reporte de Ventas")
    conn = sqlite3.connect('minerva.db')
    clientes = pd.read_sql_query("SELECT nombre FROM clientes ORDER BY nombre", conn)
    recetas = pd.read_sql_query("SELECT nombre FROM recetas ORDER BY nombre", conn)
    col1, col2 = st.columns(2)
    with col1:
        cliente = st.selectbox("Cliente", ["Todos"] + clientes['nombre'].tolist(), key='venta_cli')
    with col2:
        receta = st.selectbox("Receta", ["Todos"] + recetas['nombre'].tolist(), key='venta_rec')
    query = """
        SELECT sp.lote, sp.fecha_ingreso, c.nombre AS cliente, r.nombre AS receta, v.descripcion AS envase, sp.cantidad
        FROM stock_productos_envasados sp
        JOIN clientes c ON sp.cliente_id = c.id
        JOIN recetas r ON sp.receta_id = r.id
        JOIN envases v ON sp.envase_id = v.id
        WHERE 1=1
    """
    params = []
    if cliente != "Todos":
        query += " AND c.nombre = ?"
        params.append(cliente)
    if receta != "Todos":
        query += " AND r.nombre = ?"
        params.append(receta)
    query += " ORDER BY sp.fecha_ingreso DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    st.dataframe(df)
    st.download_button("Descargar CSV", df.to_csv(index=False).encode('utf-8'), "ventas.csv", "text/csv")
    if not df.empty:
        df['fecha_ingreso'] = pd.to_datetime(df['fecha_ingreso'])
        df['mes'] = df['fecha_ingreso'].dt.to_period('M').astype(str)
        resumen = df.groupby('mes')['cantidad'].sum().reset_index()
        fig = px.bar(resumen, x='mes', y='cantidad', title="Unidades Vendidas por Mes", labels={'mes': 'Mes', 'cantidad': 'Unidades'})
        st.plotly_chart(fig, use_container_width=True)

def reporte_costos():
    st.subheader("Reporte de Costos Asociados")
    conn = sqlite3.connect('minerva.db')
    materias = pd.read_sql_query("SELECT nombre FROM materias_primas ORDER BY nombre", conn)
    materia = st.selectbox("Materia Prima", ["Todos"] + materias['nombre'].tolist(), key='costo_mp')
    query = """
        SELECT m.nombre AS materia_prima, ca.tipo_costo, ca.monto, ca.fecha
        FROM costos_asociados ca
        JOIN materias_primas m ON ca.materia_prima_id = m.id
    """
    params = []
    if materia != "Todos":
        query += " WHERE m.nombre = ?"
        params.append(materia)
    query += " ORDER BY ca.fecha DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    st.dataframe(df)
    st.download_button("Descargar CSV", df.to_csv(index=False).encode('utf-8'), "costos_asociados.csv", "text/csv")

def reporte_cotizacion_dolar():
    st.subheader("Historial de Cotización de Dólar")
    conn = sqlite3.connect('minerva.db')
    df = pd.read_sql_query("""
        SELECT fecha_hora, compra, venta
        FROM cotizacion_dolar
        ORDER BY fecha_hora DESC
    """, conn)
    conn.close()
    st.dataframe(df)
    st.download_button("Descargar CSV", df.to_csv(index=False).encode('utf-8'), "cotizacion_dolar.csv", "text/csv")
    if not df.empty:
        df['fecha_hora'] = pd.to_datetime(df['fecha_hora'])
        fig = px.line(df, x='fecha_hora', y=['compra','venta'], title="Evolución de Cotización de Dólar", labels={'value': 'Cotización', 'fecha_hora': 'Fecha'})
        st.plotly_chart(fig, use_container_width=True)

# ==============================================================================
# FUNCIÓN PRINCIPAL DE REPORTES
# ==============================================================================
def modulo_reportes():
    st.title("Reportes del Sistema Minerva")
    reporte = st.selectbox(
        "Selecciona el tipo de reporte",
        [
            "Compras Materia Prima",
            "Compras Envases",
            "Stock Materias Primas",
            "Stock Envases",
            "Movimientos Materia Prima",
            "Movimientos Envases",
            "Producción",
            "**Costo de Producción Mensual** 👈", # NUEVO REPORTE
            "Órdenes de Envasado",
            "Ventas",
            "Costos Asociados",
            "Cotización Dólar"
        ]
    )
    if reporte == "Compras Materia Prima":
        reporte_compras_materia_prima()
    elif reporte == "Compras Envases":
        reporte_compras_envases()
    elif reporte == "Stock Materias Primas":
        reporte_stock_materias_primas()
    elif reporte == "Stock Envases":
        reporte_stock_envases()
    elif reporte == "Movimientos Materia Prima":
        reporte_movimientos_materia_prima()
    elif reporte == "Movimientos Envases":
        reporte_movimientos_envases()
    elif reporte == "Producción":
        reporte_produccion()
    elif reporte == "**Costo de Producción Mensual** 👈": # Manejador para el nuevo reporte
        reporte_costo_produccion()
    elif reporte == "Órdenes de Envasado":
        reporte_envasado()
    elif reporte == "Ventas":
        reporte_ventas()
    elif reporte == "Costos Asociados":
        reporte_costos()
    elif reporte == "Cotización Dólar":
        reporte_cotizacion_dolar()