import streamlit as st
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Configuración de página de Streamlit
st.set_page_config(
    page_title="Generador de Presupuestos - Minerva",
    page_icon="🧴",
    layout="centered"
)

# Inicializar la lista de productos en el estado de sesión de Streamlit si no existe
if "lista_productos" not in st.session_state:
    st.session_state.lista_productos = []

st.title("🧴 Minerva - Generador de Presupuestos")
st.write("Cargá la información general, agregá uno a uno los productos capilares y generá el PDF formal.")

# 1. INFORMACIÓN GENERAL DEL PRESUPUESTO
st.subheader("1. Información General del Comprobante")
col1, col2 = st.columns(2)
with col1:
    nro_presupuesto = st.text_input("Número de Presupuesto", "PR-2026-0045")
    fecha_emision = st.text_input("Fecha de Emisión", "23 de Junio, 2026")
    validez = st.text_input("Validez de Oferta", "15 días corridos")
with col2:
    cliente = st.text_input("Cliente / Razón Social", "Distribuidora / Cliente Mayorista")
    moneda = st.selectbox("Moneda", ["ARS", "USD"])
    condicion_venta = st.text_input("Condición de Venta", "Contado / Transferencia")

st.markdown("---")

# 2. FORMULARIO PARA AGREGAR PRODUCTOS UNO POR UNO
st.subheader("2. Agregar Productos al Presupuesto")

# Campos de entrada con llaves únicas para resetearlos al enviar
col_prod1, col_prod2, col_prod3 = st.columns([1, 2, 1])
with col_prod1:
    prod_codigo = st.text_input("Código del Producto", "MC-ARG200", key="temp_codigo")
with col_prod2:
    prod_nombre = st.text_input("Nombre del Producto", "Máscara de Argán", key="temp_nombre")
with col_prod3:
    prod_cantidad = st.text_input("Cantidad / Formato", "1 Tambor (200 L)", key="temp_cantidad")

col_prod4, col_prod5 = st.columns([3, 1])
with col_prod4:
    prod_descripcion = st.text_input("Descripción / Detalle", "Tratamiento de nutrición capilar profunda.", key="temp_desc")
with col_prod5:
    prod_precio = st.number_input("Precio Unitario ($)", min_value=0.0, value=251500.0, step=500.0, key="temp_precio")

# Botones de control de lista
col_btn1, col_btn2 = st.columns([1, 1])
with col_btn1:
    if st.button("➕ Agregar Producto a la Lista", use_container_width=True):
        nuevo_item = {
            "codigo": prod_codigo,
            "nombre": prod_nombre,
            "descripcion": prod_descripcion,
            "cantidad": prod_cantidad,
            "precio": prod_precio
        }
        st.session_state.lista_productos.append(nuevo_item)
        st.success(f"¡{prod_nombre} agregado!")

with col_btn2:
    if st.button("🗑️ Vaciar Lista de Productos", use_container_width=True, type="secondary"):
        st.session_state.lista_productos = []
        st.warning("Lista de productos vaciada.")

st.markdown("---")

# 3. LISTA DE PRODUCTOS ACTUALMENTE AGREGADOS
st.subheader("3. Vista Previa de Productos Agregados")

if len(st.session_state.lista_productos) == 0:
    st.info("Aún no has agregado productos al presupuesto actual. Completá los campos anteriores y presioná 'Agregar'.")
else:
    # Mostrar la lista en formato amigable
    subtotal_acumulado = 0.0
    for idx, item in enumerate(st.session_state.lista_productos):
        subtotal_acumulado += item["precio"]
        precio_txt = f"$ {item['precio']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        st.markdown(f"**Item {idx+1}:** `[{item['codigo']}]` **{item['nombre']}** ({item['cantidad']}) — **{precio_txt}**")
        st.caption(f"Detalle: {item['descripcion']}")
    
    total_general_txt = f"$ {subtotal_acumulado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    st.markdown(f"### Total Estimado: **{total_general_txt} {moneda}**")


