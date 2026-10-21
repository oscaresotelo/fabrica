import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

# ── CONFIGURACIÓN VISUAL ──────────────────────────────────────────────────────
DB_PATH = "minerva.db"
VERDE_MINERVA = colors.HexColor("#1B5E20")
GRIS_HEADER   = colors.HexColor("#37474F")
GRIS_FILA     = colors.HexColor("#F5F5F5")
ROJO_ANULADA  = colors.HexColor("#FFEBEE")

# ── BASE DE DATOS ─────────────────────────────────────────────────────────────
def get_conn():
    return sqlite3.connect(DB_PATH)

def cargar_lista_revendedores():
    """Trae la lista de revendedores reales para el filtro de la barra lateral."""
    query = "SELECT id, nombre FROM revendedores ORDER BY nombre ASC"
    try:
        with get_conn() as conn:
            return pd.read_sql(query, conn)
    except Exception:
        return pd.DataFrame(columns=["id", "nombre"])

def cargar_ventas(fecha_desde: date, fecha_hasta: date, estados_seleccionados: list, revendedor_id=None):
    """Carga las ventas aplicando filtros utilizando la tabla 'revendedores' y el campo 'revendedor_id'."""
    estados = [e.lower().strip() for e in estados_seleccionados]
    
    query = f"""
        SELECT
            v.numero_comprobante    AS comprobante,
            r.nombre                AS cliente,
            v.fecha_venta           AS fecha,
            v.total_venta           AS total,
            v.estado_venta          AS estado
        FROM ventas v
        LEFT JOIN revendedores r ON r.id = v.revendedor_id
        WHERE v.fecha_venta BETWEEN ? AND ?
        AND LOWER(v.estado_venta) IN ({','.join(['?'] * len(estados))})
    """
    params = [fecha_desde.strftime("%Y-%m-%d"), fecha_hasta.strftime("%Y-%m-%d")] + estados

    if revendedor_id is not None:
        query += " AND v.revendedor_id = ? "
        params.append(int(revendedor_id))
        
    query += " ORDER BY v.fecha_venta ASC, CAST(v.numero_comprobante AS INTEGER) ASC"

    with get_conn() as conn:
        df = pd.read_sql(query, conn, params=params)
        df['total'] = pd.to_numeric(df['total'], errors='coerce').fillna(0.0)
        df['estado'] = df['estado'].astype(str).str.strip().str.lower()
        return df

def cargar_productos_mas_vendidos(fecha_desde: date, fecha_hasta: date, revendedor_id=None):
    """
    Analiza el ranking de productos asociando detalle_venta con stock_productos_envasados,
    y de ahí cruzando con recetas y envases utilizando los campos reales (rec.nombre y env.descripcion).
    """
    query = """
        SELECT 
            (rec.nombre || ' - ' || env.descripcion) AS Producto,
            SUM(d.cantidad) AS [Cantidad Vendida],
            SUM(d.cantidad * d.precio_unitario) AS [Total Recaudado]
        FROM detalle_venta d
        INNER JOIN stock_productos_envasados s ON s.id = d.stock_id
        INNER JOIN recetas rec ON rec.id = s.receta_id
        INNER JOIN envases env ON env.id = s.envase_id
        INNER JOIN ventas v ON v.id = d.venta_id
        WHERE v.fecha_venta BETWEEN ? AND ?
        AND LOWER(v.estado_venta) = 'activa'
    """
    params = [fecha_desde.strftime("%Y-%m-%d"), fecha_hasta.strftime("%Y-%m-%d")]
    
    if revendedor_id is not None:
        query += " AND v.revendedor_id = ? "
        params.append(int(revendedor_id))
        
    query += " GROUP BY s.receta_id, s.envase_id, rec.nombre, env.descripcion ORDER BY [Cantidad Vendida] DESC"
    
    with get_conn() as conn:
        df = pd.read_sql(query, conn, params=params)
        df['Cantidad Vendida'] = pd.to_numeric(df['Cantidad Vendida']).fillna(0)
        df['Total Recaudado'] = pd.to_numeric(df['Total Recaudado']).fillna(0.0)
        return df

