import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, timedelta

# =================================================================================================
# CONFIGURACIÓN
# =================================================================================================
# La ruta a la base de datos debe ser consistente con su entorno.
DB_PATH = "minerva.db" 

# =================================================================================================
# UTILIDADES DB
# =================================================================================================

def get_connection():
    """Establece la conexión a la base de datos."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

@st.cache_data
def fetch_df(query, params=()):
    """Ejecuta una consulta SELECT y devuelve los resultados como un DataFrame de Pandas."""
    conn = get_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
    except sqlite3.Error as e:
        # Usar st.error solo si se llama desde un contexto de Streamlit visible
        #st.error(f"Error al ejecutar la consulta: {e}") 
        return pd.DataFrame()
    finally:
        conn.close()
    return df

@st.cache_data
def get_metadata():
    """Obtiene el rango de fechas, lista de revendedores, y lista de categorías de egreso."""
    # 1. Rango de fechas
    date_query = """
    SELECT MIN(fecha_venta) AS min_date, MAX(fecha_venta) AS max_date 
    FROM ventas;
    """
    date_df = fetch_df(date_query)
    min_date = pd.to_datetime(date_df['min_date'].iloc[0]).date() if not date_df.empty and date_df['min_date'].iloc[0] else date.today() - timedelta(days=365)
    max_date = pd.to_datetime(date_df['max_date'].iloc[0]).date() if not date_df.empty and date_df['max_date'].iloc[0] else date.today()

    # 2. Lista de Revendedores
    revendedores_query = "SELECT id, nombre FROM revendedores ORDER BY nombre;"
    revendedores_df = fetch_df(revendedores_query)
    
    # 3. Lista de Categorías de Imputación de Egreso (Destinos)
    categorias_query = """
    SELECT id, nombre 
    FROM categorias_imputacion 
    WHERE tipo = 'Egreso' OR nombre LIKE '%Proveedor%' OR nombre LIKE '%Sueldo%' 
    ORDER BY nombre;
    """
    categorias_df = fetch_df(categorias_query)
    
    return min_date, max_date, revendedores_df, categorias_df 

# =================================================================================================
# LÓGICA DE NEGOCIO (Consultas SQL)
# =================================================================================================

@st.cache_data
def get_total_deuda_global(fecha_inicio, fecha_fin, revendedor_ids=None):
    """Calcula el dinero total que nos deben, filtrando por rango y revendedor."""
    where_revendedor = ""
    params_rev = []
    if revendedor_ids:
        placeholders = ','.join('?' for _ in revendedor_ids)
        where_revendedor = f" AND T1.revendedor_id IN ({placeholders})"
        params_rev = revendedor_ids

    query = f"""
    SELECT 
        COALESCE(SUM(T1.total_venta), 0) - COALESCE(SUM(T2.importe_pagado), 0) AS Deuda_Total_Global
    FROM ventas AS T1
    LEFT JOIN pagos_comprobantes AS T2 ON T1.id = T2.venta_id
    WHERE T1.fecha_venta BETWEEN ? AND ?
    {where_revendedor};
    """
    params = [fecha_inicio.strftime("%Y-%m-%d"), fecha_fin.strftime("%Y-%m-%d")] + params_rev
    df = fetch_df(query, params)
    return df['Deuda_Total_Global'].iloc[0] if not df.empty else 0.0

@st.cache_data
def get_reseller_debt_summary(fecha_inicio, fecha_fin, revendedor_ids=None):
    """Calcula la deuda total y la fecha de la venta pendiente más antigua por revendedor."""
    where_revendedor = ""
    params_rev = []
    if revendedor_ids:
        placeholders = ','.join('?' for _ in revendedor_ids)
        where_revendedor = f" AND v.revendedor_id IN ({placeholders})"
        params_rev = revendedor_ids

    query = f"""
    WITH VentaPagos AS (
        SELECT
            v.id AS venta_id,
            v.revendedor_id,
            v.fecha_venta,
            v.total_venta,
            COALESCE(SUM(pc.importe_pagado), 0) AS pagos_aplicados
        FROM ventas AS v
        LEFT JOIN pagos_comprobantes AS pc ON v.id = pc.venta_id
        WHERE v.fecha_venta BETWEEN ? AND ?
        {where_revendedor}
        GROUP BY v.id, v.revendedor_id, v.fecha_venta, v.total_venta
    )
    SELECT
        r.nombre AS Revendedor,
        SUM(VP.total_venta - VP.pagos_aplicados) AS Deuda_Total,
        MIN(CASE WHEN VP.total_venta > VP.pagos_aplicados THEN VP.fecha_venta ELSE NULL END) AS Fecha_Venta_Mas_Antigua_Pendiente
    FROM revendedores AS r
    JOIN VentaPagos AS VP ON r.id = VP.revendedor_id
    GROUP BY r.nombre
    HAVING Deuda_Total > 0
    ORDER BY Fecha_Venta_Mas_Antigua_Pendiente ASC;
    """
    params = [fecha_inicio.strftime("%Y-%m-%d"), fecha_fin.strftime("%Y-%m-%d")] + params_rev
    return fetch_df(query, params)

@st.cache_data
def get_pending_sales_detail(fecha_inicio, fecha_fin, revendedor_ids=None):
    """Obtiene el detalle de cada venta con saldo pendiente."""
    where_revendedor = ""
    params_rev = []
    if revendedor_ids:
        placeholders = ','.join('?' for _ in revendedor_ids)
        where_revendedor = f" AND v.revendedor_id IN ({placeholders})"
        params_rev = revendedor_ids

    query = f"""
    SELECT
        v.id AS ID_Venta,
        r.nombre AS Revendedor,
        v.numero_comprobante AS Comprobante,
        v.fecha_venta AS Fecha_Venta,
        v.total_venta AS Monto_Original,
        COALESCE(SUM(pc.importe_pagado), 0) AS Pagos_Recibidos,
        (v.total_venta - COALESCE(SUM(pc.importe_pagado), 0)) AS Saldo_Pendiente,
        CAST(julianday('now') - julianday(v.fecha_venta) AS INTEGER) AS Dias_Atraso
    FROM ventas AS v
    JOIN revendedores AS r ON v.revendedor_id = r.id
    LEFT JOIN pagos_comprobantes AS pc ON v.id = pc.venta_id
    WHERE v.fecha_venta BETWEEN ? AND ?
    {where_revendedor}
    GROUP BY v.id, r.nombre, v.numero_comprobante, v.fecha_venta, v.total_venta
    HAVING Saldo_Pendiente > 0 
    ORDER BY Dias_Atraso DESC;
    """
    params = [fecha_inicio.strftime("%Y-%m-%d"), fecha_fin.strftime("%Y-%m-%d")] + params_rev
    return fetch_df(query, params)

@st.cache_data
def get_payment_imputations(fecha_inicio, fecha_fin, revendedor_ids=None, categoria_ids=None):
    """Rastrea cómo se utilizó el dinero de los pagos, ahora filtrando por Destino (Categoría) también."""
    where_revendedor = ""
    params_rev = []
    if revendedor_ids:
        placeholders = ','.join('?' for _ in revendedor_ids)
        where_revendedor = f" AND r.id IN ({placeholders})"
        params_rev = revendedor_ids

    where_categoria = ""
    params_cat = []
    if categoria_ids:
        placeholders = ','.join('?' for _ in categoria_ids)
        where_categoria = f" AND ci.id IN ({placeholders})"
        params_cat = categoria_ids

    query = f"""
    SELECT
        r.nombre AS Revendedor_Origen,
        pc.fecha_pago AS Fecha_Pago_Recibido,
        ci.nombre AS Categoria_Destino,
        ip.monto_imputado AS Monto_Aplicado,
        ip.referencia_egreso AS Referencia_Egreso
    FROM imputaciones_pago AS ip
    JOIN pagos_comprobantes AS pc ON ip.pago_comprobante_id = pc.id
    LEFT JOIN ventas AS v ON pc.venta_id = v.id 
    LEFT JOIN revendedores AS r ON v.revendedor_id = r.id
    JOIN categorias_imputacion AS ci ON ip.categoria_id = ci.id
    WHERE pc.fecha_pago BETWEEN ? AND ?
    {where_revendedor}
    {where_categoria}
    ORDER BY Fecha_Pago_Recibido DESC;
    """
    params = [fecha_inicio.strftime("%Y-%m-%d"), fecha_fin.strftime("%Y-%m-%d")] + params_rev + params_cat
    return fetch_df(query, params)

@st.cache_data
def get_upcoming_promises(dias_atraso, dias_futuro, revendedor_ids=None):
    """Obtiene promesas de pago que están por vencer o vencidas recientemente."""
    where_revendedor = ""
    params_rev = []
    if revendedor_ids:
        placeholders = ','.join('?' for _ in revendedor_ids)
        where_revendedor = f" AND r.id IN ({placeholders})"
        params_rev = revendedor_ids
    
    start_date = date.today() - timedelta(days=dias_atraso)
    end_date = date.today() + timedelta(days=dias_futuro)
    
    query = f"""
    SELECT
        r.nombre AS Revendedor,
        r.contacto AS Contacto_Revendedor,
        p.fecha_promesa AS Fecha_Promesa,
        p.monto_prometido AS Monto_Prometido,
        p.observaciones AS Observaciones,
        CASE
            WHEN p.fecha_promesa < date('now') THEN '🔴 Vencida'
            WHEN p.fecha_promesa = date('now') THEN '🟡 Vence Hoy'
            ELSE '🟢 Por Vencer'
        END AS Estado,
        CAST(julianday(p.fecha_promesa) - julianday('now') AS INTEGER) AS Dias_Restantes
    FROM promesas_pago AS p
    JOIN revendedores AS r ON p.revendedor_id = r.id
    WHERE p.fecha_promesa BETWEEN ? AND ?
    {where_revendedor}
    ORDER BY p.fecha_promesa ASC;
    """
    params = [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")] + params_rev
    return fetch_df(query, params)

# =================================================================================================
# INTERFAZ STREAMLIT
# =================================================================================================

# Se modifica para aceptar un contenedor (parent_st)
def app_cobranza_interface(parent_st=st):
    """Función principal para dibujar la interfaz de Streamlit dentro de un contenedor."""
    
    # Todos los elementos de UI deben usar parent_st
    parent_st.title("💸 Dashboard Interactivo de Cobranza de Revendedores")
    
    # -------------------------------------------------------------------------
    # 1. BARRA LATERAL (FILTROS GLOBALES) -> **Usa st.sidebar** (Elemento GLOBAL)
    # -------------------------------------------------------------------------
    
    # Aquí se corrige la asignación de variables
    min_db_date, max_db_date, df_revendedores, df_categorias = get_metadata()
    
    st.sidebar.header("⚙️ Configuración y Filtros Globales")
    
    # --- FILTRO DE FECHAS ---
    st.sidebar.subheader("📅 Rango de Fechas (Ventas/Pagos)")
    default_start_date = max_db_date - timedelta(days=90)
    if default_start_date < min_db_date: default_start_date = min_db_date

    # Se usa st.sidebar para los filtros
    fecha_inicio = st.sidebar.date_input("Fecha de Inicio:", value=default_start_date, min_value=min_db_date, max_value=max_db_date, key='ci_f_inicio')
    fecha_fin = st.sidebar.date_input("Fecha de Fin:", value=max_db_date, min_value=min_db_date, max_value=max_db_date, key='ci_f_fin')
    if fecha_inicio > fecha_fin: st.sidebar.error("⚠️ La fecha de inicio no puede ser posterior a la de fin."); fecha_inicio = fecha_fin

    # --- FILTRO DE REVENDEDOR ---
    st.sidebar.subheader("👤 Revendedor(es)")
    revendedor_map = {'Todos': 0}
    if not df_revendedores.empty: revendedor_map.update(df_revendedores.set_index('nombre')['id'].to_dict())
    nombres_revendedores = ['Todos'] + sorted(df_revendedores['nombre'].tolist())
    selected_names = st.sidebar.multiselect("Seleccione Revendedor(es):", options=nombres_revendedores, default='Todos', key='ci_rev_select')
    
    revendedor_ids = [revendedor_map[name] for name in selected_names if name != 'Todos']
    final_revendedor_ids = revendedor_ids if revendedor_ids else None 

    parent_st.markdown("---") # Usar parent_st
    
    # -------------------------------------------------------------------------
    # 2. INDICADORES CLAVE (KPIs)
    # -------------------------------------------------------------------------
    
    parent_st.header("🔑 Indicadores de Deuda Consolidados") # Usar parent_st
    total_deuda = get_total_deuda_global(fecha_inicio, fecha_fin, final_revendedor_ids)
    df_resumen = get_reseller_debt_summary(fecha_inicio, fecha_fin, final_revendedor_ids)

    col1, col2, col3 = parent_st.columns(3) # Usar parent_st
    with col1:
        parent_st.metric(label="Dinero Total Adeudado", value=f"${total_deuda:,.2f}", delta_color="inverse")
    with col2:
        revendedor_atrasado = df_resumen.iloc[0]['Revendedor'] if not df_resumen.empty else "N/A"
        fecha_antigua = df_resumen.iloc[0]['Fecha_Venta_Mas_Antigua_Pendiente'] if not df_resumen.empty else "N/A"
        parent_st.metric(label="Revendedor Más Atrasado", value=revendedor_atrasado, delta=f"Venta Pendiente Desde: {fecha_antigua}", delta_color="inverse")
    with col3:
        parent_st.metric(label="Revendedores con Deuda", value=f"{len(df_resumen)} Revendedores")

    parent_st.markdown("---") # Usar parent_st
    
    # -------------------------------------------------------------------------
    # 3. VISTAS DETALLADAS INTERACTIVAS (TABS)
    # -------------------------------------------------------------------------
    
    # Usar parent_st para crear las pestañas
    tab1, tab2, tab3, tab4 = parent_st.tabs(["📝 Conciliación Detallada", "📉 Deuda por Revendedor", "💳 Trazabilidad de Imputaciones", "📞 Promesas de Pago (Proactivo)"])

    # --- TAB 1: CONCILIACIÓN DETALLADA ---
    with tab1:
        tab1.subheader("Conciliación de Ventas Pendientes (Factura por Factura)")
        df_detalle_ventas = get_pending_sales_detail(fecha_inicio, fecha_fin, final_revendedor_ids)
        if not df_detalle_ventas.empty:
            df_display_detalle = df_detalle_ventas.copy()
            df_display_detalle['Monto_Original'] = df_display_detalle['Monto_Original'].apply(lambda x: f'{x:,.2f}')
            df_display_detalle['Pagos_Recibidos'] = df_display_detalle['Pagos_Recibidos'].apply(lambda x: f'{x:,.2f}')
            df_display_detalle['Saldo_Pendiente'] = df_display_detalle['Saldo_Pendiente'].apply(lambda x: f'{x:,.2f}')
            
            tab1.dataframe( # Usar tab1
                df_display_detalle,
                use_container_width=True,
                column_config={
                    "Saldo_Pendiente": st.column_config.TextColumn("💰 **SALDO PENDIENTE (USD)**"),
                    "Dias_Atraso": st.column_config.NumberColumn("🔴 Días Atraso", format="%d días"),
                }, hide_index=True,
            )
        else:
            tab1.info("No se encontraron facturas pendientes con los filtros aplicados.")

    # --- TAB 2: RESUMEN DE DEUDA POR REVENDEDOR ---
    with tab2:
        tab2.subheader("Resumen Consolidado de Deuda por Revendedor")
        tab2.dataframe( # Usar tab2
            df_resumen.assign(Deuda_Total=df_resumen['Deuda_Total'].apply(lambda x: f'${x:,.2f}')),
            use_container_width=True, hide_index=True
        )

    # --- TAB 3: FLUJO DE IMPUTACIONES ---
    with tab3:
        tab3.subheader("Trazabilidad: Pagos de Revendedores vs. Destino (Proveedor/Sueldo)")
        
        categoria_map = {'Todos los Egresos': 0}
        if not df_categorias.empty: categoria_map.update(df_categorias.set_index('nombre')['id'].to_dict())
        nombres_categorias = ['Todos los Egresos'] + sorted(df_categorias['nombre'].tolist())
        selected_categories = tab3.multiselect("Filtrar por Destino Específico:", options=nombres_categorias, default='Todos los Egresos', key='ci_cat_select')
        
        categoria_ids = [categoria_map[name] for name in selected_categories if name != 'Todos los Egresos']
        final_categoria_ids = categoria_ids if categoria_ids else None

        df_imputaciones = get_payment_imputations(fecha_inicio, fecha_fin, final_revendedor_ids, final_categoria_ids)
        
        if not df_imputaciones.empty:
            df_imputaciones_display = df_imputaciones.copy()
            df_imputaciones_display['Monto_Aplicado'] = df_imputaciones_display['Monto_Aplicado'].apply(lambda x: f'${x:,.2f}')
            
            tab3.dataframe(df_imputaciones_display, use_container_width=True, hide_index=True) # Usar tab3
            
        else:
            tab3.info("No se encontraron imputaciones que coincidan con el revendedor, fecha y/o destino seleccionados.")
            
    # --- TAB 4: PROMESAS DE PAGO (NUEVA SECCIÓN PROACTIVA) ---
    with tab4:
        tab4.header("Gestión Proactiva: Promesas de Pago por Vencer") # Usar tab4
        tab4.markdown("Utilice esta vista para ver promesas a punto de vencer (para recordar al cliente) o que ya vencieron (para iniciar la gestión de cobro).")

        col_p1, col_p2 = tab4.columns(2) # Usar tab4
        with col_p1:
            dias_atraso = tab4.slider("Mostrar promesas vencidas hasta hace (días):", min_value=0, max_value=90, value=7, step=1, key='ci_dias_atraso')
        with col_p2:
            dias_futuro = tab4.slider("Mostrar promesas por vencer en los próximos (días):", min_value=0, max_value=90, value=15, step=1, key='ci_dias_futuro')
            
        tab4.warning(f"Se muestran promesas desde el **{date.today() - timedelta(days=dias_atraso)}** hasta el **{date.today() + timedelta(days=dias_futuro)}**.")

        df_promesas = get_upcoming_promises(dias_atraso, dias_futuro, final_revendedor_ids)

        if not df_promesas.empty:
            df_promesas_display = df_promesas.copy()
            df_promesas_display['Monto_Prometido'] = df_promesas_display['Monto_Prometido'].apply(lambda x: f'${x:,.2f}')

            def highlight_status(row):
                style = [''] * len(row)
                if 'Vencida' in row['Estado']:
                    style = ['background-color: #ffcccc'] * len(row)
                elif 'Vence Hoy' in row['Estado']:
                    style = ['background-color: #ffffcc'] * len(row)
                return style

            tab4.dataframe( # Usar tab4
                df_promesas_display.style.apply(highlight_status, axis=1),
                use_container_width=True,
                column_config={
                    "Revendedor": "Revendedor",
                    "Contacto_Revendedor": "Contacto",
                    "Fecha_Promesa": st.column_config.DateColumn("Fecha Promesa"),
                    "Monto_Prometido": st.column_config.TextColumn("Monto Prometido (USD)"),
                    "Observaciones": "Observaciones",
                    "Estado": "Estado",
                    "Dias_Restantes": st.column_config.NumberColumn("Días para Vencer", help="Negativo = Vencida")
                },
                hide_index=True
            )
        else:
            tab4.info("No se encontraron promesas de pago en el rango de fechas y/o revendedor(es) seleccionado.")


# Ejecutar la aplicación
if __name__ == "__main__":
    app_cobranza_interface() # Si se ejecuta de forma independiente, usa st por defecto