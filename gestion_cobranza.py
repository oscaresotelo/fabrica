import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
from seguimiento_cobranza import app_cobranza_interface

# =================================================================================================
# CONFIG
# =================================================================================================
DB_PATH = "minerva.db"

# =================================================================================================
# UTILIDADES DB
# =================================================================================================
def get_connection():
    """Establece la conexión a la base de datos."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_df(query, params=()):
    """Ejecuta una consulta SELECT y devuelve los resultados como un DataFrame de Pandas."""
    conn = get_connection()
    try:
        # Usamos read_sql_query de pandas para manejar la conversión a DataFrame
        df = pd.read_sql_query(query, conn, params=params)
    except sqlite3.Error as e:
        # Si hay un error de base de datos (como columna inexistente), lo mostramos.
        st.error(f"Error al ejecutar la consulta: {e}")
        return pd.DataFrame()  # Retorna DataFrame vacío en caso de error
    finally:
        conn.close()
    return df

def get_table_columns(table_name):
    """Devuelve la lista de columnas de una tabla (útil para detectar nombres reales)."""
    conn = get_connection()
    try:
        # Utilizamos PRAGMA table_info para obtener la metadata de la tabla
        cur = conn.execute(f"PRAGMA table_info('{table_name}')")
        cols = [row["name"] for row in cur.fetchall()]
    except sqlite3.Error as e:
        st.error(f"Error al obtener las columnas de la tabla '{table_name}': {e}")
        return []
    finally:
        conn.close()
    return cols

def first_existing_column(table_name, candidates):
    """Devuelve el primer nombre de columna de 'candidates' que exista en la tabla."""
    cols = get_table_columns(table_name)
    for c in candidates:
        if c in cols:
            return c
    return None

# =================================================================================================
# LÓGICA DE COBRANZA (ROBUSTA)
# =================================================================================================

def get_estado_revendedores():
    """
    Calcula el estado de cuenta por revendedor:
    -> calcula el saldo por factura (total_factura - pagos_en_esa_factura)
    -> luego agrupa por revendedor para sumar totales y saldos.
    """
    # Detectar nombre de la columna 'total' en la tabla ventas
    total_col = first_existing_column("ventas", ["total_venta", "total", "total_mas_iva", "importe_total"])
    if total_col is None:
        st.warning("No se encontró una columna de total en la tabla 'ventas'. Los cálculos de saldo serán 0.")
        query_simple = """
        SELECT r.id, r.nombre, 0 AS total_ventas, 0 AS total_pagos, 0 AS saldo_pendiente
        FROM revendedores r
        ORDER BY r.nombre;
        """
        return fetch_df(query_simple)

    # Query que calcula a nivel factura el total y lo que fue pagado sobre esa factura,
    # luego agrupa por revendedor para consolidar.
    query = f"""
    SELECT
        r.id,
        r.nombre,
        COALESCE(SUM(v.total_val), 0) AS total_ventas,
        COALESCE(SUM(v.total_pagado), 0) AS total_pagos,
        COALESCE(SUM(v.total_val - v.total_pagado), 0) AS saldo_pendiente
    FROM revendedores r
    LEFT JOIN (
        SELECT
            ventas.id AS venta_id,
            ventas.revendedor_id AS revendedor_id,
            COALESCE(ventas.{total_col}, 0) AS total_val,
            COALESCE(p.total_pagado, 0) AS total_pagado
        FROM ventas
        LEFT JOIN (
            SELECT venta_id, SUM(importe_pagado) AS total_pagado
            FROM pagos_comprobantes
            GROUP BY venta_id
        ) p ON ventas.id = p.venta_id
    ) v ON r.id = v.revendedor_id
    GROUP BY r.id, r.nombre
    ORDER BY saldo_pendiente DESC;
    """
    return fetch_df(query)

def get_movimientos_revendedor(revendedor_id):
    """
    Obtiene detalle de ventas y pagos por revendedor de forma robusta,
    detectando nombres de columnas comunes.
    """
    # Detectar columnas en ventas
    total_col = first_existing_column("ventas", ["total_venta", "total", "total_mas_iva", "importe_total"])
    fecha_col = first_existing_column("ventas", ["fecha_venta", "fecha", "fecha_factura", "fecha_emision"])
    numero_col = first_existing_column("ventas", ["numero_comprobante", "numero", "factura", "n_comprobante", "numero_factura"])

    # Si faltan columnas críticas, devolver dataframes vacíos para evitar excepciones
    if total_col is None:
        ventas_df = pd.DataFrame(columns=["venta_id", "fecha_venta", "numero_comprobante", "total_venta", "total_pagado"])
        pagos_df = pd.DataFrame(columns=["fecha_pago", "importe_pagado", "numero_comprobante"])
        return ventas_df, pagos_df

    # Construir la query de ventas usando las columnas detectadas (si fecha o número no existen se usan valores nulos)
    fecha_select = f"ventas.{fecha_col}" if fecha_col else "NULL AS fecha_venta"
    numero_select = f"ventas.{numero_col}" if numero_col else "ventas.id AS numero_comprobante"

    ventas_query = f"""
    SELECT
        ventas.id AS venta_id,
        {fecha_select} AS fecha_venta,
        {numero_select} AS numero_comprobante,
        COALESCE(ventas.{total_col}, 0) AS total_venta,
        COALESCE((SELECT SUM(importe_pagado) FROM pagos_comprobantes WHERE venta_id = ventas.id), 0) AS total_pagado
    FROM ventas
    WHERE ventas.revendedor_id = ?
    ORDER BY fecha_venta DESC NULLS LAST, venta_id DESC;
    """

    pagos_query = f"""
    SELECT
        p.fecha_pago,
        p.importe_pagado,
        COALESCE(v.{numero_col}, v.id) AS numero_comprobante
    FROM pagos_comprobantes p
    LEFT JOIN ventas v ON p.venta_id = v.id
    WHERE v.revendedor_id = ?
    ORDER BY p.fecha_pago DESC;
    """

    ventas_df = fetch_df(ventas_query, (revendedor_id,))
    pagos_df = fetch_df(pagos_query, (revendedor_id,))

    return ventas_df, pagos_df

def get_revendedores_saldo():
    """
    Obtiene todos los revendedores con su saldo actual calculado.
    """
    df_estado = get_estado_revendedores()
    
    if df_estado.empty:
        return pd.DataFrame({'id': [], 'nombre': [], 'saldo': []})

    # Renombrar 'saldo_pendiente' a 'saldo' para que la función llamadora funcione.
    df_estado = df_estado.rename(columns={'saldo_pendiente': 'saldo'})
    return df_estado[['id', 'nombre', 'saldo']]

def get_imputacion_categories():
    """
    Obtiene las categorías de imputación de tipo 'EGRESO'.
    """
    query = "SELECT id, nombre FROM categorias_imputacion WHERE tipo = 'EGRESO' ORDER BY nombre"
    return fetch_df(query)

# =================================================================================================
# LÓGICA DE TRANSACCIÓN CRÍTICA (Pago y Imputación a Egresos)
# =================================================================================================

def registrar_pago_e_imputar(revendedor_id, fecha_pago, monto_total, imputaciones):
    """
    Registra el pago, lo DISTRIBUYE a las facturas y luego inserta las imputaciones
    del dinero a los destinos operativos.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN TRANSACTION")

        # 1. Distribuir el pago a las facturas pendientes 
        cursor = conn.cursor()
        
        # Obtener ventas adeudadas ordenadas por fecha
        cursor.execute("""
            SELECT id, total_venta,
            COALESCE((SELECT SUM(importe_pagado) FROM pagos_comprobantes WHERE venta_id = ventas.id), 0) AS total_pagado
            FROM ventas
            WHERE revendedor_id = ? AND total_venta >
            COALESCE((SELECT SUM(importe_pagado) FROM pagos_comprobantes WHERE venta_id = ventas.id), 0)
            ORDER BY fecha_venta ASC
        """, (revendedor_id,))
        ventas = [dict(row) for row in cursor.fetchall()] 

        importe_restante = monto_total
        sobrante_no_imputado = 0.0
        
        # Iterar sobre las ventas e imputar el pago a pagos_comprobantes
        for venta in ventas:
            venta_id = venta["id"]
            total_venta = venta["total_venta"]
            total_pagado = venta["total_pagado"]
            saldo_pendiente = total_venta - total_pagado

            if importe_restante >= saldo_pendiente:
                # Registrar pago completo de la factura
                cursor.execute("""
                    INSERT INTO pagos_comprobantes (venta_id, importe_pagado, fecha_pago)
                    VALUES (?, ?, ?)
                """, (venta_id, saldo_pendiente, fecha_pago))
                importe_restante -= saldo_pendiente

            else:
                # Registrar pago parcial de la factura
                cursor.execute("""
                    INSERT INTO pagos_comprobantes (venta_id, importe_pagado, fecha_pago)
                    VALUES (?, ?, ?)
                """, (venta_id, importe_restante, fecha_pago))
                importe_restante = 0
                break

        # Manejar el sobrante si lo hay (asumiendo tabla sobrantes_pagos)
        if importe_restante > 0:
            sobrante_no_imputado = importe_restante
            try:
                # Usar la tabla de sobrantes
                conn.execute("""
                    INSERT INTO sobrantes_pagos (revendedor_id, importe_sobrante, fecha_sobrante)
                    VALUES (?, ?, ?)
                """, (revendedor_id, sobrante_no_imputado, fecha_pago))
            except sqlite3.Error:
                # Solo advertir si la tabla no existe
                st.warning(f"La tabla 'sobrantes_pagos' no existe, el sobrante de ${sobrante_no_imputado:,.2f} no se pudo registrar.")

        
        # 2. Insertar el pago global en pagos_revendedor (como registro del ingreso)
        cursor.execute(
            "INSERT INTO pagos_revendedor (revendedor_id, fecha_pago, monto, observacion) VALUES (?, ?, ?, 'Pago con imputación a egresos')",
            (revendedor_id, fecha_pago, monto_total)
        )
        pago_id = cursor.lastrowid

        # 3. Insertar las imputaciones (asignación del dinero a egresos)
        for cat_id, monto_imputado in imputaciones.items():
            conn.execute(
                "INSERT INTO imputaciones_pago (pago_revendedor_id, categoria_imputacion_id, monto_imputado) VALUES (?, ?, ?)",
                (pago_id, cat_id, monto_imputado)
            )

        conn.commit()
        return True

    except sqlite3.Error as e:
        conn.rollback()
        st.error(f"Error al registrar el pago e imputaciones: {e}")
        return False
    finally:
        conn.close()

