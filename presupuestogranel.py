
import streamlit as st
import sqlite3
import pandas as pd
import os
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

st.set_page_config(
    page_title="Minerva - Análisis de Costos y Precios de Venta",
    page_icon="📊",
    layout="wide"
)

def obtener_costos_base_db(db_path="minerva.db"):
    """
    Obtiene los costos base en USD de cada receta consultando la última
    compra registrada para cada materia prima en la base de datos SQLite.
    """
    if not os.path.exists(db_path):
        st.error(f"No se encontró el archivo de base de datos '{db_path}' en el directorio actual.")
        return pd.DataFrame()
    
    conn = sqlite3.connect(db_path)
    query = """
    WITH ultimo_precio_materia_prima AS (
        SELECT 
            materia_prima_id,
            precio_unitario,
            fecha,
            ROW_NUMBER() OVER (
                PARTITION BY materia_prima_id 
                ORDER BY fecha DESC, id DESC
            ) AS rn
        FROM compras_materia_prima
    )
    SELECT 
        r.id AS receta_id,
        r.nombre AS nombre_receta,
        ROUND(SUM(ri.cantidad * up.precio_unitario), 4) AS costo_base_usd
    FROM recetas r
    JOIN receta_ingredientes ri ON r.id = ri.receta_id
    JOIN ultimo_precio_materia_prima up ON ri.materia_prima_id = up.materia_prima_id
    WHERE up.rn = 1
    GROUP BY r.id, r.nombre;
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def obtener_cantidades_totales_all_recetas(db_path="minerva.db"):
    """
    Calcula el total numérico y determina la unidad predominante de cada receta base.
    """
    if not os.path.exists(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    query = """
    SELECT receta_id, cantidad, unidad 
    FROM receta_ingredientes;
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    totales = {}
    for r_id, gp in df.groupby("receta_id"):
        suma_numerica = gp["cantidad"].sum()
        
        if not gp.empty:
            unidad_predominante = gp.groupby("unidad")["cantidad"].sum().idxmax()
        else:
            unidad_predominante = "L"
            
        texto_total = f"{suma_numerica:,.2f} {unidad_predominante}"
        totales[r_id] = {
            "texto": texto_total,
            "num": suma_numerica
        }
    return totales

