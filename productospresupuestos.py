import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle

def get_connection():
    return sqlite3.connect('minerva.db')

def generar_pdf_presupuesto(nombre_cliente, fecha, df_carrito, descuento_global_porc):
    """Genera el PDF con la lógica de sumatorias solicitada."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Encabezado
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, height - 2*cm, "PRESUPUESTO COMERCIAL")
    
    c.setFont("Helvetica", 10)
    c.drawString(2*cm, height - 3*cm, f"Cliente: {nombre_cliente}")
    c.drawString(2*cm, height - 3.5*cm, f"Fecha: {fecha.strftime('%d/%m/%Y')}")
    
    # Variables para los cálculos finales
    suma_subtotales_originales = 0
    suma_descuentos_items = 0
    
    data = [["PRODUCTO", "CANT", "PRECIO U.", "SUBTOTAL", "DESC.", "SUBT. FINAL"]]
    
    for _, row in df_carrito.iterrows():
        bruto_linea = row['Cantidad'] * row['Precio Unit.']
        monto_desc_linea = bruto_linea * (row['Desc %'] / 100)
        final_linea = row['Subtotal']
        
        # Acumuladores
        suma_subtotales_originales += bruto_linea
        suma_descuentos_items += monto_desc_linea
        
        data.append([
            row["Producto"],
            f"{row['Cantidad']}",
            f"${row['Precio Unit.']:,.2f}",
            f"${bruto_linea:,.2f}",
            f"${monto_desc_linea:,.2f}",
            f"${final_linea:,.2f}"
        ])
    
    # Tabla
    tabla = Table(data, colWidths=[5.5*cm, 1.5*cm, 2.5*cm, 2.5*cm, 3*cm, 3*cm])
    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ])
    tabla.setStyle(style)
    
    tabla.wrapOn(c, width, height)
    tabla_height = len(data) * 0.6 * cm
    tabla.drawOn(c, 1*cm, height - 5*cm - tabla_height)
    
    # --- LÓGICA DE TOTALES ---
    pos_y = height - 6*cm - tabla_height
    
    # 1. Total Original (Suma de precios sin ningún descuento)
    total_original = suma_subtotales_originales
    
    # 2. Total Descuento (Suma de descuentos por ítem + descuento global sobre el subtotal parcial)
    subtotal_con_desc_items = total_original - suma_descuentos_items
    monto_desc_global = subtotal_con_desc_items * (descuento_global_porc / 100)
    total_descuento_acumulado = suma_descuentos_items + monto_desc_global
    
    # 3. Total Final
    total_final_con_desc = total_original - total_descuento_acumulado

    c.setFont("Helvetica-Bold", 11)
    c.drawString(10*cm, pos_y, f"TOTAL ORIGINAL: ${total_original:,.2f}")
    c.drawString(10*cm, pos_y - 0.7*cm, f"TOTAL DESCUENTO: ${total_descuento_acumulado:,.2f}")
    
    c.line(10*cm, pos_y - 1*cm, 19*cm, pos_y - 1*cm)
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(10*cm, pos_y - 1.6*cm, f"TOTAL FINAL CON DESCUENTO: ${total_final_con_desc:,.2f}")
    
    c.save()
    buffer.seek(0)
    return buffer

def presupuesto_generico_app():
    st.title("📑 Generador de Presupuestos")

    # 1. Datos del Cliente
    with st.expander("👤 Información del Cliente", expanded=True):
        col_c1, col_c2 = st.columns(2)
        nombre_cliente = col_c1.text_input("Nombre del Cliente / Razón Social", placeholder="Ej: Distribuidora Norte")
        fecha_presupuesto = col_c2.date_input("Fecha", datetime.now())

    if 'carrito' not in st.session_state:
        st.session_state.carrito = []

    # 2. Buscador de Productos
    st.subheader("🔍 Selección de Productos")
    conn = get_connection()
    query = """
        SELECT p.id, p.nombre, l.nombre as linea, 
               (SELECT pre.precio_unitario FROM precios_productos_envasados pre 
                WHERE pre.producto_id = p.id AND (pre.fecha_hasta IS NULL OR pre.fecha_hasta > date('now'))
                ORDER BY pre.fecha_desde DESC LIMIT 1) as precio_db
        FROM productos p
        LEFT JOIN lineas l ON p.linea_id = l.id
    """
    df_db = pd.read_sql(query, conn)
    conn.close()

    col1, col2, col3, col4, col5 = st.columns([2.5, 1, 1, 1, 1])
    
    with col1:
        opciones = df_db.apply(lambda x: f"{x['nombre']} - {x['linea'] if x['linea'] else 'General'}", axis=1).tolist()
        seleccion = st.selectbox("Producto", ["-- Seleccione --"] + opciones)
    
    with col2:
        cantidad = st.number_input("Cant.", min_value=0.1, value=1.0)

    if seleccion != "-- Seleccione --":
        idx = opciones.index(seleccion)
        producto_info = df_db.iloc[idx]
        precio_sugerido = float(producto_info['precio_db']) if pd.notnull(producto_info['precio_db']) else 0.0
        
        with col3:
            precio_u = st.number_input("Precio U.", value=precio_sugerido, min_value=0.0)
        with col4:
            desc_prod = st.number_input("% Desc.", min_value=0, max_value=100, value=0, key="desc_p")
        
        with col5:
            st.write(" ")
            if st.button("➕ Añadir"):
                precio_con_desc = precio_u * (1 - desc_prod/100)
                st.session_state.carrito.append({
                    "ID": producto_info['id'],
                    "Producto": producto_info['nombre'],
                    "Cantidad": cantidad,
                    "Precio Unit.": precio_u,
                    "Desc %": desc_prod,
                    "Subtotal": cantidad * precio_con_desc
                })
                st.rerun()

    # 3. Visualización y PDF
    if st.session_state.carrito:
        st.subheader("📋 Detalle Actual")
        df_carrito = pd.DataFrame(st.session_state.carrito)
        
        df_mostrar = df_carrito.copy()
        df_mostrar["Subt. Bruto"] = df_mostrar["Cantidad"] * df_mostrar["Precio Unit."]
        df_mostrar["Ahorro"] = df_mostrar["Subt. Bruto"] - df_mostrar["Subtotal"]
        
        st.table(df_mostrar[["Producto", "Cantidad", "Precio Unit.", "Desc %", "Ahorro", "Subtotal"]].style.format({
            "Precio Unit.": "${:.2f}", "Subt. Bruto": "${:.2f}", "Ahorro": "${:.2f}", "Subtotal": "${:.2f}"
        }))

        st.divider()
        c1, c2, c3 = st.columns(3)
        total_bruto_carrito = df_carrito["Subtotal"].sum()
        
        with c1:
            desc_global = st.number_input("% Descuento General (Extra)", min_value=0, max_value=100, value=0)
        with c2:
            total_neto = total_bruto_carrito * (1 - desc_global/100)
            st.metric("TOTAL NETO", f"${total_neto:,.2f}")
        with c3:
            if st.button("🗑️ Vaciar"):
                st.session_state.carrito = []
                st.rerun()

        if nombre_cliente:
            # Pasamos solo el descuento global, la función PDF recalcula todo desde el carrito
            pdf_file = generar_pdf_presupuesto(nombre_cliente, fecha_presupuesto, df_carrito, desc_global)
            st.download_button(
                label="📥 Descargar Presupuesto PDF",
                data=pdf_file,
                file_name=f"Presupuesto_{nombre_cliente}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        else:
            st.warning("Escriba el nombre del cliente para habilitar la descarga.")
    else:
        st.info("Agregue productos para ver el detalle.")

if __name__ == "__main__":
    presupuesto_generico_app()