# =================================================================================================
# OPERACIONES ORIGINALES (Pago Tradicional y Promesa)
# =================================================================================================

def registrar_pago_y_distribuir(revendedor_id, importe, fecha=None):
    """
    Registra un pago y lo distribuye entre las facturas más antiguas del revendedor.
    """
    conn = get_connection()
    if fecha is None:
        fecha = date.today().strftime("%Y-%m-%d")
    try:
        cursor = conn.cursor()
        # 1. Obtener ventas adeudadas ordenadas por fecha
        cursor.execute("""
            SELECT id, total_venta, 
            COALESCE((SELECT SUM(importe_pagado) FROM pagos_comprobantes WHERE venta_id = ventas.id), 0) AS total_pagado
            FROM ventas
            WHERE revendedor_id = ? AND total_venta > 
            COALESCE((SELECT SUM(importe_pagado) FROM pagos_comprobantes WHERE venta_id = ventas.id), 0)
            ORDER BY fecha_venta ASC
        """, (revendedor_id,))
        ventas = [dict(row) for row in cursor.fetchall()] # convertir la respuesta a dict

        importe_restante = importe
        # 2. Iterar sobre las ventas e imputar el pago
        for venta in ventas:
            venta_id = venta["id"]
            total_venta = venta["total_venta"]
            total_pagado = venta["total_pagado"]
            saldo_pendiente = total_venta - total_pagado

            if importe_restante >= saldo_pendiente:
                # Registrar pago completo de la factura
                cursor.execute("""
                    INSERT INTO pagos_comprobantes (venta_id, importe_pagado, fecha_pago)
                    VALUES (?, ?, ?)
                """, (venta_id, saldo_pendiente, fecha))
                importe_restante -= saldo_pendiente

            else:
                # Registrar pago parcial de la factura
                cursor.execute("""
                    INSERT INTO pagos_comprobantes (venta_id, importe_pagado, fecha_pago)
                    VALUES (?, ?, ?)
                """, (venta_id, importe_restante, fecha))
                importe_restante = 0
                break  # No queda más importe para distribuir

        # 3. Manejar el sobrante (asumiendo tabla sobrantes_pagos)
        if importe_restante > 0:
            try:
                cursor.execute("""
                    INSERT INTO sobrantes_pagos (revendedor_id, importe_sobrante, fecha_sobrante)
                    VALUES (?, ?, ?)
                """, (revendedor_id, importe_restante, fecha))
            except sqlite3.Error:
                st.warning(f"La tabla 'sobrantes_pagos' no existe, el sobrante de ${importe_restante:,.2f} no se pudo registrar.")

        conn.commit()
        return True

    except sqlite3.Error as e:
        conn.rollback()
        st.error(f"Error al registrar y distribuir el pago: {e}")
        return False
    finally:
        conn.close()

