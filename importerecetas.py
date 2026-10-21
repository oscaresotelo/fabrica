import streamlit as st
import sqlite3
import pandas as pd
from io import BytesIO
import plotly.express as px

# Configuración de la página
st.set_page_config(layout="wide", page_title="Análisis de Costos Minerva")

# Conexión a la base de datos SQLite
DATABASE = 'minerva.db'

@st.cache_data(ttl=3600)
def obtener_datos(valor_dolar):
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

# ---- TÍTULO Y WIDGETS PRINCIPALES ----
st.title('📈 Análisis de Costos de Productos')
st.markdown("Una herramienta para visualizar y calcular el costo de los productos en base al valor del dólar.")
st.markdown("---")

# ---- BARRA LATERAL PARA INPUTS Y OPCIONES ----
st.sidebar.header('Opciones de Cálculo')
valor_dolar = st.sidebar.number_input(
    'Ingrese el valor del dólar:',
    value=1380.0,
    min_value=0.0,
    step=0.01,
    help="El valor del dólar para convertir los costos."
)

# ---- CONTENIDO PRINCIPAL ----
df_resultados = obtener_datos(valor_dolar)

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
        
        # Crear un DataFrame para el gráfico de torta
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
        
        # Convertir DataFrame a Excel
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