def obtener_ingredientes_receta(receta_id, db_path="minerva.db"):
    """
    Obtiene el desglose detallado de ingredientes para auditoría interna.
    """
    if not os.path.exists(db_path):
        return pd.DataFrame()
    conn = sqlite3.connect(db_path)
    query = f"""
    WITH ultimo_precio AS (
        SELECT 
            materia_prima_id,
            precio_unitario,
            fecha,
            ROW_NUMBER() OVER (
                PARTITION BY materia_prima_id 
                ORDER BY fecha DESC, id DESC
            ) AS rn
        FROM compras_materia_prima
    )
    SELECT 
        mp.nombre AS ingrediente,
        ri.cantidad,
        ri.unidad,
        ROUND(up.precio_unitario, 4) AS ultimo_precio_usd,
        ROUND(ri.cantidad * up.precio_unitario, 4) AS costo_ingrediente_usd
    FROM receta_ingredientes ri
    JOIN materias_primas mp ON ri.materia_prima_id = mp.id
    JOIN ultimo_precio up ON ri.materia_prima_id = up.materia_prima_id
    WHERE ri.receta_id = {receta_id} AND up.rn = 1;
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def formato_pesos(valor):
    """
    Aplica formato de divisa ARS ($ 1.250,50) a un valor numérico float.
    """
    if pd.isna(valor):
        return "$ 0,00"
    return f"$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def parsear_pesos(texto):
    """
    Convierte una cadena en formato '$ 1.250,50' a float (1250.50) para realizar sumas.
    """
    if not isinstance(texto, str):
        return 0.0
    s = texto.replace("$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0

def generar_pdf_reporte_costos(df_datos, tipo_cambio, costo_asoc, lote_l, moneda_sel):
    """
    Genera un archivo PDF formal con la tabla de costos, precios de venta, márgenes de ganancia
    y una fila final de TOTALES generales acumulados.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=25, leftMargin=25, topMargin=30, bottomMargin=30
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    # Estilos de tipografía y colores
    style_titulo_empresa = ParagraphStyle('PdfTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=20, textColor=colors.HexColor("#f39c12"))
    style_sub_empresa = ParagraphStyle('PdfSub', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor("#bdc3c7"))
    style_tipo_doc = ParagraphStyle('PdfDoc', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=13, textColor=colors.white, alignment=2)
    style_fecha_doc = ParagraphStyle('PdfFecha', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, textColor=colors.HexColor("#bdc3c7"), alignment=2)
    
    style_meta_label = ParagraphStyle('PdfMetaLbl', fontName='Helvetica-Bold', fontSize=8, textColor=colors.HexColor("#34495e"))
    style_meta_val = ParagraphStyle('PdfMetaVal', fontName='Helvetica', fontSize=8.5, textColor=colors.HexColor("#555555"))
    
    style_h2 = ParagraphStyle('PdfH2', fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor("#1a252f"), spaceBefore=10, spaceAfter=4)
    style_body = ParagraphStyle('PdfBody', fontName='Helvetica', fontSize=8.5, textColor=colors.HexColor("#555555"), spaceAfter=6)
    
    style_th = ParagraphStyle('PdfTH', fontName='Helvetica-Bold', fontSize=6.5, textColor=colors.white, alignment=1)
    style_td = ParagraphStyle('PdfTD', fontName='Helvetica', fontSize=7, textColor=colors.HexColor("#2c3e50"))
    style_td_num = ParagraphStyle('PdfTDNum', fontName='Helvetica', fontSize=7, textColor=colors.HexColor("#2c3e50"), alignment=2)
    
    # Estilos para la fila de Totales
    style_tot_label = ParagraphStyle('PdfTotLbl', fontName='Helvetica-Bold', fontSize=7, textColor=colors.HexColor("#1a252f"))
    style_tot_num = ParagraphStyle('PdfTotNum', fontName='Helvetica-Bold', fontSize=7, textColor=colors.HexColor("#1a252f"), alignment=2)

    # Encabezado corporativo
    header_data = [
        [Paragraph("FÁBRICA MINERVA", style_titulo_empresa), Paragraph("ANÁLISIS DE COSTOS Y VENTAS", style_tipo_doc)],
        [Paragraph("Cosmética Capilar de Alta Calidad", style_sub_empresa), Paragraph("", style_fecha_doc)]
    ]
    header_table = Table(header_data, colWidths=[300, 262])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#1a252f")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,-1), (-1,-1), 10),
        ('LEFTPADDING', (0,0), (0,-1), 12),
        ('RIGHTPADDING', (-1,0), (-1,-1), 12),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10))

    # Parámetros utilizados
    meta_data = [
        [Paragraph("COTIZACIÓN DÓLAR:", style_meta_label), Paragraph(f"$ {tipo_cambio:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), style_meta_val),
         Paragraph("TAMAÑO DE LOTE:", style_meta_label), Paragraph(f"{lote_l:,.0f} Litros", style_meta_val)],
        [Paragraph("COSTOS ASOCIADOS ADIC.:", style_meta_label), Paragraph(f"$ {costo_asoc:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), style_meta_val),
         Paragraph("MONEDA BASE:", style_meta_label), Paragraph(moneda_sel, style_meta_val)]
    ]
    meta_table = Table(meta_data, colWidths=[140, 141, 140, 141])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LINEBELOW', (0,-1), (-1,-1), 0.5, colors.HexColor("#ecf0f1")),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Sección de Detalle
    story.append(Paragraph("ESTRUCTURA FINANCIERA Y MÁRGENES DE GANANCIA POR PRODUCTO", style_h2))
    story.append(Paragraph("Resumen de costos, precios sugeridos de venta y margen bruto por lote de fabricación:", style_body))
    
    # Encabezados de la tabla del PDF
    table_content = [
        [
            Paragraph("PRODUCTO", style_th), 
            Paragraph("F. ESCALA", style_th), 
            Paragraph("M.P. (ARS)", style_th), 
            Paragraph("TOTAL COSTO LOTE", style_th), 
            Paragraph("COSTO/L", style_th),
            Paragraph("PRECIO VENTA/L", style_th),
            Paragraph("VENTA LOTE", style_th),
            Paragraph("GANANCIA LOTE", style_th),
            Paragraph("MARGEN", style_th)
        ]
    ]
    
    # Ordenar alfabéticamente por producto
    df_datos_ordenado = df_datos.sort_values(by="Nombre de la Receta", ascending=True)
    
    # Variables acumuladoras para los totales
    sum_mp_ars = 0.0
    sum_costo_lote = 0.0
    sum_venta_lote = 0.0
    sum_ganancia_lote = 0.0
    
    for _, fila in df_datos_ordenado.iterrows():
        nombre = str(fila.get("Nombre de la Receta", ""))
        f_escala = str(fila.get("Factor de Escala", ""))
        mp_ars_str = str(fila.get("Materia Prima (ARS)", ""))
        total_costo_str = str(fila.get("Costo Total Tambor (ARS)", ""))
        costo_l = str(fila.get("Costo Final por Litro (ARS)", ""))
        precio_v_l = str(fila.get("Precio Venta / Litro (ARS)", ""))
        venta_lote_str = str(fila.get("Venta Total Lote (ARS)", ""))
        ganancia_str = str(fila.get("Ganancia Lote (ARS)", ""))
        margen = str(fila.get("Margen Ganancia (%)", ""))
        
        # Sumar valores absolutos acumulados
        sum_mp_ars += parsear_pesos(mp_ars_str)
        sum_costo_lote += parsear_pesos(total_costo_str)
        sum_venta_lote += parsear_pesos(venta_lote_str)
        sum_ganancia_lote += parsear_pesos(ganancia_str)
        
        table_content.append([
            Paragraph(nombre, style_td),
            Paragraph(f_escala, style_td_num),
            Paragraph(mp_ars_str, style_td_num),
            Paragraph(total_costo_str, style_td_num),
            Paragraph(costo_l, style_td_num),
            Paragraph(precio_v_l, style_td_num),
            Paragraph(venta_lote_str, style_td_num),
            Paragraph(ganancia_str, style_td_num),
            Paragraph(margen, style_td_num)
        ])
    
    # Cálculo del margen promedio global ponderado sobre la venta total acumulada
    margen_global_pct = (sum_ganancia_lote / sum_venta_lote * 100) if sum_venta_lote > 0 else 0.0
    margen_global_str = f"{margen_global_pct:,.1f}%"
    
    # Fila de TOTALES
    table_content.append([
        Paragraph("TOTALES", style_tot_label),
        Paragraph("-", style_tot_num),
        Paragraph(formato_pesos(sum_mp_ars), style_tot_num),
        Paragraph(formato_pesos(sum_costo_lote), style_tot_num),
        Paragraph("-", style_tot_num),
        Paragraph("-", style_tot_num),
        Paragraph(formato_pesos(sum_venta_lote), style_tot_num),
        Paragraph(formato_pesos(sum_ganancia_lote), style_tot_num),
        Paragraph(margen_global_str, style_tot_num)
    ])
    
    prod_table = Table(table_content, colWidths=[92, 42, 60, 68, 55, 65, 68, 65, 47], repeatRows=1)
    
    estilo_tabla = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#34495e")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 3),
    ]
    
    # Filas de datos (sin incluir la fila de Totales final)
    for i in range(1, len(table_content) - 1):
        bg_color = colors.HexColor("#f8fafc") if i % 2 != 0 else colors.white
        estilo_tabla.append(('BACKGROUND', (0, i), (-1, i), bg_color))
        estilo_tabla.append(('LINEBELOW', (0, i), (-1, i), 0.5, colors.HexColor("#e2e8f0")))
        
    # Estilo especial para la última fila (TOTALES)
    tot_row_idx = len(table_content) - 1
    estilo_tabla.extend([
        ('BACKGROUND', (0, tot_row_idx), (-1, tot_row_idx), colors.HexColor("#eaeded")),
        ('LINEABOVE', (0, tot_row_idx), (-1, tot_row_idx), 1.5, colors.HexColor("#1a252f")),
        ('LINEBELOW', (0, tot_row_idx), (-1, tot_row_idx), 1.5, colors.HexColor("#1a252f")),
        ('TOPPADDING', (0, tot_row_idx), (-1, tot_row_idx), 5),
        ('BOTTOMPADDING', (0, tot_row_idx), (-1, tot_row_idx), 5),
    ])
        
    prod_table.setStyle(TableStyle(estilo_tabla))
    story.append(prod_table)
    story.append(Spacer(1, 15))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

st.title("📊 Minerva - Análisis de Costos y Precios de Venta")
st.write("Calculá de manera exacta el costo real en Pesos (ARS) de tus productos, asigná precios de venta individuales y evaluá tus márgenes de ganancia.")

st.subheader("⚙️ Configuración de Costos Fijos y Divisa")
col_conf1, col_conf2, col_conf3 = st.columns(3)

with col_conf1:
    tipo_cambio = st.number_input(
        "Cotización del Dólar ($ ARS)",
        min_value=1.0,
        value=1000.0,
        step=10.0,
        help="Tipo de cambio utilizado para convertir los costos de materias primas (USD) a pesos."
    )

with col_conf2:
    costo_asociado_fijo = st.number_input(
        "Costos Asociados Adicionales ($ ARS por Lote)",
        min_value=0.0,
        value=76382.56,
        step=1000.0,
        help="Suma fija en pesos (alquileres, sueldos, fletes, etc.) que se añadirá de forma directa al costo total de cada lote/tambor."
    )

with col_conf3:
    batch_size_l = st.number_input(
        "Tamaño de Lote estándar (Litros)",
        min_value=1.0,
        value=200.0,
        step=10.0,
        help="Volumen total del lote o tambor para el cual se calculan los costos fijos y el desglose de materias primas."
    )

st.markdown("---")

df_costo_base = obtener_costos_base_db()
dict_totales_cantidades = obtener_cantidades_totales_all_recetas()

if not df_costo_base.empty:
    df_analisis = df_costo_base.copy()
    
    # Integración de cantidades base y cálculo de factor de escala
    df_analisis["Cantidad Fórmula"] = df_analisis["receta_id"].map(lambda x: dict_totales_cantidades.get(x, {}).get("texto", "N/A"))
    df_analisis["Suma Numérica Base"] = df_analisis["receta_id"].map(lambda x: dict_totales_cantidades.get(x, {}).get("num", 0.0))
    
    df_analisis["Factor Escala Num"] = df_analisis.apply(
        lambda r: batch_size_l / r['Suma Numérica Base'] if r['Suma Numérica Base'] > 0 else 1.0, 
        axis=1
    )
    df_analisis["Factor Escala"] = df_analisis["Factor Escala Num"].apply(lambda x: f"x {x:,.2f}")
    
    # Cálculos de Costos numéricos por lote y por litro
    df_analisis["Materia Prima (USD/Lote)"] = df_analisis["costo_base_usd"] * df_analisis["Factor Escala Num"]
    df_analisis["Materia Prima (ARS/Lote)"] = df_analisis["Materia Prima (USD/Lote)"] * tipo_cambio
    df_analisis["Costo Total Lote (ARS)"] = df_analisis["Materia Prima (ARS/Lote)"] + costo_asociado_fijo
    df_analisis["Costo por Litro (ARS)"] = df_analisis["Costo Total Lote (ARS)"] / batch_size_l

    st.subheader("📋 1. Selección de Productos a Cotizar")
    st.write("Elegí qué productos querés incluir en el análisis financiero:")
    
    recetas_disponibles = df_analisis["nombre_receta"].tolist()
    
    recetas_seleccionadas = st.multiselect(
        "Seleccioná o desmarcá productos según tu necesidad:",
        options=recetas_disponibles,
        default=recetas_disponibles,
        help="Los productos seleccionados aquí aparecerán en la tabla editable de precios y en el informe final."
    )

    if recetas_seleccionadas:
        # Filtrar DataFrame base según selección del usuario
        df_seleccionado = df_analisis[df_analisis["nombre_receta"].isin(recetas_seleccionadas)].copy()

        st.markdown("---")
        st.subheader("💲 2. Asignación de Precio de Venta por Litro")
        st.write("Ingresá manualmente el **Precio de Venta por Litro ($ ARS)** para cada uno de los productos seleccionados, o aplicá un recargo (*markup*) masivo:")

        # Inicializar diccionario de precios en Session State si no existe
        if "precios_venta_dict" not in st.session_state:
            st.session_state.precios_venta_dict = {}

        # Herramienta de asignación masiva por % de recargo para productos seleccionados
        with st.expander("⚡ Aplicar Porcentaje de Recargo (Markup) Masivo a Seleccionados", expanded=False):
            col_m1, col_m2 = st.columns([2, 1])
            with col_m1:
                porcentaje_markup_sugerido = st.number_input(
                    "Margen de Recargo sobre el Costo (%)",
                    min_value=0.0,
                    value=50.0,
                    step=5.0,
                    help="Ejemplo: Un 50% fijará el Precio de Venta = Costo por Litro * 1.50"
                )
            with col_m2:
                st.write(" ")
                st.write(" ")
                if st.button("Aplicar Recargo a Seleccionados", use_container_width=True):
                    for _, row in df_seleccionado.iterrows():
                        costo_litro = row["Costo por Litro (ARS)"]
                        precio_calculado = costo_litro * (1 + (porcentaje_markup_sugerido / 100.0))
                        st.session_state.precios_venta_dict[row["receta_id"]] = round(precio_calculado, 2)
                    st.success(f"¡Se aplicó un recargo del {porcentaje_markup_sugerido}% a los productos seleccionados!")

        # Función auxiliar para recuperar el precio actual guardado o sugerir un default (30% sobre el costo)
        def obtener_precio_actual(row):
            r_id = row["receta_id"]
            if r_id in st.session_state.precios_venta_dict:
                return st.session_state.precios_venta_dict[r_id]
            return round(row["Costo por Litro (ARS)"] * 1.30, 2)

        df_edicion_precios = pd.DataFrame({
            "receta_id": df_seleccionado["receta_id"],
            "Producto": df_seleccionado["nombre_receta"],
            "Costo Final / Litro ($ ARS)": df_seleccionado["Costo por Litro (ARS)"].apply(lambda x: round(x, 2)),
            "Precio Venta / Litro ($ ARS)": df_seleccionado.apply(obtener_precio_actual, axis=1)
        })

        # Mostrar editor de datos interactivo para los productos filtrados
        df_editado = st.data_editor(
            df_edicion_precios,
            column_config={
                "receta_id": None, # Ocultar ID
                "Producto": st.column_config.TextColumn("Producto", disabled=True),
                "Costo Final / Litro ($ ARS)": st.column_config.NumberColumn(
                    "Costo / Litro ($ ARS)", 
                    format="$ %.2f", 
                    disabled=True
                ),
                "Precio Venta / Litro ($ ARS)": st.column_config.NumberColumn(
                    "✏️ Precio Venta / Litro ($ ARS)", 
                    min_value=0.0, 
                    step=10.0, 
                    format="$ %.2f",
                    help="Hacé doble clic en esta celda para escribir el precio de venta deseado."
                )
            },
            use_container_width=True,
            hide_index=True,
            key="editor_precios_seleccionados"
        )

        # Actualizar Session State con las modificaciones del usuario
        for _, row_ed in df_editado.iterrows():
            st.session_state.precios_venta_dict[row_ed["receta_id"]] = row_ed["Precio Venta / Litro ($ ARS)"]

        df_seleccionado["Precio Venta / Litro Num"] = df_seleccionado["receta_id"].map(st.session_state.precios_venta_dict)
        df_seleccionado["Precio Venta / Litro Num"] = df_seleccionado["Precio Venta / Litro Num"].fillna(df_seleccionado["Costo por Litro (ARS)"] * 1.30)

        # Cálculos económicos detallados
        df_seleccionado["Venta Total Lote Num"] = df_seleccionado["Precio Venta / Litro Num"] * batch_size_l
        df_seleccionado["Ganancia Lote Num"] = df_seleccionado["Venta Total Lote Num"] - df_seleccionado["Costo Total Lote (ARS)"]
        df_seleccionado["Margen Ganancia Num"] = df_seleccionado.apply(
            lambda r: (r["Ganancia Lote Num"] / r["Venta Total Lote Num"] * 100) if r["Venta Total Lote Num"] > 0 else 0.0,
            axis=1
        )

        st.markdown("---")
        st.subheader("📈 3. Resumen Financiero y Rentabilidad por Producto")

        # Construcción segura del DataFrame de visualización
        df_display = pd.DataFrame()
        df_display["receta_id"] = df_seleccionado["receta_id"]
        df_display["Nombre de la Receta"] = df_seleccionado["nombre_receta"]
        df_display["Factor de Escala"] = df_seleccionado["Factor Escala"]
        df_display["Materia Prima (ARS)"] = df_seleccionado["Materia Prima (ARS/Lote)"].apply(formato_pesos)
        df_display["Costo Total Tambor (ARS)"] = df_seleccionado["Costo Total Lote (ARS)"].apply(formato_pesos)
        df_display["Costo Final por Litro (ARS)"] = df_seleccionado["Costo por Litro (ARS)"].apply(formato_pesos)
        df_display["Precio Venta / Litro (ARS)"] = df_seleccionado["Precio Venta / Litro Num"].apply(formato_pesos)
        df_display["Venta Total Lote (ARS)"] = df_seleccionado["Venta Total Lote Num"].apply(formato_pesos)
        df_display["Ganancia Lote (ARS)"] = df_seleccionado["Ganancia Lote Num"].apply(formato_pesos)
        df_display["Margen Ganancia (%)"] = df_seleccionado["Margen Ganancia Num"].apply(lambda x: f"{x:,.1f}%")

        # Ordenar alfabéticamente por nombre de producto
        df_display = df_display.sort_values(by="Nombre de la Receta", ascending=True)

        # Mostrar la tabla final
        st.dataframe(df_display.drop(columns=["receta_id"]), use_container_width=True, hide_index=True)

        st.markdown("### 📥 Descargar Reporte de Rentabilidad")
        st.write("Generá un documento PDF listo para compartir con el detalle de costos, precios y ganancias:")
        
        pdf_reporte = generar_pdf_reporte_costos(df_display, tipo_cambio, costo_asociado_fijo, batch_size_l, "ARS")
        
        st.download_button(
            label="📄 Exportar Análisis de Rentabilidad a PDF",
            data=pdf_reporte,
            file_name="reporte_costos_y_ventas_minerva.pdf",
            mime="application/pdf",
            use_container_width=True
        )

        st.markdown("---")
        st.subheader("🔍 Desglose Técnico de Ingredientes")
        st.write("Verificá la fórmula detallada y costos unitarios de insumos para cualquiera de los productos seleccionados:")
        
        receta_seleccionada_id = st.selectbox(
            "Ver ingredientes de la receta:",
            options=df_seleccionado["receta_id"].tolist(),
            format_func=lambda x: df_seleccionado[df_seleccionado["receta_id"] == x]["nombre_receta"].values[0]
        )
        
        if receta_seleccionada_id:
            df_ingredientes = obtener_ingredientes_receta(receta_seleccionada_id)
            if not df_ingredientes.empty:
                receta_info = df_seleccionado[df_seleccionado["receta_id"] == receta_seleccionada_id].iloc[0]
                factor_escala_num = receta_info["Factor Escala Num"]
                
                df_ingredientes["Costo Unitario (ARS)"] = df_ingredientes["ultimo_precio_usd"] * tipo_cambio
                df_ingredientes["Costo Total Insumo (ARS)"] = df_ingredientes["costo_ingrediente_usd"] * tipo_cambio
                
                df_ingredientes["Cantidad para Lote"] = df_ingredientes["cantidad"] * factor_escala_num
                df_ingredientes["Costo Lote (ARS)"] = df_ingredientes["Costo Total Insumo (ARS)"] * factor_escala_num
                
                suma_numerica_auditada = df_ingredientes["cantidad"].sum()
                unidad_predominante_auditada = df_ingredientes.groupby("unidad")["cantidad"].sum().idxmax() if not df_ingredientes.empty else "L"
                
                totales_texto_base = f"{suma_numerica_auditada:,.3f} {unidad_predominante_auditada}"
                totales_texto_lote = f"{(suma_numerica_auditada * factor_escala_num):,.2f} {unidad_predominante_auditada}"
                
                col_tot1, col_tot2, col_tot3 = st.columns(3)
                with col_tot1:
                    st.metric(label="⚖️ Cantidad Total Receta Base", value=totales_texto_base)
                with col_tot2:
                    st.metric(label="📦 Cantidad Total para Lote Objetivo", value=totales_texto_lote)
                with col_tot3:
                    st.metric(label="🔄 Factor de Multiplicación", value=f"x {factor_escala_num:,.2f}")
                
                st.markdown(" ")
                
                df_ing_display = df_ingredientes.copy()
                df_ing_display["Último Precio (USD)"] = df_ing_display["ultimo_precio_usd"].apply(lambda x: f"USD {x:,.4f}")
                df_ing_display["Precio Unitario (ARS)"] = df_ing_display["Costo Unitario (ARS)"].apply(formato_pesos)
                df_ing_display["Cant. para Lote"] = df_ing_display["Cantidad para Lote"].apply(lambda x: f"{x:,.3f}")
                df_ing_display["Costo Base (ARS)"] = df_ing_display["Costo Total Insumo (ARS)"].apply(formato_pesos)
                df_ing_display["Costo para Lote (ARS)"] = df_ing_display["Costo Lote (ARS)"].apply(formato_pesos)
                
                df_ing_display = df_ing_display[[
                    "ingrediente", "cantidad", "unidad", "Cant. para Lote",
                    "Último Precio (USD)", "Precio Unitario (ARS)", "Costo Base (ARS)", "Costo para Lote (ARS)"
                ]]
                df_ing_display.columns = [
                    "Ingrediente Activo", "Cant. Base", "Unidad", "Cant. p/ Lote",
                    "Último Precio (USD)", "Precio Unitario (ARS)", "Costo Base (ARS)", "Costo p/ Lote (ARS)"
                ]
                
                st.dataframe(df_ing_display, use_container_width=True, hide_index=True)
            else:
                st.warning("No se encontraron registros de materias primas cargadas para esta receta.")
    else:
        st.warning("⚠️ Seleccioná al menos un producto en el paso 1 para continuar con la asignación de precios.")
            
else:
    st.warning("No se pudieron cargar recetas de la base de datos. Aseguráte de que 'minerva.db' esté correctamente inicializada.")
