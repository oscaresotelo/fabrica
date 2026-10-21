import streamlit as st
import barcode
from barcode.writer import ImageWriter
import pandas as pd
import os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURACIÓN ---
PREFIJO_PAIS = "779"
CODIGO_EMPRESA = "82145" 
CSV_FILE = "db_minerva.csv"

st.set_page_config(page_title="Minerva Barcode System", page_icon="🌿")

if not os.path.exists(CSV_FILE):
    pd.DataFrame(columns=["SKU", "Producto", "Codigo_Completo"]).to_csv(CSV_FILE, index=False)

def get_next_sku():
    df = pd.read_csv(CSV_FILE)
    return len(df) + 1

st.title("🌿 Minerva: Generador Profesional")

nombre_prod = st.text_input("Nombre del Producto", placeholder="Ej: SHAMPOO POST COLOR EXTRA ACIDO")
confirmar = st.button("Generar Etiqueta Clara")

if confirmar and nombre_prod:
    proximo_sku = str(get_next_sku()).zfill(4)
    cadena_12 = f"{PREFIJO_PAIS}{CODIGO_EMPRESA}{proximo_sku}"
    
    # 1. Generamos el código de barras puro (sin texto automático para que no se pise)
    EAN = barcode.get_barcode_class('ean13')
    # Usamos ImageWriter con texto desactivado para controlarlo nosotros
    barcode_obj = EAN(cadena_12, writer=ImageWriter())
    full_code = barcode_obj.get_fullcode()
    
    buffer = BytesIO()
    barcode_obj.write(buffer, options={"write_text": False, "module_height": 15.0})
    img_barcode = Image.open(buffer)
    
    # 2. Creamos un lienzo nuevo más alto para separar los elementos
    # Ancho original, pero le damos 150px más de alto para texto arriba y abajo
    w, h = img_barcode.size
    final_img = Image.new('RGB', (w, h + 150), (255, 255, 255))
    
    # 3. Pegamos el código de barras en el centro
    final_img.paste(img_barcode, (0, 70))
    
    # 4. Dibujamos los textos manualmente
    draw = ImageDraw.Draw(final_img)
    try:
        # Intentamos usar una fuente estándar, si no la básica
        font_nombre = ImageFont.truetype("arial.ttf", 25)
        font_codigo = ImageFont.truetype("arial.ttf", 35)
    except:
        font_nombre = ImageFont.load_default()
        font_codigo = ImageFont.load_default()

    # Nombre del producto arriba (bien centrado y separado)
    draw.text((w/2, 35), nombre_prod.upper(), fill=(0, 0, 0), anchor="mm", font=font_nombre)
    
    # Número del código abajo (grande y sin tocar las barras)
    draw.text((w/2, h + 100), full_code, fill=(0, 0, 0), anchor="mm", font=font_codigo)
    
    # 5. Registro y visualización
    pd.DataFrame([[get_next_sku(), nombre_prod, full_code]]).to_csv(CSV_FILE, mode='a', header=False, index=False)
    
    st.image(final_img, caption="Vista previa de la etiqueta corregida")
    
    img_io = BytesIO()
    final_img.save(img_io, 'PNG')
    st.download_button("📥 Descargar Etiqueta (Formato Correcto)", img_io.getvalue(), f"Minerva_{full_code}.png")

st.divider()
st.subheader("📋 Inventario Registrado")
st.dataframe(pd.read_csv(CSV_FILE), use_container_width=True)