def registrar_promesa(revendedor_id, fecha_promesa, monto_prometido, observaciones):
    """Registra una promesa de pago en la tabla promesas_pago."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO promesas_pago (revendedor_id, fecha_promesa, monto_prometido, observaciones)
            VALUES (?, ?, ?, ?)
        """, (revendedor_id, fecha_promesa, monto_prometido, observaciones))
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Error al registrar la promesa de pago: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

# =================================================================================================
# VISTAS/SECCIONES DE STREAMLIT (Lógica de la pestaña 3)
# =================================================================================================

def mostrar_seccion_registrar_pago_imputado():
    """Interfaz para registrar un pago, descontar la deuda y asignar destinos."""
    st.title("💸 Registrar Pago con Imputación a Gastos")

    # Utilizamos la función robusta que calcula el saldo
    revendedores_df = get_revendedores_saldo() 
    
    if revendedores_df.empty:
        st.warning("No hay revendedores registrados con saldo. Revise la tabla 'revendedores'.")
        return

    # Preparar opciones para el selectbox
    revendedores_df["display"] = revendedores_df["nombre"] + " (ID:" + revendedores_df["id"].astype(str) + ")"
    nombres_revendedores = revendedores_df['display'].tolist()
    nombre_a_id = revendedores_df.set_index('display')['id'].to_dict()
    
    # 1. Selección de Revendedor
    revendedor_seleccionado_display = st.selectbox(
        "1. Seleccione el Revendedor:",
        nombres_revendedores,
        key='pago_revendedor_select'
    )
    revendedor_id = nombre_a_id.get(revendedor_seleccionado_display)
    
    # Mostrar saldo actual
    saldo_actual = 0.0
    if revendedor_seleccionado_display and revendedor_id in revendedores_df['id'].values:
        # Usamos 'saldo' que fue renombrado en get_revendedores_saldo
        saldo_actual = revendedores_df[revendedores_df['id'] == revendedor_id]['saldo'].iloc[0]
        st.info(f"Deuda (Saldo) Actual de {revendedor_seleccionado_display.split(' (')[0]}: **${saldo_actual:,.2f}**")
    
    st.markdown("---") 

    # 2. Monto Total del Pago (Descuenta la Deuda)
    monto_total_pago = st.number_input(
        "2. Monto Total Pagado por el Revendedor (Se distribuirá a la Deuda):",
        min_value=0.0,
        value=0.0,
        step=100.0,
        format="%.2f",
        key="monto_total_pago"
    )

    fecha_pago = st.date_input("Fecha de Pago:", value=date.today(), key='fecha_pago_imputacion')

    st.markdown("---") 
    st.markdown("#### 3. Asignación del Dinero (Destino Operativo)")
    st.caption("Debe asignar el **monto total pagado** a los gastos operativos (Proveedores, Fijos, Sueldos, etc.).")

    # Cargar categorías de imputación (EGRESOS)
    categorias_df = get_imputacion_categories()
    if categorias_df.empty:
        st.error("No hay categorías de imputación de tipo 'EGRESO' configuradas. Por favor, revise la tabla `categorias_imputacion`.")
        return

    categorias_dict = categorias_df.set_index('id')['nombre'].to_dict()
    imputaciones_monto = {}
    monto_imputado_acumulado = 0.0

    # Iterar sobre las categorías para ingresar montos
    with st.container(border=True):
        for cat_id, cat_nombre in categorias_dict.items():
            monto_imputacion = st.number_input(
                f"Monto asignado a **{cat_nombre}**:",
                min_value=0.0,
                value=0.0,
                step=1.0,
                format="%.2f",
                key=f"imputacion_{cat_id}_monto"
            )
            if monto_imputacion > 0:
                imputaciones_monto[cat_id] = monto_imputacion
                monto_imputado_acumulado += monto_imputacion

    # Verificación de saldos
    monto_restante = monto_total_pago - monto_imputado_acumulado

    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.metric("Monto Total Pagado", f"${monto_total_pago:,.2f}")
    with col_info2:
        st.metric("Monto Total Asignado", f"${monto_imputado_acumulado:,.2f}")

    if abs(monto_restante) > 0.01: # Tolerancia para punto flotante
        if monto_restante > 0.01:
            st.warning(f"⚠️ Aún restan **${monto_restante:,.2f}** por asignar. La asignación debe cubrir el pago total.")
        else:
            st.error(f"🛑 El monto asignado excede el pago total por **${abs(monto_restante):,.2f}**. Corrija la asignación.")
    

    if st.button("4. Confirmar Pago y Asignación de Destinos", use_container_width=True):
        if revendedor_id is None:
            st.error("Seleccione un revendedor.")
        elif monto_total_pago <= 0:
            st.error("El monto total del pago debe ser mayor a cero.")
        elif abs(monto_restante) > 0.01:
            st.error("Error de Imputación: La suma de los destinos debe ser **exactamente igual** al monto total pagado.")
        elif not imputaciones_monto:
            st.error("Debe asignar el dinero (imputar) a uno o más destinos operativos.")
        else:
            if registrar_pago_e_imputar(
                revendedor_id, 
                fecha_pago.strftime("%Y-%m-%d"), 
                monto_total_pago, 
                imputaciones_monto
            ):
                st.success(f"✅ Pago de ${monto_total_pago:,.2f} registrado. Deuda descontada y fondos asignados con éxito.")
                st.balloons()
                st.rerun()

