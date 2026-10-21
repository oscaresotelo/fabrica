import sqlite3
import pandas as pd
import streamlit as st

def calcular_overhead_por_litro(mes, anio):
    """
    Implementa la lógica de Prorrateo:
    1. Suma sueldos.
    2. Suma gastos del mes.
    3. Divide por capacidad de planta (32.000L).
    """
    with sqlite3.connect('minerva.db') as conn:
        # 1. Extracción de Sueldos (SQL)
        df_empleados = pd.read_sql("SELECT SUM(sueldo_base) as total FROM empleados", conn)
        total_sueldos = df_empleados['total'].iloc[0] or 0

        # 2. Consolidación de Gastos Fijos del mes seleccionado
        query_gastos = """
            SELECT SUM(importe_total) as total 
            FROM gastos 
            WHERE strftime('%m', fecha_factura) = ? 
            AND strftime('%Y', fecha_factura) = ?
        """
        df_gastos = pd.read_sql(query_gastos, conn, params=(f"{mes:02d}", str(anio)))
        total_gastos_fijos = df_gastos['total'].iloc[0] or 0

        # 3. El Prorrateo por Litro (Capacidad de Planta: 32.000 L)
        capacidad_planta = 32000
        gasto_operativo_mensual = total_sueldos + total_gastos_fijos
        overhead_por_litro = gasto_operativo_mensual / capacidad_planta if capacidad_planta > 0 else 0

        return {
            "gasto_mensual_total": gasto_operativo_mensual,
            "overhead_por_litro": overhead_por_litro,
            "total_sueldos": total_sueldos,
            "total_gastos": total_gastos_fijos
        }

def render_sidebar_gastos_fijos():
    """
    Dibuja los controles en el sidebar y retorna el costo aplicado por envase.
    """
    st.sidebar.divider()
    st.sidebar.subheader("🏢 Costos Indirectos (Overhead)")
    
    # Selección de mes y año para la consulta SQL
    mes_sel = st.sidebar.selectbox("Mes para Gastos/Sueldos:", range(1, 13), index=8) # Default Septiembre
    anio_sel = st.sidebar.number_input("Año:", min_value=2024, max_value=2030, value=2025)
    
    res = calcular_overhead_por_litro(mes_sel, anio_sel)
    
    with st.sidebar.expander("🔍 Ver Estructura Overhead"):
        st.write(f"Sueldos: $ {res['total_sueldos']:,.0f}")
        st.write(f"Gastos: $ {res['total_gastos']:,.0f}")
        st.write(f"Costo por Litro: $ {res['overhead_por_litro']:,.2f}")
    
    return res['overhead_por_litro']