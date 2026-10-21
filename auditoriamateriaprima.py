import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# Configuración de página con un diseño moderno y ancho
st.set_page_config(
    page_title="Auditoría Pro - Minerva", 
    page_icon="🛡️",
    layout="wide"
)

def get_connection():
    """Establece conexión con la base de datos SQLite."""
    return sqlite3.connect('minerva.db')

def get_data(fecha_inicio, fecha_fin):
    """
    Consulta principal modificada:
    Trae los registros individuales de egreso para poder auditar
    las fechas exactas y cantidades de uso de cada materia prima en cada receta.
    """
    conn = get_connection()
    # Traemos 'mmp.fecha' y la cantidad individual sin agrupar por completo en SQL
    # para poder procesar la cronología en el frontend con Pandas.
    query = """
    SELECT 
        mp.id AS mp_id,
        mp.nombre AS materia_prima,
        r.nombre AS receta,
        mmp.fecha AS fecha_movimiento,
        ABS(mmp.cantidad) AS cantidad,
        mp.unidad
    FROM movimientos_materia_prima mmp
    JOIN materias_primas mp ON mmp.materia_prima_id = mp.id
    JOIN lotes l ON mmp.lote = l.numero
    JOIN recetas r ON l.receta_id = r.id
    WHERE mmp.tipo_movimiento = 'egreso'
      AND mmp.fecha BETWEEN ? AND ?
    ORDER BY mmp.fecha DESC, mp.nombre ASC
    """
    df = pd.read_sql_query(query, conn, params=[str(fecha_inicio), str(fecha_fin)])
    conn.close()
    return df

st.title("🛡️ Auditoría General de Egresos")
st.markdown(
    "Filtra por rango de fechas para analizar el consumo real de cada insumo, "
    "las recetas de destino y las **fechas exactas de utilización**."
)

# Sidebar de filtros temporales
with st.sidebar:
    st.header("⚙️ Rango de Fechas")
    f_inicio = st.date_input("Desde", datetime(2025, 12, 1))
    f_fin = st.date_input("Hasta", datetime(2026, 1, 12))
    
    st.write("---")
    # Botón principal para procesar los datos
    ejecutar = st.button("Calcular Auditoría", type="primary", use_container_width=True)

if ejecutar:
    df = get_data(f_inicio, f_fin)
    
    if not df.empty:
        # Asegurar formato de fecha legible
        df['fecha_movimiento'] = pd.to_datetime(df['fecha_movimiento']).dt.strftime('%Y-%m-%d %H:%M')
        
        # --- RESUMEN GENERAL POR MATERIA PRIMA ---
        st.subheader("📊 Resumen General de Consumo")
        
        # Agrupamos con Pandas para la tabla general resumida
        resumen_general = df.groupby(['materia_prima', 'unidad']).agg(
            total_egresado=('cantidad', 'sum'),
            cant_recetas=('receta', 'nunique') # Recetas únicas en las que se usó
        ).reset_index()
        
        resumen_general.columns = ['Insumo', 'Unidad', 'Total Consumido', 'Recetas Distintas']
        
        # Aplicamos formato de decimales para mejor legibilidad
        resumen_general['Total Consumido'] = resumen_general['Total Consumido'].map('{:,.2f}'.format)
        
        st.dataframe(resumen_general, use_container_width=True, hide_index=True)
        
        st.divider()
        
        # --- DESGLOSE DETALLADO POR INSUMO (AUDITORÍA DE RECETAS Y FECHAS) ---
        st.subheader("🧪 Desglose de Uso y Trazabilidad Cronológica")
        st.caption("Haz clic en cada insumo para ver los detalles de consumo, recetas asociadas y su historial de fechas.")
        
        # Obtenemos la lista de materias primas únicas
        lista_mp = df['materia_prima'].unique()
        
        for mp in lista_mp:
            # Filtramos todos los registros correspondientes a esta Materia Prima
            detalle_mp = df[df['materia_prima'] == mp]
            total_mp = detalle_mp['cantidad'].sum()
            unidad_mp = detalle_mp['unidad'].iloc[0]
            
            # Título expansor interactivo con métrica de consumo total
            with st.expander(f"📦 **{mp}** | Total consumido: {total_mp:.2f} {unidad_mp}"):
                
                # Creamos dos pestañas: una para el resumen por receta, y otra para las fechas exactas
                tab_resumen, tab_fechas = st.tabs(["📋 Consumo por Receta", "📅 Registro de Fechas (Auditoría)"])
                
                # PESTAÑA 1: Resumen agrupado por Receta con Gráfico
                with tab_resumen:
                    col_tabla, col_grafico = st.columns([0.5, 0.5])
                    
                    # Agrupamos por receta para mostrar totales
                    recetas_agrupadas = detalle_mp.groupby('receta').agg(
                        cantidad_total=('cantidad', 'sum')
                    ).reset_index().sort_values(by='cantidad_total', ascending=False)
                    
                    with col_tabla:
                        st.markdown(f"**Distribución de {mp} por Receta destino:**")
                        st.dataframe(
                            recetas_agrupadas.rename(columns={
                                'receta': 'Receta Destino',
                                'cantidad_total': f'Total Usado ({unidad_mp})'
                            }),
                            use_container_width=True,
                            hide_index=True
                        )
                    
                    with col_grafico:
                        st.markdown("**Participación de Consumo**")
                        st.bar_chart(recetas_agrupadas.set_index('receta')['cantidad_total'])
                
                # PESTAÑA 2: Historial detallado por fechas de utilización (Tu requerimiento principal)
                with tab_fechas:
                    st.markdown(f"**Historial cronológico de cuándo y en qué recetas se utilizó {mp}:**")
                    
                    # Seleccionamos las columnas clave ordenadas por fecha de forma descendente
                    historial_fechas = detalle_mp[['fecha_movimiento', 'receta', 'cantidad']].copy()
                    
                    # Renombramos columnas para el usuario final
                    historial_fechas.columns = ['Fecha y Hora', 'Receta Destino', f'Cantidad Usada ({unidad_mp})']
                    
                    # Mostramos la tabla detallada
                    st.dataframe(
                        historial_fechas,
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Pequeña métrica informativa sobre la frecuencia de uso
                    st.info(f"💡 Este insumo se ha solicitado o extraído **{len(historial_fechas)} veces** para la elaboración de recetas en el rango seleccionado.")
                    
    else:
        st.warning("⚠️ No se encontraron movimientos de egreso en el periodo seleccionado.")
else:
    st.info("👈 Seleccione el rango de fechas en el panel izquierdo y haga clic en **'Calcular Auditoría'** para generar el reporte detallado.")