# =================================================================================================
# SECCIÓN REGISTRO DE PROMESAS (Extraída de las pestañas)
# =================================================================================================

def mostrar_seccion_promesas_de_pago():
    """Interfaz para registrar una promesa de pago, ahora dentro de un expander."""
    
    st.subheader("✍️ Registrar Promesa de Pago")
        
    df_revendedores_all = fetch_df("SELECT id, nombre FROM revendedores ORDER BY nombre")
    if df_revendedores_all.empty:
        st.info("No hay revendedores para registrar una promesa.")
        return

    nombre_a_id = dict(zip(df_revendedores_all['nombre'], df_revendedores_all['id']))
    nombres_revendedores = df_revendedores_all['nombre'].tolist()
    
    # Se usan claves diferentes para evitar conflictos con los selectboxes de otras pestañas
    revendedor_promesa = st.selectbox(
        "Seleccione el revendedor:",
        nombres_revendedores,
        key='promesa_revendedor_select_main' 
    )
    revendedor_id_promesa = nombre_a_id.get(revendedor_promesa)
    
    fecha_promesa = st.date_input("Fecha de la Promesa:", value=date.today(), key='fecha_promesa_main')
    monto_promesa = st.number_input(
        "Monto Prometido:",
        min_value=0.0,
        value=0.0,
        step=100.0,
        format="%.2f",
        key='monto_promesa_main'
    )
    observaciones_promesa = st.text_area("Observaciones (opcional):", key='obs_promesa_main')
    
    if st.button("Guardar Promesa", key='button_promesa_main'):
        if revendedor_id_promesa is None:
            st.error("Error: No se pudo encontrar el ID del revendedor. Intente seleccionar de nuevo.")
        elif monto_promesa > 0:
            if registrar_promesa(revendedor_id_promesa, fecha_promesa.strftime("%Y-%m-%d"), monto_promesa, observaciones_promesa):
                st.success("✅ Promesa de pago registrada con éxito.")
                st.rerun()
        else:
            st.warning("El monto prometido debe ser mayor a cero.")

