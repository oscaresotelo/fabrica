import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
from st_aggrid import AgGrid, GridOptionsBuilder, ColumnsAutoSizeMode, JsCode

st.set_page_config(
    page_title="Gestión de Pagos Materias Primas",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Funciones ---
def conectar_db():
    return sqlite3.connect('minerva.db')

def cargar_boletas(filtro_proveedor=None, filtro_materia=None, filtro_fecha_inicio=None, filtro_fecha_fin=None):
    conn = conectar_db()
    query = """
    SELECT
        cmp.id,
        cmp.numero_comprobante,
        cmp.costo_total,
        mp.nombre AS materia_prima,
        prov.nombre AS proveedor,
        cmp.fecha
    FROM compras_materia_prima cmp
    JOIN materias_primas mp ON cmp.materia_prima_id = mp.id
    JOIN proveedores prov ON cmp.proveedor_id = prov.id
    WHERE 1=1
    """
    params = []
    if filtro_proveedor:
        query += " AND prov.nombre = ?"
        params.append(filtro_proveedor)
    if filtro_materia:
        query += " AND mp.nombre = ?"
        params.append(filtro_materia)
    if filtro_fecha_inicio and filtro_fecha_fin:
        query += " AND cmp.fecha BETWEEN ? AND ?"
        params.append(str(filtro_fecha_inicio))
        params.append(str(filtro_fecha_fin))
    elif filtro_fecha_inicio:
        query += " AND cmp.fecha >= ?"
        params.append(str(filtro_fecha_inicio))
    elif filtro_fecha_fin:
        query += " AND cmp.fecha <= ?"
        params.append(str(filtro_fecha_fin))
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def obtener_pagos_realizados(compra_id):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(importe) FROM pagos_materia_prima WHERE compra_id = ?", (compra_id,))
    total_pagado = cursor.fetchone()[0] or 0
    conn.close()
    return total_pagado

def insertar_pago(compra_id, importe, fecha):
    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO pagos_materia_prima (compra_id, importe, fecha) VALUES (?, ?, ?)", (compra_id, importe, fecha))
        conn.commit()
        st.success("Pago registrado con éxito!")
    except Exception as e:
        st.error(f"Error al registrar el pago: {e}")
    finally:
        conn.close()

# --- UI ---
st.title("Gestión de Pagos de Materias Primas")

# Sidebar - Filtros
with st.sidebar:
    st.header("Filtros")
    conn = conectar_db()
    proveedores = pd.read_sql_query("SELECT DISTINCT nombre FROM proveedores", conn)['nombre'].tolist()
    materias = pd.read_sql_query("SELECT DISTINCT nombre FROM materias_primas", conn)['nombre'].tolist()
    conn.close()

    filtro_proveedor = st.selectbox("Proveedor", [None] + proveedores, format_func=lambda x: "Todos" if x is None else x)
    filtro_materia = st.selectbox("Materia Prima", [None] + materias, format_func=lambda x: "Todas" if x is None else x)
    fecha_inicio = st.date_input("Fecha Inicio", value=None)
    fecha_fin = st.date_input("Fecha Fin", value=None)
    filtro_estado = st.selectbox("Estado de Pago", ["Todos", "Con deuda", "Pagado"])

# Cargar boletas y calcular saldo
boletas_df = cargar_boletas(filtro_proveedor, filtro_materia, fecha_inicio if fecha_inicio else None, fecha_fin if fecha_fin else None)
if not boletas_df.empty:
    boletas_df["pagado"] = boletas_df["id"].apply(obtener_pagos_realizados)
    boletas_df["saldo_pendiente"] = boletas_df["costo_total"] - boletas_df["pagado"]

    # Filtrar por estado de pago
    if filtro_estado == "Con deuda":
        boletas_df = boletas_df[boletas_df["saldo_pendiente"] > 0]
    elif filtro_estado == "Pagado":
        boletas_df = boletas_df[boletas_df["saldo_pendiente"] <= 0]

    # Ordenar por saldo pendiente
    boletas_df = boletas_df.sort_values(by="saldo_pendiente", ascending=False)

    # Mostrar resumen por proveedor
    st.subheader("📊 Resumen de Deuda por Proveedor")
    resumen = boletas_df.groupby("proveedor")["saldo_pendiente"].sum().reset_index()
    resumen_total = resumen["saldo_pendiente"].sum()
    st.dataframe(resumen)
    st.write(f"**💰 Deuda Total Pendiente:** ${resumen_total:,.2f}")

    # Configurar tabla principal
    gb = GridOptionsBuilder.from_dataframe(boletas_df)
    gb.configure_selection('single', use_checkbox=True)
    gb.configure_column("costo_total", type=["numericColumn"], valueFormatter=JsCode("function(p){return '$'+p.value.toFixed(2);}"))
    gb.configure_column("saldo_pendiente", type=["numericColumn"], valueFormatter=JsCode("""
        function(p){
            if (p.value > 0) { return '🔴 $'+p.value.toFixed(2); }
            else { return '✅ $'+p.value.toFixed(2); }
        }
    """))
    gridOptions = gb.build()

    # Mostrar tabla
    st.subheader("📋 Boletas")
    response = AgGrid(
        boletas_df,
        gridOptions=gridOptions,
        columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
        height=400,
        allow_unsafe_jscode=True,
        key="grid_boletas"
    )

    # --- Manejo seguro de selección ---
    selected_rows = response.get("selected_rows", [])
    if isinstance(selected_rows, pd.DataFrame):
        has_selection = not selected_rows.empty
    elif isinstance(selected_rows, list):
        has_selection = len(selected_rows) > 0
    else:
        has_selection = False

    if has_selection:
        if isinstance(selected_rows, pd.DataFrame):
            boleta_sel = selected_rows.iloc[0].to_dict()
        else:
            boleta_sel = selected_rows[0]

        st.write("### Información de la Boleta Seleccionada")
        st.write(f"Número Comprobante: {boleta_sel['numero_comprobante']}")
        st.write(f"Materia Prima: {boleta_sel['materia_prima']}")
        st.write(f"Proveedor: {boleta_sel['proveedor']}")
        st.write(f"Costo Total: ${boleta_sel['costo_total']:,.2f}")
        st.write(f"Pagado: ${boleta_sel['pagado']:,.2f}")
        st.write(f"Saldo Pendiente: ${boleta_sel['saldo_pendiente']:,.2f}")

        with st.form("registro_pago"):
            importe_pago = st.number_input("Importe del Pago", min_value=0.01)
            fecha_pago = st.date_input("Fecha del Pago")
            submitted = st.form_submit_button("Registrar Pago")
            if submitted:
                insertar_pago(boleta_sel["id"], importe_pago, str(fecha_pago))
                st.experimental_rerun()
else:
    st.warning("No se encontraron boletas con los filtros seleccionados.")
