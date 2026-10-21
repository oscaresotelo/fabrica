from fpdf import FPDF

class OrdenPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'ORDEN DE COMPRA', border=False, ln=True, align='C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', align='C')


class RemitoPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'REMITO DE TRANSPORTE', border=False, ln=True, align='C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', align='C')


def generar_pdf_bytes(datos_encabezado, df_detalles, transporte=""):
    pdf = OrdenPDF()
    pdf.add_page()

    # Información del encabezado
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(40, 7, "ID Orden:", 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 7, str(datos_encabezado['ID']), 0, 1)

    pdf.set_font('Arial', 'B', 10)
    pdf.cell(40, 7, "Proveedor:", 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 7, str(datos_encabezado['Proveedor']), 0, 1)

    pdf.set_font('Arial', 'B', 10)
    pdf.cell(40, 7, "Fecha Emisión:", 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 7, str(datos_encabezado['Fecha']), 0, 1)

    # Campo Transporte (solo se muestra si tiene valor)
    transporte_str = str(transporte).strip() if transporte else ""
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(40, 7, "Transporte:", 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 7, transporte_str if transporte_str else "S/D", 0, 1)

    pdf.ln(10)

    # Tabla de detalles - Encabezados
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(80, 10, 'Materia Prima', 1, 0, 'C', True)
    pdf.cell(30, 10, 'Cantidad', 1, 0, 'C', True)
    pdf.cell(40, 10, 'P. Unitario', 1, 0, 'C', True)
    pdf.cell(40, 10, 'Subtotal', 1, 1, 'C', True)

    # Filas de la tabla
    pdf.set_font('Arial', '', 10)
    total = 0
    for _, row in df_detalles.iterrows():
        cant = float(row['Cantidad'])
        precio = float(row['Precio Unitario'])
        subtotal = cant * precio
        total += subtotal

        pdf.cell(80, 8, str(row['Materia Prima']), 1)
        pdf.cell(30, 8, f"{cant:,.2f}", 1, 0, 'R')
        pdf.cell(40, 8, f"$ {precio:,.2f}", 1, 0, 'R')
        pdf.cell(40, 8, f"$ {subtotal:,.2f}", 1, 1, 'R')

    # Total final
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(150, 10, 'TOTAL', 1, 0, 'R', True)
    pdf.cell(40, 10, f"$ {total:,.2f}", 1, 1, 'R', True)

    # Generamos la salida del PDF
    pdf_output = pdf.output(dest="S")

    # Conversión robusta a 'bytes' (Estándar para Streamlit en cualquier entorno)
    if isinstance(pdf_output, str):
        pdf_output = pdf_output.encode("latin1")
    else:
        pdf_output = bytes(pdf_output)

    return pdf_output


def generar_pdf_remito_transporte(datos_encabezado, df_detalles, transporte=""):
    """
    Genera un PDF simplificado para el transportista:
    solo proveedor, transporte, y cantidades de materia prima. Sin precios.
    """
    pdf = RemitoPDF()
    pdf.add_page()

    # Encabezado
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(40, 7, "ID Orden:", 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 7, str(datos_encabezado['ID']), 0, 1)

    pdf.set_font('Arial', 'B', 10)
    pdf.cell(40, 7, "Proveedor:", 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 7, str(datos_encabezado['Proveedor']), 0, 1)

    transporte_str = str(transporte).strip() if transporte else ""
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(40, 7, "Transporte:", 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 7, transporte_str if transporte_str else "S/D", 0, 1)

    pdf.set_font('Arial', 'B', 10)
    pdf.cell(40, 7, "Fecha Emisión:", 0)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 7, str(datos_encabezado['Fecha']), 0, 1)

    pdf.ln(10)

    # Tabla sin precios
    pdf.set_fill_color(200, 220, 255)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(120, 10, 'Materia Prima', 1, 0, 'C', True)
    pdf.cell(70, 10, 'Cantidad', 1, 1, 'C', True)

    pdf.set_font('Arial', '', 10)
    for _, row in df_detalles.iterrows():
        cant = float(row['Cantidad'])
        pdf.cell(120, 8, str(row['Materia Prima']), 1)
        pdf.cell(70, 8, f"{cant:,.2f}", 1, 1, 'R')

    # Línea de firma al pie
    pdf.ln(20)
    pdf.set_font('Arial', '', 10)
    pdf.cell(90, 8, "Firma Transportista: ______________________", 0)
    pdf.cell(90, 8, "Aclaración: ______________________", 0, 1)

    # Generamos la salida del PDF
    pdf_bytes = pdf.output(dest="S")

    # Conversión robusta a 'bytes' (Evita el error en st.download_button en cualquier entorno)
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode("latin1")
    else:
        pdf_bytes = bytes(pdf_bytes)

    return pdf_bytes