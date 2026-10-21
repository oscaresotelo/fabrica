
import streamlit as st
import pandas as pd
from fpdf import FPDF

st.set_page_config(page_title="Minerva - Control de Fechas", layout="wide")

@st.cache_data
def load_data():
    params = {'encoding': 'latin-1', 'low_memory': False}
    art = pd.read_csv('articulos.TXT', **params)
    comp = pd.read_csv('comprobante.TXT', **params)
    det = pd.read_csv('comprobantedetalle.TXT', **params)
    
    # Limpieza de columnas
    for df in [art, comp, det]:
        df.columns = df.columns.str.strip()

    # Normalización claves
    det['articulo'] = det['articulo'].astype(str).str.strip()
    art['codigo'] = art['codigo'].astype(str).str.strip()
    det['codigo_comp'] = det['codigo_comp'].astype(str).str.strip()
    comp['codigo'] = comp['codigo'].astype(str).str.strip()
    
    # Fecha
    comp['fecha'] = pd.to_datetime(comp['fecha'], errors='coerce')
    
    return art, comp, det


def generar_pdf(df, desde, hasta):
    pdf = FPDF()
    pdf.add_page()
    
    # Título
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "MINERVA - REPORTE DE PRODUCTOS", ln=True, align="C")
    
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 10, f"Desde: {desde} | Hasta: {hasta}", ln=True, align="C")
    pdf.ln(5)

    # Encabezado tabla (SIN IMPORTES)
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(140, 8, "Producto", 1, 0, "L", True)
    pdf.cell(40, 8, "Cantidad", 1, 1, "C", True)

    # Datos
    pdf.set_font("Arial", "", 9)

    for _, row in df.iterrows():
        pdf.cell(140, 7, str(row['nombre'])[:65], 1)
        pdf.cell(40, 7, str(int(row['cantidad'])), 1, 1, "C")

    # 🔥 CLAVE: convertir a bytes
    return pdf.output(dest='S').encode('latin-1')


try:
    art, comp, det = load_data()

    st.title("📊 Consulta de Ventas por Período")

    # Sidebar fechas
    st.sidebar.header("Selección de Período")
    
    fecha_minima = comp['fecha'].min().date()
    fecha_maxima = comp['fecha'].max().date()

    desde = st.sidebar.date_input(
        "Fecha Desde:",
        value=fecha_minima,
        min_value=fecha_minima,
        max_value=fecha_maxima
    )

    hasta = st.sidebar.date_input(
        "Fecha Hasta:",
        value=fecha_maxima,
        min_value=fecha_minima,
        max_value=fecha_maxima
    )

    if desde > hasta:
        st.error("Error: La fecha 'Desde' no puede ser posterior a la fecha 'Hasta'.")
    else:
        # Filtrar comprobantes
        mask = (comp['fecha'].dt.date >= desde) & (comp['fecha'].dt.date <= hasta)
        comp_filt = comp[mask]

        # Joins
        ventas = pd.merge(
            comp_filt[['codigo']],
            det,
            left_on='codigo',
            right_on='codigo_comp'
        )

        final = pd.merge(
            ventas,
            art[['codigo', 'nombre']],
            left_on='articulo',
            right_on='codigo'
        )

        # Agrupar SOLO lo necesario
        resumen = final.groupby('nombre').agg({
            'cantidad': 'sum'
        }).sort_values(by='cantidad', ascending=False).reset_index()

        if not resumen.empty:
            st.success(f"Se encontraron {len(resumen)} productos vendidos en este rango.")

            # Generar PDF
            pdf_bytes = generar_pdf(resumen.head(50), desde, hasta)

            st.download_button(
                label="🖨️ Generar Informe PDF",
                data=pdf_bytes,
                file_name=f"Productos_{desde}_al_{hasta}.pdf",
                mime="application/pdf"
            )

            # Vista previa
            st.dataframe(resumen, use_container_width=True)

        else:
            st.warning("No hay ventas registradas en el período seleccionado.")

except Exception as e:
    st.error(f"Hubo un problema al procesar los archivos: {e}")

