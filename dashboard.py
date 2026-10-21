
import streamlit as st
import requests
from bs4 import BeautifulSoup
import sqlite3
from datetime import datetime
import pandas as pd
import time
import plotly.express as px

# --- FUNCIONES DÓLAR (idénticas a tu código funcional) ---

def crear_tabla_dolar():
    conn = sqlite3.connect('minerva.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS cotizacion_dolar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            compra REAL NOT NULL,
            venta REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def insertar_o_actualizar_cotizacion_dolar(compra, venta):
    conn = sqlite3.connect('minerva.db')
    c = conn.cursor()
    fecha_hora_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("DELETE FROM cotizacion_dolar")
    c.execute("INSERT INTO cotizacion_dolar (fecha_hora, compra, venta) VALUES (?, ?, ?)",
              (fecha_hora_actual, compra, venta))
    conn.commit()
    conn.close()

def obtener_ultima_cotizacion_dolar():
    conn = sqlite3.connect('minerva.db')
    c = conn.cursor()
    c.execute("SELECT compra, venta, fecha_hora FROM cotizacion_dolar ORDER BY fecha_hora DESC LIMIT 1")
    data = c.fetchone()
    conn.close()
    if data:
        return {"compra": data[0], "venta": data[1], "fecha": data[2]}
    return None

def crear_tabla_historial_cambios():
    conn = sqlite3.connect('minerva.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS historial_cambios_dolar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_cambio TEXT NOT NULL,
            tipo_cambio TEXT NOT NULL,
            valor_anterior REAL,
            valor_nuevo REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def insertar_cambio_dolar(tipo_cambio, valor_anterior, valor_nuevo):
    conn = sqlite3.connect('minerva.db')
    c = conn.cursor()
    fecha_hora_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("INSERT INTO historial_cambios_dolar (fecha_cambio, tipo_cambio, valor_anterior, valor_nuevo) VALUES (?, ?, ?, ?)",
              (fecha_hora_actual, tipo_cambio, valor_anterior, valor_nuevo))
    conn.commit()
    conn.close()

def obtener_historial_cambios():
    conn = sqlite3.connect('minerva.db')
    df = pd.read_sql_query("SELECT fecha_cambio, tipo_cambio, valor_anterior, valor_nuevo FROM historial_cambios_dolar ORDER BY fecha_cambio DESC LIMIT 20", conn)
    conn.close()
    return df

def obtener_precio_dolar_bna_real():
    url = "https://www.bna.com.ar/Personas"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        main_tag = soup.find('main')
        if not main_tag:
            st.warning("No se encontró la etiqueta <main>.")
            return None
        target_div = main_tag
        try:
            target_div = target_div.find_all('div', recursive=False)[0]
            target_div = target_div.find_all('div', recursive=False)[0]
            target_div = target_div.find_all('div', recursive=False)[3]
            target_div = target_div.find_all('div', recursive=False)[0]
            target_div = target_div.find_all('div', recursive=False)[0]
            target_div = target_div.find_all('div', recursive=False)[0]
            target_div = target_div.find_all('div', recursive=False)[0]
        except IndexError:
            st.warning("La estructura de divs no coincide con el XPath. Los índices pueden haber cambiado.")
            return None
        table = target_div.find('table')
        if not table:
            st.warning("No se encontró la tabla en la ruta especificada.")
            return None
        tbody = table.find('tbody')
        if not tbody:
            st.warning("No se encontró el tbody en la tabla.")
            return None
        first_row = tbody.find_all('tr', recursive=False)
        if not first_row:
            st.warning("No se encontró la primera fila (tr) en el tbody.")
            return None
        row_data = first_row[0]
        cols = row_data.find_all('td')
        if len(cols) >= 3:
            compra_raw = cols[1].get_text(strip=True)
            venta_raw = cols[2].get_text(strip=True)
            compra = compra_raw.replace('.', '').replace(',', '.')
            venta = venta_raw.replace('.', '').replace(',', '.')
            try:
                return {"compra": float(compra), "venta": float(venta)}
            except ValueError:
                st.warning(f"Valores extraídos no numéricos: Compra='{compra_raw}', Venta='{venta_raw}'")
                return None
        else:
            st.warning("No se encontraron suficientes columnas (td) en la fila esperada.")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error de conexión al intentar obtener datos del Banco Nación: {e}")
        return None
    except Exception as e:
        st.error(f"Error inesperado al procesar la página: {e}")
        return None

# --- FUNCIONES GENERALES DE DASHBOARD ---

def fetch_data(query, params=None):
    with sqlite3.connect('minerva.db') as conn:
        df = pd.read_sql_query(query, conn, params=params)
    return df

def mostrar_dataframe_bonito(df, titulo="Detalle", formato_condicional=None):
    st.markdown(f"<h3 style='color:#0072C6;text-align:center;'>{titulo}</h3>", unsafe_allow_html=True)
    with st.expander(f"Ver {titulo}", expanded=True):
        if formato_condicional:
            st.dataframe(formato_condicional(df), use_container_width=True, hide_index=True)
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Descargar CSV",
            data=csv,
            file_name=f"{titulo.replace(' ','_').lower()}.csv",
            mime='text/csv',
            key=f"download_{titulo}"
        )

def formato_stock_bajo(df):
    if 'cantidad' in df.columns:
        return df.style.applymap(
            lambda v: 'background-color: #ffcccc' if isinstance(v, (int, float)) and v < 100 else '',
            subset=['cantidad']
        )
    if 'Stock Actual' in df.columns:
        return df.style.applymap(
            lambda v: 'background-color: #ffcccc' if isinstance(v, (int, float)) and v < 100 else '',
            subset=['Stock Actual']
        )
    return df

# --- DASHBOARD PRINCIPAL ---

def mostrar_dashboard():
    crear_tabla_dolar()
    crear_tabla_historial_cambios()

    st.markdown("""
    <style>
    body { background-color: #f7f9fc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    .metric-card { background: white; border-radius: 10px; padding: 25px 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; margin-bottom: 10px; transition: box-shadow 0.3s ease; }
    .metric-card:hover { box-shadow: 0 8px 20px rgba(0,0,0,0.15); }
    .metric-value { font-size: 48px; font-weight: 700; color: #0072C6; margin-bottom: 5px; }
    .metric-label { font-size: 18px; font-weight: 600; color: #555; }
    .stButton>button { background-color: #0072C6; color: white; font-weight: 600; border-radius: 8px; padding: 10px 18px; width: 100%; transition: background-color 0.3s ease; margin-top: 10px; }
    .stButton>button:hover { background-color: #005a9e; }
    .dataframe-container { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); max-height: 500px; overflow-y: auto; margin-bottom: 40px; }
    h1, h2 { color: #0072C6; margin-top: 30px; margin-bottom: 20px; text-align: center; }
    .fecha-cotizacion { font-size: 14px; color: #999; font-style: italic; margin-top: -10px; text-align: right; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<h1>Minerva Productos Capilares</h1>", unsafe_allow_html=True)
    st.markdown("<h2>🏭 Dashboard de Producción y Stock</h2>", unsafe_allow_html=True)

    # --- Consultas principales ---
    try:
        pedidos = fetch_data("""
            SELECT COUNT(*) AS total
            FROM producciones p
            JOIN pedidos_produccion pp ON p.pedido_id = pp.id
            WHERE p.estado IN ('pendiente', 'proceso', 'en_proceso');
        """).iloc[0]['total']
    except Exception as e:
        pedidos = None
        st.error(f"Error al obtener pedidos activos: {e}")

    try:
        stock_bajo = fetch_data("""
            SELECT COUNT(*) AS total
            FROM stock_materias_primas s
            WHERE s.cantidad_actual < 500;  -- Cambiado: de 'cantidad' a 'cantidad_actual'
        """).iloc[0]['total']
    except Exception as e:
        stock_bajo = None
        st.error(f"Error al obtener stock bajo: {e}")

    try:
        lotes_sin_envasar = fetch_data("""
            SELECT COUNT(*) AS total
            FROM producciones p
            WHERE p.estado = 'producido'
            AND p.id NOT IN (
                SELECT oe.produccion_id FROM ordenes_envasado oe
            );
        """).iloc[0]['total']
    except Exception as e:
        lotes_sin_envasar = None
        st.error(f"Error al obtener lotes sin envasar: {e}")

    # --- Panel de métricas principales ---
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{pedidos if pedidos is not None else 'Error'}</div>
            <div class="metric-label">Pedidos Activos</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔍 Ver Detalle Pedidos", key="btn_pedidos"):
            try:
                df_pedidos = fetch_data("""
                    SELECT p.id AS 'ID', pp.fecha AS 'Fecha', c.nombre AS 'Cliente', p.estado AS 'Estado', pp.cantidad AS 'Cantidad (L)', pp.numero_pedido AS 'Nro Pedido'
                    FROM producciones p
                    JOIN pedidos_produccion pp ON p.pedido_id = pp.id
                    LEFT JOIN clientes c ON pp.cliente_id = c.id
                    WHERE p.estado IN ('pendiente', 'proceso', 'en_proceso')
                    ORDER BY pp.fecha DESC LIMIT 50;
                """)
                mostrar_dataframe_bonito(df_pedidos, titulo="Pedidos Activos")
            except Exception as e:
                st.error(f"Error al obtener detalle de pedidos: {e}")

    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{stock_bajo if stock_bajo is not None else 'Error'}</div>
            <div class="metric-label">Stock Bajo MP</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔍 Ver Stock Bajo", key="btn_stock"):
            try:
                df_stock_bajo = fetch_data("""
                    SELECT 
                        m.nombre AS 'Materia Prima', 
                        ROUND(s.cantidad_actual, 2) AS 'Stock Actual', -- Cambiado y redondeado
                        m.unidad AS 'Unidad'
                    FROM stock_materias_primas s
                    JOIN materias_primas m ON s.materia_prima_id = m.id
                    WHERE s.cantidad_actual < 500                      -- Filtro correcto
                    ORDER BY s.cantidad_actual ASC LIMIT 150;
                """)
                mostrar_dataframe_bonito(df_stock_bajo, titulo="Stock Bajo", formato_condicional=formato_stock_bajo)
                
                # El gráfico también se actualizará automáticamente al usar 'Stock Actual'
                if not df_stock_bajo.empty:
                    fig_stock = px.bar(df_stock_bajo, x='Materia Prima', y='Stock Actual',
                                       title='Materias Primas con Stock Bajo (Real)',
                                       labels={'Materia Prima': 'Materia Prima', 'Stock Actual': 'Cantidad Real'})
                    st.plotly_chart(fig_stock, use_container_width=True)
            except Exception as e:
                st.error(f"Error al obtener detalle de stock: {e}")

    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{lotes_sin_envasar if lotes_sin_envasar is not None else 'Error'}</div>
            <div class="metric-label">Lotes Sin Envasar</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔍 Ver Lotes", key="btn_lotes"):
            try:
                df_lotes = fetch_data("""
                    SELECT p.lote AS 'Lote', p.fecha AS 'Fecha', pp.numero_pedido AS 'Nro Pedido', c.nombre AS 'Cliente', p.estado AS 'Estado'
                    FROM producciones p
                    JOIN pedidos_produccion pp ON p.pedido_id = pp.id
                    LEFT JOIN clientes c ON pp.cliente_id = c.id
                    WHERE p.estado = 'producido'
                      AND p.id NOT IN (
                          SELECT oe.produccion_id FROM ordenes_envasado oe
                      )
                    ORDER BY p.fecha DESC
                    LIMIT 150;
                """)
                mostrar_dataframe_bonito(df_lotes, titulo="Lotes Sin Envasar")
            except Exception as e:
                st.error(f"Error al obtener lotes sin envasar: {e}")

    with col4:
        # Panel de cotización dólar con scraping y guardado
        ultima = obtener_ultima_cotizacion_dolar()
        compra = ultima['compra'] if ultima else None
        venta = ultima['venta'] if ultima else None
        fecha = ultima['fecha'] if ultima else None

        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{f"${compra:.2f} / ${venta:.2f}" if compra is not None and venta is not None else "N/D"}</div>
            <div class="metric-label">Dólar Compra / Venta</div>
            <div class="fecha-cotizacion">{fecha if fecha else ""}</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🌐 Actualizar Cotización BNA"):
            st.info("Intentando obtener la cotización...")
            with st.spinner("Cargando datos..."):
                ultima_cotizacion_guardada = obtener_ultima_cotizacion_dolar()
                dolar_data = obtener_precio_dolar_bna_real()
                time.sleep(1)
            if dolar_data:
                insertar_o_actualizar_cotizacion_dolar(dolar_data['compra'], dolar_data['venta'])
                st.success(f"Cotización actualizada: Compra ${dolar_data['compra']:.2f}, Venta ${dolar_data['venta']:.2f}")
                # Guardar cambios en historial si corresponde
                if ultima_cotizacion_guardada:
                    if dolar_data['compra'] != ultima_cotizacion_guardada['compra']:
                        insertar_cambio_dolar("compra", ultima_cotizacion_guardada['compra'], dolar_data['compra'])
                    if dolar_data['venta'] != ultima_cotizacion_guardada['venta']:
                        insertar_cambio_dolar("venta", ultima_cotizacion_guardada['venta'], dolar_data['venta'])
                else:
                    insertar_cambio_dolar("compra", None, dolar_data['compra'])
                    insertar_cambio_dolar("venta", None, dolar_data['venta'])
                st.rerun()
            else:
                st.error("No se pudo obtener la cotización del dólar. Intente de nuevo.")

        # Historial de cambios
        with st.expander("Ver historial de cambios"):
            df_hist = obtener_historial_cambios()
            if not df_hist.empty:
                st.dataframe(df_hist, use_container_width=True, hide_index=True)
            else:
                st.info("No hay historial de cambios registrado.")

    st.markdown("<hr>", unsafe_allow_html=True)

    # --- Gráfico de estado de pedidos ---
    try:
        df_estados_pedidos = fetch_data("""
            SELECT p.estado, COUNT(p.id) AS cantidad
            FROM producciones p
            GROUP BY p.estado;
        """)
        if not df_estados_pedidos.empty:
            fig_pie = px.pie(df_estados_pedidos, values='cantidad', names='estado',
                             title='Distribución de Pedidos por Estado')
            st.plotly_chart(fig_pie, use_container_width=True)
    except Exception as e:
        st.error(f"Error al generar gráfico de estados de pedidos: {e}")

    st.markdown("<hr>", unsafe_allow_html=True)

    # --- Últimas compras ---
    st.markdown("<h2>🧾 Últimas Compras de Materias Primas</h2>", unsafe_allow_html=True)

    try:
        compras_df = fetch_data("""
            SELECT c.fecha AS 'Fecha', p.nombre AS 'Proveedor', m.nombre AS 'Materia Prima',
                     c.numero_comprobante AS 'Comprobante', c.cantidad AS 'Cantidad', c.precio_unitario AS 'Precio Unitario'
            FROM compras_materia_prima c
            JOIN proveedores p ON c.proveedor_id = p.id
            JOIN materias_primas m ON c.materia_prima_id = m.id
            ORDER BY c.fecha DESC LIMIT 10;
        """)
        mostrar_dataframe_bonito(compras_df, titulo="Últimas Compras")
    except Exception as e:
        st.error(f"Error al obtener últimas compras: {e}")

    st.markdown("<hr>", unsafe_allow_html=True)

    # --- Últimos movimientos de stock de productos envasados ---
    st.markdown("<h2>📦 Últimos Movimientos de Productos Envasados</h2>", unsafe_allow_html=True)

    try:
    # Obtener los últimos movimientos de productos envasados sin usar la tabla movimientos_productos_envasados
        movimientos_envasados_df = fetch_data("""
        SELECT
            spe.fecha_ingreso AS 'Fecha',
            c.nombre AS 'Cliente',
            r.nombre AS 'Receta',
            e.descripcion AS 'Envase',
            oe.cantidad_unidades AS 'Cantidad',
            'Egreso' AS 'Tipo',
            spe.lote AS 'Lote',
            oe.id AS 'Orden de Envasado',
            spe.cantidad as 'Stock'
        FROM stock_productos_envasados spe
        JOIN productos_clientes pc ON spe.receta_id = pc.id_receta
        JOIN ordenes_envasado oe ON oe.producto_cliente_id = pc.id
        JOIN clientes c ON spe.cliente_id = c.id
        JOIN recetas r ON spe.receta_id = r.id
        JOIN envases e ON spe.envase_id = e.id
        WHERE spe.cantidad > 0
        ORDER BY spe.fecha_ingreso DESC
        LIMIT 10;
    """)
        mostrar_dataframe_bonito(movimientos_envasados_df, titulo="Últimos Movimientos de Productos Envasados")
    except Exception as e:
        st.error(f"Error al obtener últimos movimientos de productos envasados: {e}")