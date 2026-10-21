import streamlit as st
import sqlite3
import pandas as pd
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from io import BytesIO
from datetime import datetime

st.set_page_config(page_title="Minerva - Rentabilidad", layout="wide")

def get_connection():
    return sqlite3.connect("minerva.db")

# --- FUNCIÓN DE OVERHEAD: USA 'beneficiario_nombre' ---
def calcular_overhead_dinamico(mes, anio, capacidad_litros=35200):
    """Calcula gastos operativos prorrateados usando únicamente la tabla gastos"""
    conn = get_connection()
    mes_str = f"{mes:02d}"
    query_detalle = """
        SELECT 
            fecha_factura as Fecha, 
            beneficiario_nombre as Detalle, 
            importe_total as Importe
        FROM gastos 
        WHERE strftime('%m', fecha_factura) = ? 
        AND strftime('%Y', fecha_factura) = ?
    """
    df_gastos = pd.read_sql_query(query_detalle, conn, params=(mes_str, str(anio)))
    total_gastos = df_gastos["Importe"].sum()
    conn.close()
    
    overhead_por_litro = total_gastos / capacidad_litros
    return overhead_por_litro, total_gastos, df_gastos

def crear_tabla_fletes():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS "costos_flete_recetas" (
            "id" INTEGER PRIMARY KEY AUTOINCREMENT,
            "receta_id" INTEGER NOT NULL,
            "monto" REAL NOT NULL,
            "fecha_desde" TEXT NOT NULL,
            FOREIGN KEY("receta_id") REFERENCES "recetas"("id")
        )
    """)
    conn.commit()
    conn.close()

crear_tabla_fletes()

def get_data_costos(cliente_id):
    conn = get_connection()
    query = f"""
    WITH UltimosPrecios AS (
        SELECT cp1.materia_prima_id, cp1.precio_unitario AS precio_usd
        FROM compras_materia_prima cp1
        WHERE cp1.id = (
            SELECT MAX(cp2.id)
            FROM compras_materia_prima cp2
            WHERE cp2.materia_prima_id = cp1.materia_prima_id
        )
    ),
    UltimoFlete AS (
        SELECT receta_id, monto AS costo_flete_lote
        FROM costos_flete_recetas cf1
        WHERE cf1.id = (
            SELECT MAX(cf2.id)
            FROM costos_flete_recetas cf2
            WHERE cf2.receta_id = cf1.receta_id
        )
    ),
    CostosRecetas AS (
        SELECT 
            r.id AS receta_id,
            r.nombre,
            SUM(ri.cantidad * up.precio_usd) AS costo_receta_200l_usd
        FROM recetas r
        JOIN receta_ingredientes ri ON r.id = ri.receta_id
        JOIN UltimosPrecios up ON ri.materia_prima_id = up.materia_prima_id
        GROUP BY r.id
    )
    SELECT 
        p.nombre AS Producto,
        cr.costo_receta_200l_usd,
        cr.costo_receta_200l_usd / 200 AS mp_usd_litro,
        pp.precio_unitario AS venta_usd_lote,
        IFNULL(uf.costo_flete_lote, 0) AS flete_lote_ars
    FROM productos p
    JOIN CostosRecetas cr ON p.id_receta = cr.receta_id
    JOIN precios_productos_envasados pp ON p.id = pp.producto_id
    LEFT JOIN UltimoFlete uf ON cr.receta_id = uf.receta_id
    WHERE p.cliente_id = {cliente_id}
    AND (pp.fecha_hasta IS NULL OR pp.fecha_hasta = '')
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def generar_pdf(df, cliente_id, tc, g_operativos):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    estilo_producto = ParagraphStyle("producto", fontSize=8, leading=10)
    elementos = []
    elementos.append(Paragraph(f"Reporte Rentabilidad Cliente {cliente_id}", styles["Title"]))
    elementos.append(Paragraph(f"Dólar: ${tc} | Gastos Operativos/L: ${g_operativos:,.2f}", styles["Normal"]))
    elementos.append(Spacer(1, 15))

    # Cabecera con Flete y % incluido para que el reporte sea completo
    data = [["Producto", "MP Receta USD", "Venta/L USD", "Flete/L ARS", "Costo/L ARS", "Ganancia/L ARS", "%", "Ganancia Lote ARS"]]

    for _, row in df.iterrows():
        venta_litro_ars = (row["venta_usd_lote"] / 200) * tc
        mp_ars = row["mp_usd_litro"] * tc
        flete_litro = row["flete_lote_ars"] / 200
        costo_litro = mp_ars + g_operativos + flete_litro
        ganancia_litro = venta_litro_ars - costo_litro
        ganancia_lote = ganancia_litro * 200
        
        # Cálculo de porcentaje: (Ganancia / Costo) * 100
        porc_ganancia = (ganancia_litro / costo_litro * 100) if costo_litro > 0 else 0

        data.append([
            Paragraph(row["Producto"], estilo_producto),
            f"{row['costo_receta_200l_usd']:,.2f}",
            f"{(row['venta_usd_lote']/200):,.2f}",
            f"{flete_litro:,.2f}",
            f"{costo_litro:,.2f}",
            f"{ganancia_litro:,.2f}",
            f"{porc_ganancia:,.1f}%",
            f"{ganancia_lote:,.2f}"
        ])

    table = Table(data, colWidths=[5*cm, 2.5*cm, 2.5*cm, 2.3*cm, 2.8*cm, 2.8*cm, 1.8*cm, 3.2*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.grey), ("TEXTCOLOR",(0,0),(-1,0),colors.whitesmoke),
        ("ALIGN",(0,0),(-1,0),"CENTER"), ("ALIGN",(1,1),(-1,-1),"RIGHT"),
        ("GRID",(0,0),(-1,-1),0.4,colors.black), ("FONTSIZE",(0,0),(-1,-1),8)
    ]))
    elementos.append(table)
    doc.build(elementos)
    buffer.seek(0)
    return buffer