# =================================================================================================
# ESTRUCTURA PRINCIPAL DE LA APLICACIÓN (5 PESTAÑAS + EXPANDER)
# =================================================================================================
def mostrar_gestion_cobranza():
    st.header("Gestión de Pagos y Cobranzas de Revendedores")
    st.markdown("---")

    # 📌 Expander de Promesas (Ahora visible en la parte superior)
    with st.expander("✍️ Registrar Nueva Promesa de Pago", expanded=False):
        mostrar_seccion_promesas_de_pago()

    st.markdown("---")
    
    # Definición de las 5 pestañas principales:
    # Se eliminó "Promesas de Pago" de la lista de pestañas
    tab1, tab6_seguimiento, tab2, tab3_imputacion, tab4_original = st.tabs([
    "Resumen General", 
    "Seguimiento de Cobranza", 
    "Detalle por Revendedor", 
    "Pago con Imputación (Nuevo)", 
    "Pago Tradicional (a Facturas)"
    ])
    
    # ----------------------------------------------------
    # TAB 1: RESUMEN GENERAL + PROMESAS EN RESUMEN
    # ----------------------------------------------------
    with tab1:
        st.subheader("📊 Resumen General de Cuentas por Revendedor")
        df_estado = get_estado_revendedores() 

        if df_estado.empty:
            st.info("No hay revendedores en la base de datos.")
            return

        df_estado_display = df_estado.copy()
        df_estado_display["RevendedorDisplay"] = df_estado_display["nombre"].astype(str) + " (ID:" + df_estado_display["id"].astype(str) + ")"

        # Obtener la última fecha de pago para cada revendedor
        df_ultimos_pagos = fetch_df("""
            SELECT
                r.id,
                MAX(pc.fecha_pago) AS ultima_fecha_pago
            FROM revendedores r
            LEFT JOIN ventas v ON r.id = v.revendedor_id
            LEFT JOIN pagos_comprobantes pc ON v.id = pc.venta_id
            GROUP BY r.id
        """)

        df_estado_display = pd.merge(df_estado_display, df_ultimos_pagos, on='id', how='left')
        df_estado_display["ultima_fecha_pago"] = pd.to_datetime(df_estado_display["ultima_fecha_pago"], errors='coerce').dt.strftime('%Y-%m-%d')
        df_estado_display["ultima_fecha_pago"] = df_estado_display["ultima_fecha_pago"].fillna("Sin pagos")

        df_estado_display.rename(columns={
            "total_ventas": "Total Ventas",
            "total_pagos": "Total Pagado",
            "saldo_pendiente": "Saldo Pendiente",
            "ultima_fecha_pago": "Última Fecha de Pago"
        }, inplace=True)

        st.dataframe(df_estado_display[[
            "RevendedorDisplay",
            "Total Ventas",
            "Total Pagado",
            "Saldo Pendiente",
            "Última Fecha de Pago"
        ]].style.format({
            "Total Ventas": "AR$ {:,.2f}",
            "Total Pagado": "AR$ {:,.2f}",
            "Saldo Pendiente": "AR$ {:,.2f}"
        }), use_container_width=True)
        
        st.markdown("---")
        # Mostrar el listado de Promesas registradas en un expander dentro del Resumen
        with st.expander("🗓️ Ver Promesas de Pago Registradas", expanded=False):
            df_promesas = fetch_df("""
                SELECT
                    r.nombre AS revendedor,
                    pp.fecha_promesa,
                    pp.monto_prometido,
                    pp.observaciones
                FROM promesas_pago pp
                JOIN revendedores r ON pp.revendedor_id = r.id
                ORDER BY pp.fecha_promesa DESC
            """)
            if not df_promesas.empty:
                st.dataframe(df_promesas.rename(columns={
                    'fecha_promesa': 'Fecha de Promesa',
                    'monto_prometido': 'Monto Prometido',
                    'observaciones': 'Observaciones'
                }).style.format({"Monto Prometido": "AR$ {:,.2f}"}), use_container_width=True)
            else:
                st.info("No hay promesas de pago registradas.")

    # ----------------------------------------------------
    # TAB 2: DETALLE POR REVENDEDOR
    # ----------------------------------------------------
    with tab2:
        st.subheader("🔍 Detalle de Cuenta por Revendedor")
        df_estado = get_estado_revendedores()

        if df_estado.empty:
            st.info("No hay revendedores en la base de datos.")
            return

        df_estado_display = df_estado.copy()
        df_estado_display["RevendedorDisplay"] = df_estado_display["nombre"].astype(str) + " (ID:" + df_estado_display["id"].astype(str) + ")"

        opciones = df_estado_display["RevendedorDisplay"].tolist()
        seleccionado = st.selectbox("Seleccione un revendedor para ver su detalle de cuenta:", opciones, key="detalle_revendedor_select")

        try:
            revendedor_id_detalle = int(seleccionado.split("ID:")[1].strip(")"))
        except Exception:
            st.error("No se pudo obtener el id del revendedor seleccionado.")
            return

        ventas_df, pagos_df = get_movimientos_revendedor(revendedor_id_detalle)

        st.subheader("📄 Historial de Ventas")
        if ventas_df.empty:
            st.write("No hay historial de ventas para mostrar.")
        else:
            ventas_hist = ventas_df.copy()
            ventas_hist["total_venta"] = pd.to_numeric(ventas_hist["total_venta"], errors="coerce").fillna(0.0)
            ventas_hist["total_pagado"] = pd.to_numeric(ventas_hist["total_pagado"], errors="coerce").fillna(0.0)
            ventas_hist["Saldo Pendiente"] = ventas_hist["total_venta"] - ventas_hist["total_pagado"]

            ventas_hist["Fecha Venta"] = pd.to_datetime(ventas_hist["fecha_venta"], errors="coerce")
            hoy = pd.Timestamp(date.today())
            ventas_hist["Días de Mora"] = (hoy - ventas_hist["Fecha Venta"]).dt.days
            ventas_hist["Días de Mora"] = ventas_hist["Días de Mora"].fillna("N/A")

            ventas_hist["Factura"] = ventas_hist["numero_comprobante"]
            ventas_hist = ventas_hist.rename(columns={
                "total_venta": "Total Factura",
                "total_pagado": "Total Pagado"
            })

            st.dataframe(
                ventas_hist[["Fecha Venta", "Factura", "Total Factura", "Total Pagado", "Saldo Pendiente", "Días de Mora"]]
                .style.format({
                    "Total Factura": "AR$ {:,.2f}",
                    "Total Pagado": "AR$ {:,.2f}",
                    "Saldo Pendiente": "AR$ {:,.2f}"
                }),
                use_container_width=True
            )

        st.markdown("---")
        st.subheader("🧾 Historial de Pagos Recibidos")
        if pagos_df.empty:
            st.write("No se encontraron pagos asociados a este revendedor.")
        else:
            pagos_show = pagos_df.copy()
            pagos_show = pagos_show.rename(columns={
                "fecha_pago": "Fecha de Pago",
                "importe_pagado": "Importe Pagado",
                "numero_comprobante": "Factura Vinculada"
            })
            st.dataframe(
                pagos_show[["Fecha de Pago", "Importe Pagado", "Factura Vinculada"]]
                .style.format({"Importe Pagado": "AR$ {:,.2f}"}),
                use_container_width=True
            )

    # ----------------------------------------------------
    # TAB 3: PAGO CON IMPUTACIÓN (NUEVO)
    # ----------------------------------------------------
    with tab3_imputacion:
        mostrar_seccion_registrar_pago_imputado()
        
    # ----------------------------------------------------
    # TAB 4: PAGO TRADICIONAL (A FACTURAS)
    # ----------------------------------------------------
    with tab4_original:
        st.subheader("💵 Pago Tradicional (Aplicar a Facturas)")
        st.caption("Esta sección aplica automáticamente el pago a las facturas pendientes más antiguas.")

        df_revendedores_all = fetch_df("SELECT id, nombre FROM revendedores ORDER BY nombre")
        if df_revendedores_all.empty:
            st.info("No hay revendedores en la base de datos.")
            return

        df_estado_display = df_revendedores_all.copy()
        df_estado_display["RevendedorDisplay"] = df_estado_display["nombre"].astype(str) + " (ID:" + df_estado_display["id"].astype(str) + ")"
        opciones = df_estado_display["RevendedorDisplay"].tolist()

        seleccionado_pago = st.selectbox(
            "Seleccione un revendedor para registrar pago:",
            opciones,
            key="pago_tradicional_revendedor_select"
        )

        try:
            revendedor_id_tradicional = int(seleccionado_pago.split("ID:")[1].strip(")"))
        except Exception:
            st.error("No se pudo obtener el id del revendedor seleccionado.")
            return

        col1, col2 = st.columns(2)
        with col1:
            monto_pago = st.number_input(
                "Monto a pagar:",
                min_value=0.01,
                value=0.01,
                step=1.0,
                format="%.2f",
                key="monto_tradicional"
            )
        with col2:
            fecha_pago_tradicional = st.date_input("Fecha de pago:", value=date.today(), key="fecha_pago_tradicional")

        if st.button("Registrar Pago y Distribuir a Facturas"):
            if registrar_pago_y_distribuir(revendedor_id_tradicional, monto_pago, fecha_pago_tradicional.strftime("%Y-%m-%d")):
                st.success("🎉 ¡Pago registrado y distribuido con éxito!")
                st.rerun()

    # ----------------------------------------------------
    # TAB 6: SEGUIMIENTO DE COBRANZA (Integra seguimiento_cobranza.py)
    # ----------------------------------------------------
    with tab6_seguimiento:
        # Se pasa el objeto de la pestaña (tab6_seguimiento) como el contenedor.
        app_cobranza_interface(parent_st=tab6_seguimiento)
        
# =================================================================================================
# RUN
# =================================================================================================
if __name__ == "__main__":
    st.set_page_config(layout="wide") # Se mantiene la configuración 'wide' para ayudar con el espacio.
    mostrar_gestion_cobranza()