# ── GENERACIÓN DE PDF: FACTURACIÓN ────────────────────────────────────────────
def generar_pdf_facturacion(df: pd.DataFrame, fecha_desde: date, fecha_hasta: date, nombre_filtro: str) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.2*cm, rightMargin=1.2*cm,
        topMargin=1.5*cm,  bottomMargin=1.5*cm,
    )

    styles = getSampleStyleSheet()
    estilo_titulo   = ParagraphStyle("titulo",   fontSize=16, textColor=VERDE_MINERVA, fontName="Helvetica-Bold", alignment=TA_CENTER)
    estilo_seccion  = ParagraphStyle("seccion",  fontSize=11, textColor=GRIS_HEADER,   fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=5)
    estilo_total    = ParagraphStyle("total",    fontSize=13, textColor=VERDE_MINERVA, fontName="Helvetica-Bold", alignment=TA_RIGHT)
    estilo_detalle  = ParagraphStyle("detalle",  fontSize=7.5, textColor=colors.grey,  fontName="Helvetica",      alignment=TA_LEFT)

    story = []
    story.append(Paragraph("MINERVA - INFORME DE FACTURACIÓN", estilo_titulo))
    story.append(Paragraph(
        f"<b>Periodo:</b> {fecha_desde.strftime('%d/%m/%Y')} al {fecha_hasta.strftime('%d/%m/%Y')} | <b>Filtro:</b> {nombre_filtro}",
        styles["Normal"]
    ))
    story.append(Spacer(1, 0.5*cm))

    df_activas = df[df["estado"] == "activa"].copy()
    suma_total_activa = float(df_activas["total"].sum())
    lista_auditoria = [
        f"C.{str(row['comprobante'])}: ${float(row['total']):,.2f}"
        for _, row in df_activas.iterrows()
    ]

    header = [["Comp.", "Revendedor", "Fecha", "Estado", "Subtotal"]]
    data = []

    for _, r in df.iterrows():
        monto = float(r["total"])
        estado_str = r["estado"]
        n_comp = str(r["comprobante"]) if r["comprobante"] else "S/N"

        nombre_rev = r["cliente"] if r["cliente"] else "Consumidor Final"
        if len(nombre_rev) > 30:
            nombre_rev = nombre_rev[:28] + ".."

        data.append([
            n_comp,
            nombre_rev,
            pd.to_datetime(r["fecha"]).strftime("%d/%m/%y") if pd.notna(r["fecha"]) else "-",
            estado_str.capitalize(),
            f"$ {monto:,.2f}"
        ])

    tabla = Table(header + data, colWidths=[1.5*cm, 9*cm, 2*cm, 2.5*cm, 3.5*cm], repeatRows=1)

    style_table = [
        ('BACKGROUND', (0, 0), (-1, 0), GRIS_HEADER),
        ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
        ('ALIGN',      (0, 0), (0, -1), 'CENTER'),
        ('ALIGN',      (2, 0), (3, -1), 'CENTER'),
        ('ALIGN',      (4, 0), (4, -1), 'RIGHT'),
        ('GRID',       (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE',   (0, 0), (-1, -1), 9),
    ]

    for i, (_, r) in enumerate(df.iterrows(), start=1):
        if r["estado"] == "anulada":
            style_table.append(('BACKGROUND', (0, i), (-1, i), ROJO_ANULADA))
        elif i % 2 == 0:
            style_table.append(('BACKGROUND', (0, i), (-1, i), GRIS_FILA))

    tabla.setStyle(TableStyle(style_table))
    story.append(tabla)
    story.append(Spacer(1, 0.8*cm))

    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Paragraph("DETALLE DE CONCILIACIÓN (MONTOS SUMADOS AL TOTAL):", estilo_seccion))

    if lista_auditoria:
        chunks = [lista_auditoria[i:i + 4] for i in range(0, len(lista_auditoria), 4)]
        for chunk in chunks:
            story.append(Paragraph("  |  ".join(chunk), estilo_detalle))
    else:
        story.append(Paragraph("Sin comprobantes activos en el período.", estilo_detalle))

    story.append(Spacer(1, 0.6*cm))
    story.append(Paragraph(f"TOTAL NETO (Activas): $ {suma_total_activa:,.2f}", estilo_total))

    doc.build(story)
    return buf.getvalue()

# ── GENERACIÓN DE PDF: PRODUCTOS MÁS VENDIDOS ─────────────────────────────────
def generar_pdf_productos(df: pd.DataFrame, fecha_desde: date, fecha_hasta: date, nombre_filtro: str) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.5*cm,  bottomMargin=1.5*cm,
    )

    styles = getSampleStyleSheet()
    estilo_titulo  = ParagraphStyle("titulo_prod", fontSize=16, textColor=VERDE_MINERVA, fontName="Helvetica-Bold", alignment=TA_CENTER)
    
    story = []
    story.append(Paragraph("MINERVA - RANKING DE PRODUCTOS MÁS VENDIDOS", estilo_titulo))
    story.append(Paragraph(
        f"<b>Periodo:</b> {fecha_desde.strftime('%d/%m/%Y')} al {fecha_hasta.strftime('%d/%m/%Y')} | <b>Filtro:</b> {nombre_filtro}",
        styles["Normal"]
    ))
    story.append(Spacer(1, 0.6*cm))

    header = [["Pos.", "Producto / Artículo", "Cant. Vendida", "Total Recaudado"]]
    data = []
    
    for idx, r in enumerate(df.iterrows(), start=1):
        row = r[1]
        data.append([
            f"#{idx}",
            str(row["Producto"]),
            f"{int(row['Cantidad Vendida']):,}",
            f"$ {float(row['Total Recaudado']):,.2f}"
        ])

    tabla = Table(header + data, colWidths=[1.5*cm, 9.5*cm, 3.5*cm, 3.5*cm], repeatRows=1)
    
    style_table = [
        ('BACKGROUND', (0, 0), (-1, 0), GRIS_HEADER),
        ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
        ('ALIGN',      (0, 0), (0, -1), 'CENTER'),
        ('ALIGN',      (2, 0), (3, -1), 'RIGHT'),
        ('GRID',       (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE',   (0, 0), (-1, -1), 9.5),
    ]
    
    for i in range(1, len(data) + 1):
        if i % 2 == 0:
            style_table.append(('BACKGROUND', (0, i), (-1, i), GRIS_FILA))
            
    tabla.setStyle(TableStyle(style_table))
    story.append(tabla)
    
    doc.build(story)
    return buf.getvalue()

# ── INTERFAZ STREAMLIT ────────────────────────────────────────────────────────
st.set_page_config(page_title="Minerva - Reportes Avanzados", layout="wide")
st.title("📊 Panel de Facturación y Rendimiento de Ventas")

df_revendedores = cargar_lista_revendedores()
opciones_revendedores = ["Todos los revendedores"] + df_revendedores["nombre"].tolist()

with st.sidebar:
    st.header("Configuración de Filtros")
    f_inicio = st.date_input("Desde", date(2026, 4, 1))
    f_fin    = st.date_input("Hasta", date(2026, 4, 30))
    
    revendedor_sel = st.selectbox("Seleccionar Revendedor:", opciones_revendedores)
    estados  = st.multiselect("Filtrar por Estado (Solo Facturación):", ["Activa", "Anulada"], default=["Activa", "Anulada"])
    consultar = st.button("🔍 Consultar Datos", type="primary", use_container_width=True)

id_filtro = None
if revendedor_sel != "Todos los revendedores" and not df_revendedores.empty:
    fila_r = df_revendedores[df_revendedores["nombre"] == revendedor_sel]
    if not fila_r.empty:
        id_filtro = fila_r.iloc[0]["id"]

if consultar:
    if not estados:
        st.error("Por favor, selecciona al menos un estado para la pestaña de facturación.")
    else:
        st.session_state["rep_ventas"] = cargar_ventas(f_inicio, f_fin, estados, revendedor_id=id_filtro)
        st.session_state["rep_productos"] = cargar_productos_mas_vendidos(f_inicio, f_fin, revendedor_id=id_filtro)
        st.session_state["fechas_info"] = (f_inicio, f_fin)
        st.session_state["txt_filtro"] = revendedor_sel

if "rep_ventas" in st.session_state and "fechas_info" in st.session_state:
    tab_facturas, tab_productos = st.tabs(["🧾 Detalle de Facturación", "📦 Productos Más Vendidos"])
    
    fi, ff = st.session_state["fechas_info"]
    txt_f = st.session_state["txt_filtro"]
    
    with tab_facturas:
        df_v = st.session_state["rep_ventas"]
        if df_v.empty:
            st.warning("No se encontraron comprobantes para el filtro especificado.")
        else:
            df_solo_act = df_v[df_v['estado'] == 'activa']
            col1, col2 = st.columns(2)
            with col1:
                st.metric(f"Total Facturado ({txt_f})", f"$ {df_solo_act['total'].sum():,.2f}")
            with col2:
                st.metric("Comprobantes Evaluados", len(df_v))

            st.divider()
            st.dataframe(df_v, use_container_width=True, hide_index=True)
            st.divider()
            
            pdf_v_output = generar_pdf_facturacion(df_v, fi, ff, txt_f)
            st.download_button(
                label="📥 Descargar Reporte PDF de Facturación",
                data=pdf_v_output,
                file_name=f"facturacion_{fi.strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                type="primary",
                key="btn_pdf_facturas"
            )

    with tab_productos:
        df_p = st.session_state["rep_productos"]
        if df_p.empty:
            st.warning("No hay registros de productos vendidos en comprobantes activos para este período.")
        else:
            st.subheader(f"Volumen de Ventas por Artículo — {txt_f}")
            
            st.bar_chart(
                data=df_p,
                x="Producto",
                y="Cantidad Vendida",
                color="#1B5E20",
                use_container_width=True
            )
            
            st.divider()
            st.dataframe(
                df_p.style.format({"Total Recaudado": "$ {:,.2f}", "Cantidad Vendida": "{:,.0f}"}),
                use_container_width=True,
                hide_index=True
            )
            
            st.divider()
            pdf_p_output = generar_pdf_productos(df_p, fi, ff, txt_f)
            st.download_button(
                label="📥 Descargar Reporte de Productos (PDF)",
                data=pdf_p_output,
                file_name=f"ranking_productos_{fi.strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                type="primary",
                key="btn_pdf_articulos"
            )
else:
    st.info("👋 ¡Bienvenido! Por favor selecciona los filtros en la barra lateral izquierda y haz clic en '🔍 Consultar Datos' para desplegar los paneles.")