# --- INTERFAZ ---
st.title("Minerva - Análisis de Rentabilidad")

with st.sidebar:
    st.header("Variables Globales")
    tc = st.number_input("Dólar", value=1420.0)
    
    st.divider()
    st.subheader("Cálculo de Gastos Operativos")
    mes_sel = st.selectbox("Mes", range(1, 13), index=datetime.now().month - 1)
    anio_sel = st.number_input("Año", value=datetime.now().year)
    
    g_operativos_dinamico, g_total, df_detalle_gastos = calcular_overhead_dinamico(mes_sel, anio_sel)
    
    st.metric("G. Operativos / Litro", f"${g_operativos_dinamico:,.2f}")
    
    with st.expander("Ver detalles del cálculo"):
        st.write(f"**Total Gastos del Mes:** ${g_total:,.2f}")
        st.write(f"**Capacidad Base:** 35.200 L")
        st.divider()
        if not df_detalle_gastos.empty:
            st.dataframe(df_detalle_gastos, hide_index=True, use_container_width=True)
        else:
            st.info("No hay gastos registrados.")

cliente_id = st.number_input("Cliente ID", value=8)

if st.button("Calcular"):
    df = get_data_costos(cliente_id)

    if not df.empty:
        df["MP Litro ARS"] = df["mp_usd_litro"] * tc
        df["Venta Litro ARS"] = (df["venta_usd_lote"] / 200) * tc
        df["Flete Litro ARS"] = df["flete_lote_ars"] / 200
        
        df["Costo Total Litro"] = df["MP Litro ARS"] + g_operativos_dinamico + df["Flete Litro ARS"]
        df["Ganancia Litro"] = df["Venta Litro ARS"] - df["Costo Total Litro"]
        
        # --- PORCENTAJE BASADO EN COSTO TOTAL (Como en tu ejemplo) ---
        df["%"] = (df["Ganancia Litro"] / df["Costo Total Litro"] * 100).map("{:,.1f}%".format)
        
        df["Ganancia Lote"] = df["Ganancia Litro"] * 200

        st.subheader(f"Rentabilidad por Producto (G. Operativos: ${g_operativos_dinamico:,.2f})")
        # Aseguramos que Flete Litro ARS esté presente en la vista
        columnas_vista = ["Producto", "Flete Litro ARS", "MP Litro ARS", "Costo Total Litro", "Venta Litro ARS", "Ganancia Litro", "%", "Ganancia Lote"]
        st.dataframe(df[columnas_vista], use_container_width=True)

        pdf = generar_pdf(df, cliente_id, tc, g_operativos_dinamico)
        st.download_button("Descargar PDF", data=pdf, file_name=f"reporte_rentabilidad.pdf", mime="application/pdf")

# --- SECCIÓN GESTIÓN FLETES ---
st.divider()
st.header("Gestión de Fletes por Lote (200L)")

def seccion_fletes(c_id):
    conn = get_connection()
    query_recetas_cliente = """
        SELECT DISTINCT r.id, r.nombre 
        FROM recetas r
        JOIN productos p ON r.id = p.id_receta
        WHERE p.cliente_id = ?
        ORDER BY r.nombre
    """
    df_recetas = pd.read_sql_query(query_recetas_cliente, conn, params=(c_id,))
    
    if df_recetas.empty:
        st.warning("No se encontraron productos/recetas.")
        conn.close()
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        receta_sel = st.selectbox("Seleccionar Receta", df_recetas["nombre"].tolist())
        id_sel = df_recetas[df_recetas["nombre"] == receta_sel]["id"].values[0]
    with col2:
        res = conn.execute("SELECT monto FROM costos_flete_recetas WHERE receta_id = ? ORDER BY id DESC LIMIT 1", (int(id_sel),)).fetchone()
        actual = res[0] if res else 0.0
        nuevo_flete = st.number_input(f"Flete Lote (Actual: ${actual})", min_value=0.0, step=100.0, key="flete_input")
    with col3:
        st.write("##")
        if st.button("Guardar Flete"):
            fecha_act = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("INSERT INTO costos_flete_recetas (receta_id, monto, fecha_desde) VALUES (?, ?, ?)", (int(id_sel), float(nuevo_flete), fecha_act))
            conn.commit()
            st.success(f"Flete actualizado.")
            st.rerun()
    conn.close()

seccion_fletes(cliente_id)