# FUNCIÓN PARA GENERAR EL PDF USANDO REPORTLAB
def generar_pdf_reportlab_multiple(datos_gen, lista_prod):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter,
        rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    # --- ESTILOS ---
    style_titulo_empresa = ParagraphStyle('TxtTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=24, textColor=colors.HexColor("#f39c12"))
    style_sub_empresa = ParagraphStyle('TxtSub', parent=styles['Normal'], fontName='Helvetica', fontSize=10, textColor=colors.HexColor("#bdc3c7"))
    style_tipo_doc = ParagraphStyle('TxtDoc', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=18, textColor=colors.white, alignment=2)
    style_nro_doc = ParagraphStyle('TxtNro', parent=styles['Normal'], fontName='Helvetica', fontSize=10, textColor=colors.HexColor("#bdc3c7"), alignment=2)
    style_meta_label = ParagraphStyle('MetaLbl', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor("#34495e"))
    style_meta_val = ParagraphStyle('MetaVal', fontName='Helvetica', fontSize=10, textColor=colors.HexColor("#555555"))
    style_h2 = ParagraphStyle('H2', fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor("#1a252f"), spaceBefore=15, spaceAfter=5)
    style_body = ParagraphStyle('Body', fontName='Helvetica', fontSize=10, textColor=colors.HexColor("#555555"), spaceAfter=10)
    style_th = ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=9, textColor=colors.white)
    style_td = ParagraphStyle('TD', fontName='Helvetica', fontSize=9.5, textColor=colors.HexColor("#2c3e50"))
    style_td_desc = ParagraphStyle('TDDesc', fontName='Helvetica-Oblique', fontSize=8, textColor=colors.HexColor("#7f8c8d"))
    style_condiciones = ParagraphStyle('Cond', fontName='Helvetica', fontSize=9, textColor=colors.HexColor("#6c757d"), leading=13)
    style_advertencia = ParagraphStyle('Adv', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor("#c0392b"), leading=13)

    # --- ENCABEZADO ---
    header_data = [
        [Paragraph("FÁBRICA MINERVA", style_titulo_empresa), Paragraph("PRESUPUESTO", style_tipo_doc)],
        [Paragraph("Cosmética Capilar de Alta Calidad", style_sub_empresa), Paragraph(f"Nro: {datos_gen['nro_presupuesto']}", style_nro_doc)]
    ]
    header_table = Table(header_data, colWidths=[280, 252])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#1a252f")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,0), 12),
        ('BOTTOMPADDING', (0,-1), (-1,-1), 12),
        ('LEFTPADDING', (0,0), (0,-1), 15),
        ('RIGHTPADDING', (-1,0), (-1,-1), 15),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 15))

    # --- METADATOS ---
    meta_data = [
        [Paragraph("FECHA DE EMISIÓN:", style_meta_label), Paragraph(datos_gen['fecha_emision'], style_meta_val),
         Paragraph("CLIENTE:", style_meta_label), Paragraph(datos_gen['cliente'], style_meta_val)],
        [Paragraph("VALIDEZ DE OFERTA:", style_meta_label), Paragraph(datos_gen['validez'], style_meta_val),
         Paragraph("MONEDA:", style_meta_label), Paragraph(datos_gen['moneda'], style_meta_val)],
        [Paragraph("ORIGEN:", style_meta_label), Paragraph("San Miguel de Tucumán", style_meta_val),
         Paragraph("CONDICIÓN VENTA:", style_meta_label), Paragraph(datos_gen['condicion_venta'], style_meta_val)]
    ]
    meta_table = Table(meta_data, colWidths=[110, 156, 110, 156])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,-1), (-1,-1), 1, colors.HexColor("#ecf0f1")),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # --- SECCIÓN DETALLE ---
    story.append(Paragraph("DETALLE DEL PRESUPUESTO", style_h2))
    story.append(Paragraph("A continuación se detalla la cotización correspondiente a los productos solicitados:", style_body))
    
    # --- CONSTRUCCIÓN DINÁMICA DE LA TABLA ---
    table_content = [
        [Paragraph("CÓDIGO", style_th), Paragraph("DESCRIPCIÓN DEL PRODUCTO", style_th), Paragraph("CANTIDAD / FORMATO", style_th), Paragraph("PRECIO UNITARIO", style_th)]
    ]
    
    subtotal_acumulado = 0.0
    
    for item in lista_prod:
        cod = str(item["codigo"])
        prod = str(item["nombre"])
        desc = str(item["descripcion"])
        cant = str(item["cantidad"])
        precio = float(item["precio"])
        
        subtotal_acumulado += precio
        precio_txt = f"$ {precio:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        celda_descripcion = [
            Paragraph(f"<b>{prod}</b>", style_td),
            Paragraph(desc, style_td_desc)
        ]
        
        table_content.append([
            Paragraph(cod, style_td),
            celda_descripcion,
            Paragraph(cant, style_td),
            Paragraph(precio_txt, style_td)
        ])
    
    prod_table = Table(table_content, colWidths=[70, 242, 110, 110])
    
    estilo_tabla = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#34495e")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (2,0), (3,-1), 'CENTER'),
        ('PADDING', (0,0), (-1,-1), 6),
    ]
    
    for i in range(1, len(table_content)):
        bg_color = colors.HexColor("#f8fafc") if i % 2 != 0 else colors.white
        estilo_tabla.append(('BACKGROUND', (0, i), (-1, i), bg_color))
        estilo_tabla.append(('LINEBELOW', (0, i), (-1, i), 0.5, colors.HexColor("#e2e8f0")))
        
    prod_table.setStyle(TableStyle(estilo_tabla))
    story.append(prod_table)
    story.append(Spacer(1, 15))

    # --- CUADRO DE TOTALES ---
    total_general_txt = f"$ {subtotal_acumulado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    total_data = [
        [Paragraph("Subtotal:", style_meta_label), Paragraph(total_general_txt, style_td)],
        [Paragraph("Impuestos / Gastos:", style_meta_label), Paragraph("$ 0,00", style_td)],
        [Paragraph("<font color='#d35400'><b>Total Neto:</b></font>", style_h2), Paragraph(f"<font color='#d35400'><b>{total_general_txt}</b></font>", style_h2)]
    ]
    total_table = Table(total_data, colWidths=[110, 100])
    total_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#fdf5e6")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#f39c12")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 6),
        ('LINEBELOW', (0,0), (-1,1), 0.5, colors.HexColor("#f39c12")),
    ]))
    
    extern_total_table = Table([["", total_table]], colWidths=[322, 210])
    extern_total_table.setStyle(TableStyle([
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(extern_total_table)
    story.append(Spacer(1, 15))

    # --- TÉRMINOS Y CONDICIONES ---
    condiciones_html = (
        "<b>Términos y Condiciones Comerciales:</b><br/>"
        "• Plazo de Entrega: A coordinar según stock de producción diario en planta (Tucumán).<br/>"
        "• Forma de Pago: Depósito o transferencia bancaria previo a la liberación de la mercadería.<br/>"
    )
    advertencia_html = (
        "<b>Importante:</b> Los valores expresados en pesos están sujetos a la cotización oficial del "
        "dólar estadounidense (Banco Nación) del día de la facturación o pago efectivo."
    )
    
    cond_table = Table([[Paragraph(condiciones_html, style_condiciones)], [Paragraph(advertencia_html, style_advertencia)]], colWidths=[532])
    cond_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8f9fa")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#e9ecef")),
        ('PADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,1), (-1,1), 0),
    ]))
    story.append(cond_table)
    story.append(Spacer(1, 40))

    # --- SECCIÓN FIRMAS ---
    firma_table = Table([[Paragraph("___________________________<br/>Departamento Comercial<br/>Fábrica Minerva", style_body),
                          Paragraph("___________________________<br/>Aceptación de Cliente<br/>&nbsp;", style_body)]], colWidths=[266, 266])
    firma_table.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
    story.append(firma_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# 4. BOTÓN FINAL PARA EMITIR EL COMPROBANTE COMPILADO
st.markdown("---")
st.subheader("4. Generación del Comprobante")

if st.button("🔥 Generar PDF Completo", use_container_width=True, type="primary"):
    if len(st.session_state.lista_productos) == 0:
        st.error("No podés generar un presupuesto sin productos. Agregá al menos uno usando el formulario del punto 2.")
    else:
        datos_generales = {
            "nro_presupuesto": nro_presupuesto,
            "fecha_emision": fecha_emision,
            "validez": validez,
            "cliente": cliente,
            "moneda": moneda,
            "condicion_venta": condicion_venta
        }
        
        # Generar binario usando ReportLab
        archivo_pdf = generar_pdf_reportlab_multiple(datos_generales, st.session_state.lista_productos)
        
        st.success("✨ ¡Presupuesto compilado de forma nativa!")
        st.download_button(
            label="📥 Descargar Presupuesto Completo (PDF)",
            data=archivo_pdf,
            file_name=f"presupuesto_{nro_presupuesto}.pdf",
            mime="application/pdf",
            use_container_width=True
        )