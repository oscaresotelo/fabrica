import streamlit as st
import sqlite3
import pandas as pd
from io import BytesIO
import plotly.express as px

# Configuración de la página
st.set_page_config(layout="wide", page_title="Análisis de Costos Minerva")

# Conexión a la base de datos SQLite
DATABASE = 'minerva.db'
CLIENTE_ID = 8 # ID del cliente BEKIM

# Funciones de consulta a la base de datos con caché
# ---------------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def obtener_datos_generales(valor_dolar):
    try:
        conn = sqlite3.connect(DATABASE)
        query = f"""
        SELECT
            p.nombre AS nombre_producto,
            p.id AS producto_id,
            e.descripcion AS tipo_envase,
            r.nombre AS nombre_receta,
            e.capacidad_litros AS capacidad_envase,
            COALESCE(cmp_envases.precio_unitario, 0) AS precio_envase,
            (SUM(ri.cantidad * cmp.precio_unitario *
                CASE WHEN mp.unidad = 'LITROS' THEN 1 ELSE CASE WHEN mp.unidad = 'KG' THEN 1 ELSE 0 END END) / 200 * {valor_dolar}
            ) AS costo_materia_prima,
            (COALESCE(cmp_envases.precio_unitario * {valor_dolar}, 0)) AS costo_envase,
            (SUM(ri.cantidad * cmp.precio_unitario *
                CASE WHEN mp.unidad = 'LITROS' THEN 1 ELSE CASE WHEN mp.unidad = 'KG' THEN 1 ELSE 0 END END) / 200 * {valor_dolar} * e.capacidad_litros) + COALESCE(cmp_envases.precio_unitario * {valor_dolar} * e.capacidad_litros, 0) AS precio_total_producto,
            tc.unidades_por_caja AS unidades_por_caja,
            (tc.unidades_por_caja * ((SUM(ri.cantidad * cmp.precio_unitario *
                CASE WHEN mp.unidad = 'LITROS' THEN 1 ELSE CASE WHEN mp.unidad = 'KG' THEN 1 ELSE 0 END END) / 200 * {valor_dolar} * e.capacidad_litros) + COALESCE(cmp_envases.precio_unitario * {valor_dolar} * e.capacidad_litros, 0))) AS importe_total_caja
        FROM productos p
        JOIN envases e ON p.envase_id = e.id
        JOIN recetas r ON p.id_receta = r.id
        JOIN receta_ingredientes ri ON r.id = ri.receta_id
        JOIN materias_primas mp ON ri.materia_prima_id = mp.id
        LEFT JOIN compras_materia_prima cmp ON mp.id = cmp.materia_prima_id
        LEFT JOIN
            (SELECT envase_id, precio_unitario FROM (SELECT envase_id, precio_unitario, fecha_ingreso, ROW_NUMBER() OVER (PARTITION BY envase_id ORDER BY fecha_ingreso DESC) as rn FROM entradas_envases) WHERE rn = 1) AS cmp_envases ON e.id = cmp_envases.envase_id
        LEFT JOIN tipo_cajas tc ON p.tipo_caja_id = tc.id
        GROUP BY p.nombre, p.id, e.descripcion, r.nombre, e.capacidad_litros, cmp_envases.precio_unitario, tc.unidades_por_caja;
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except sqlite3.Error as e:
        st.error(f"Error al conectar a la base de datos: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def obtener_datos_bekim(valor_dolar):
    try:
        conn = sqlite3.connect(DATABASE)
        query = f"""
        SELECT
            r.id AS receta_id,
            r.nombre AS nombre_receta,
            SUM(ri.cantidad * cmp.precio_unitario) AS costo_bruto_materia_prima,
            (SUM(ri.cantidad * cmp.precio_unitario) * {valor_dolar}) AS costo_materia_prima_ars
        FROM
            recetas AS r
        JOIN
            receta_ingredientes AS ri ON r.id = ri.receta_id
        JOIN
            materias_primas AS mp ON ri.materia_prima_id = mp.id
        LEFT JOIN
            (
                SELECT
                    materia_prima_id,
                    precio_unitario
                FROM
                    compras_materia_prima
                WHERE
                    (materia_prima_id, fecha) IN (
                        SELECT materia_prima_id, MAX(fecha)
                        FROM compras_materia_prima
                        GROUP BY materia_prima_id
                    )
            ) AS cmp ON mp.id = cmp.materia_prima_id
        WHERE
            r.cliente_id = {CLIENTE_ID}
        GROUP BY
            r.id, r.nombre;
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except sqlite3.Error as e:
        st.error(f"Error al conectar a la base de datos: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def obtener_detalle_ingredientes(receta_id, valor_dolar):
    try:
        conn = sqlite3.connect(DATABASE)
        query = f"""
        SELECT
            mp.nombre AS nombre_ingrediente,
            ri.cantidad,
            cmp.precio_unitario,
            (ri.cantidad * cmp.precio_unitario) AS costo_bruto_ingrediente,
            (ri.cantidad * cmp.precio_unitario * {valor_dolar}) AS costo_ars_ingrediente
        FROM
            receta_ingredientes AS ri
        JOIN
            materias_primas AS mp ON ri.materia_prima_id = mp.id
        LEFT JOIN
            (
                SELECT
                    materia_prima_id,
                    precio_unitario
                FROM
                    compras_materia_prima
                WHERE
                    (materia_prima_id, fecha) IN (
                        SELECT materia_prima_id, MAX(fecha)
                        FROM compras_materia_prima
                        GROUP BY materia_prima_id
                    )
            ) AS cmp ON mp.id = cmp.materia_prima_id
        WHERE
            ri.receta_id = {receta_id}
        GROUP BY
            mp.nombre, ri.cantidad, cmp.precio_unitario;
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except sqlite3.Error as e:
        st.error(f"Error al obtener el detalle de los ingredientes: {e}")
        return pd.DataFrame()

# ---- TÍTULO Y WIDGETS PRINCIPALES ----
st.title('📈 Análisis de Costos Minerva')
st.markdown("Una herramienta unificada para visualizar y analizar los costos de producción.")
st.markdown("---")

# ---- BARRA LATERAL PARA SELECCIÓN DE MODO Y VALOR DEL DÓLAR ----
st.sidebar.header('Opciones de la Aplicación')
modo_seleccionado = st.sidebar.radio(
    "Selecciona el modo de análisis:",
    ('Análisis General', 'Análisis Cliente BEKIM')
)

valor_dolar = st.sidebar.number_input(
    'Ingrese el valor del dólar:',
    value=1380.0,
    min_value=0.0,
    step=0.01,
    help="El valor del dólar para convertir los costos."
)

# ---- CONTENIDO PRINCIPAL BASADO EN EL MODO SELECCIONADO ----

if modo_seleccionado == 'Análisis General':
    st.subheader('Análisis General de Costos de Productos')
    df_resultados = obtener_datos_generales(valor_dolar)

    if not df_resultados.empty:
        # ---- MÉTRICAS CLAVE ----
        st.subheader('Resumen Rápido')
        col1, col2, col3 = st.columns(3)
        
        total_productos = len(df_resultados)
        costo_promedio_litro = df_resultados['costo_materia_prima'].mean()
        importe_promedio_caja = df_resultados['importe_total_caja'].mean()
        
        col1.metric("Total de Productos", f"{total_productos}")
        col2.metric("Costo Promedio de Materia Prima", f"${costo_promedio_litro:,.2f} ARS")
        col3.metric("Importe Promedio por Caja", f"${importe_promedio_caja:,.2f} ARS")
        
        st.markdown("---")
        
        # ---- VISUALIZACIÓN EN GRÁFICO DE BARRAS (con Plotly Express) ----
        st.subheader('📊 Top 10 Productos más Caros (por unidad)')
        df_top_10 = df_resultados.sort_values(by='precio_total_producto', ascending=False).head(10)
        fig_bar = px.bar(
            df_top_10,
            x='nombre_producto',
            y='precio_total_producto',
            title='Costo por Producto (Top 10)',
            labels={'nombre_producto': 'Producto', 'precio_total_producto': 'Costo Total ($ARS)'},
            hover_name='nombre_producto'
        )
        fig_bar.update_layout(
            xaxis_tickangle=-45,
            xaxis_title_font_size=14,
            yaxis_title_font_size=14,
            font=dict(size=12),
            margin=dict(b=150)
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        
        st.markdown("---")

        # ---- ANÁLISIS DETALLADO POR PRODUCTO (INTERACTIVO) ----
        st.subheader('🔍 Análisis Detallado por Producto')
        
        productos_list = df_resultados['nombre_producto'].unique().tolist()
        producto_seleccionado = st.selectbox("Selecciona un producto para ver su desglose de costos:", productos_list)
        
        if producto_seleccionado:
            producto_data = df_resultados[df_resultados['nombre_producto'] == producto_seleccionado].iloc[0]
            
            costo_mp = producto_data['costo_materia_prima']
            costo_envase = producto_data['costo_envase']
            costo_total = producto_data['precio_total_producto']
            
            df_pie = pd.DataFrame({
                'Componente': ['Materia Prima', 'Envase'],
                'Costo': [costo_mp, costo_envase]
            })
            
            col_pie, col_metrics = st.columns([1, 1])
            
            with col_pie:
                fig_pie = px.pie(
                    df_pie,
                    values='Costo',
                    names='Componente',
                    title=f'Desglose de Costos de {producto_seleccionado}',
                    labels={'Componente': 'Tipo de Costo', 'Costo': 'Valor ($ARS)'},
                    color='Componente',
                    color_discrete_map={'Materia Prima':'blue', 'Envase':'red'}
                )
                fig_pie.update_traces(textposition='inside', textinfo='percent+label', marker=dict(line=dict(color='#000000', width=2)))
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with col_metrics:
                st.markdown("#### Resumen del Producto Seleccionado")
                st.metric("Costo Total del Producto", f"${costo_total:,.2f} ARS")
                st.metric("Costo de Materia Prima", f"${costo_mp:,.2f} ARS")
                st.metric("Costo de Envase", f"${costo_envase:,.2f} ARS")
                
        st.markdown("---")

        # ---- TABLA DE DATOS (EN EXPANDER) ----
        with st.expander("Ver tabla completa de resultados"):
            st.dataframe(df_resultados.style.format({
                "capacidad_envase": "{:.2f} L",
                "precio_envase": "${:,.2f}",
                "costo_materia_prima": "${:,.2f}",
                "costo_envase": "${:,.2f}",
                "precio_total_producto": "${:,.2f}",
                "importe_total_caja": "${:,.2f}"
            }))
            
            @st.cache_data
            def convert_df_to_excel(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Resultados')
                processed_data = output.getvalue()
                return processed_data

            excel_data = convert_df_to_excel(df_resultados)

            st.download_button(
                label="Descargar datos como Excel",
                data=excel_data,
                file_name="resultados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    else:
        st.warning("No se pudieron obtener los datos. Verifica la conexión a la base de datos y la existencia de las tablas.")

# ---------------------------------------------------------------------------------
# -------------------- MODO DE ANÁLISIS PARA CLIENTE BEKIM ------------------------
# ---------------------------------------------------------------------------------

elif modo_seleccionado == 'Análisis Cliente BEKIM':
    st.subheader('Análisis de Costos de Recetas para el Cliente BEKIM')
    df_resultados = obtener_datos_bekim(valor_dolar)

    if not df_resultados.empty:
        # ---- MÉTRICAS CLAVE ----
        st.subheader('Resumen Rápido')
        col1, col2 = st.columns(2)
        
        total_recetas = len(df_resultados)
        costo_promedio_receta = df_resultados['costo_materia_prima_ars'].mean()
        
        col1.metric("Total de Recetas para BEKIM", f"{total_recetas}")
        col2.metric("Costo Promedio de Receta (200L)", f"${costo_promedio_receta:,.2f} ARS")
        
        st.markdown("---")
        
        # ---- VISUALIZACIÓN EN GRÁFICO DE BARRAS (con Plotly Express) ----
        st.subheader('📊 Costo de Recetas para BEKIM')
        df_sorted = df_resultados.sort_values(by='costo_materia_prima_ars', ascending=False)
        
        fig_bar = px.bar(
            df_sorted,
            x='nombre_receta',
            y='costo_materia_prima_ars',
            title='Costo de Recetas ($ARS)',
            labels={'nombre_receta': 'Receta', 'costo_materia_prima_ars': 'Costo Total ($ARS)'},
            hover_name='nombre_receta'
        )
        
        fig_bar.update_layout(
            xaxis_tickangle=-45,
            xaxis_title_font_size=14,
            yaxis_title_font_size=14,
            font=dict(size=12),
            margin=dict(b=150)
        )
        
        st.plotly_chart(fig_bar, use_container_width=True)
        
        st.markdown("---")

        # ---- ANÁLISIS DETALLADO POR RECETA (INTERACTIVO) ----
        st.subheader('🔍 Análisis Detallado de Ingredientes por Receta')
        
        recetas_dict = {row['receta_id']: row['nombre_receta'] for index, row in df_resultados.iterrows()}
        receta_id_seleccionada = st.selectbox(
            "Selecciona una receta para ver el desglose de sus ingredientes:",
            options=list(recetas_dict.keys()),
            format_func=lambda id: recetas_dict[id]
        )
        
        if receta_id_seleccionada:
            df_ingredientes = obtener_detalle_ingredientes(receta_id_seleccionada, valor_dolar)
            
            if not df_ingredientes.empty:
                st.markdown(f"**Desglose de costos para la receta:** {recetas_dict[receta_id_seleccionada]}")
                
                fig_ingredientes = px.bar(
                    df_ingredientes,
                    x='nombre_ingrediente',
                    y='costo_ars_ingrediente',
                    title='Costo de Ingredientes por Receta',
                    labels={'nombre_ingrediente': 'Ingrediente', 'costo_ars_ingrediente': 'Costo ($ARS)'}
                )
                fig_ingredientes.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_ingredientes, use_container_width=True)
                
                with st.expander("Ver tabla completa de ingredientes"):
                    st.dataframe(df_ingredientes.style.format({
                        "cantidad": "{:,.2f}",
                        "precio_unitario": "${:,.2f}",
                        "costo_bruto_ingrediente": "{:,.2f}",
                        "costo_ars_ingrediente": "${:,.2f}"
                    }))
            else:
                st.warning("No se encontraron ingredientes para esta receta.")
                
        st.markdown("---")

        # ---- TABLA DE DATOS GENERAL (EN EXPANDER) ----
        with st.expander("Ver tabla completa de resultados de recetas"):
            st.dataframe(df_resultados.style.format({
                "costo_bruto_materia_prima": "{:,.2f}",
                "costo_materia_prima_ars": "${:,.2f}"
            }))
            
            @st.cache_data
            def convert_df_to_excel(df):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Resultados')
                processed_data = output.getvalue()
                return processed_data

            excel_data = convert_df_to_excel(df_resultados)

            st.download_button(
                label="Descargar datos como Excel",
                data=excel_data,
                file_name="resultados_bekim.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    else:
        st.warning("No se encontraron recetas para el cliente BEKIM. Verifica que el ID del cliente y las tablas existan en la base de datos.")