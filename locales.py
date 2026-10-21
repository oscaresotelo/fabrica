import streamlit as st
import pandas as pd
import numpy as np # Para generar datos aleatorios
import time 

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Buscador de Negocios Capilares - Argentina (v2)",
    layout="wide", # Usamos wide para la tabla grande
    initial_sidebar_state="collapsed"
)

# --- FUNCIÓN DE SIMULACIÓN MEJORADA (Genera 100+ resultados) ---
def obtener_datos_negocios_mock(producto, provincia, anio_inicio, n_resultados=120):
    """
    Genera una gran cantidad de datos simulados para demostrar una tabla robusta.
    """
    st.info(f"Simulando la búsqueda de **{producto}** en **{provincia}** desde el año **{anio_inicio}** con {n_resultados} resultados base...")
    time.sleep(1.5) 

    # Listas de datos para la generación
    nombres_base = ['Peluquería', 'Estética', 'Distribuidora', 'Tienda', 'Salón']
    apellidos_base = ['Sol', 'Luna', 'Trendy', 'Glamour', 'Esplendor', 'Premium']
    
    provincias_arg = [
        'Buenos Aires (CABA)', 'Córdoba (Capital)', 'Mendoza (Godoy Cruz)', 
        'Santa Fe (Rosario)', 'Tucumán (Capital)', 'Salta (Centro)', 
        'Río Negro (Bariloche)', 'Misiones (Posadas)'
    ]
    
    # Generación de datos
    data = {}
    
    data['Nombre del Negocio'] = [
        f"{np.random.choice(nombres_base)} {np.random.choice(apellidos_base)} {i+1}" 
        for i in range(n_resultados)
    ]
    
    # Generar números de teléfono aleatorios (formato argentino)
    data['Teléfono'] = [
        f'+54 9 {np.random.randint(11, 99):02} {np.random.randint(1000, 9999):04}-{np.random.randint(1000, 9999):04}' 
        for _ in range(n_resultados)
    ]
    
    # Asignar provincias de manera aleatoria
    data['Provincia/Localidad'] = np.random.choice(provincias_arg, n_resultados).tolist()
    
    # Asignar años de actividad aleatorios (entre 2015 y 2025)
    data['Año de Venta (Simulado)'] = np.random.randint(2015, 2026, n_resultados).tolist()

    df_completo = pd.DataFrame(data)
    
    # --- FILTRADO DE DATOS (Lo que realmente hace la herramienta) ---
    
    # 1. Filtro por Año
    df_filtrado_anio = df_completo[df_completo['Año de Venta (Simulado)'] >= int(anio_inicio)]
    
    # 2. Filtro por Provincia (si no es "Todas")
    if provincia != "Todas":
        # Usamos .str.contains para buscar el nombre de la provincia
        df_final = df_filtrado_anio[df_filtrado_anio['Provincia/Localidad'].str.contains(provincia)]
    else:
        df_final = df_filtrado_anio
        
    return df_final

# --- INTERFAZ DE STREAMLIT ---

st.title("💇 Buscador de Negocios Capilares en Argentina")
st.subheader("Herramienta conceptual de raspado de datos (Simulación v2)")

# --- Formulario de Entrada ---
with st.form("busqueda_form"):
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        producto_busqueda = st.text_input(
            "Producto Capilar:", 
            value="Tratamientos Keratina"
        )
    
    with col2:
        provincia_opciones = [
            "Todas", "Buenos Aires", "Córdoba", "Mendoza", "Santa Fe", "Tucumán", "Salta", "Río Negro"
        ]
        provincia_busqueda = st.selectbox(
            "Provincia/Localidad de Enfoque:", 
            provincia_opciones
        )
    
    with col3:
        anio_busqueda = st.selectbox(
            "Negocios con actividad desde el Año:",
            options=range(2018, 2026),
            index=3 # Por defecto, selecciona 2021
        )
    
    submitted = st.form_submit_button("🔍 Iniciar Búsqueda")

# --- Lógica de Búsqueda y Resultados ---
if submitted:
    
    with st.spinner("Procesando la simulación y aplicando filtros..."):
        
        resultados_df = obtener_datos_negocios_mock(
            producto_busqueda, 
            provincia_busqueda, 
            anio_busqueda
        )

    st.success(f"✅ Búsqueda completada. Se encontraron **{len(resultados_df)}** negocios que cumplen los criterios.")
    
    # Mostrar el DataFrame de resultados
    st.dataframe(resultados_df, use_container_width=True)
    
    # Opción para descargar los datos
    csv = resultados_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Descargar resultados como CSV",
        data=csv,
        file_name='negocios_capilares_v2.csv',
        mime='text/csv',
    )
    
    st.caption("🚨 **Recordatorio:** Estos son datos simulados generados aleatoriamente para demostrar el funcionamiento de la aplicación.")