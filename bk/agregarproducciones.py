import streamlit as st
import sqlite3
from datetime import datetime, date
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import uuid
import pandas as pd

def gestionar_produccion():
    # --- Estilos ---
    st.markdown("""
    <style>
        .metric-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .stButton>button {
            background-color: #0072C6;
            color: white;
            font-weight: 600;
            border-radius: 8px;
            padding: 10px 20px;
            margin-top: 10px;
        }
        .stButton>button:hover {
            background-color: #005a9e;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("# 🏭 Gestión de Producción")
    st.markdown("---")

    def generar_numero_lote():
        """Genera un número de lote único con fecha y código aleatorio"""
        return f"Lote-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

    def obtener_pedidos():
        """Obtiene todos los pedidos pendientes"""
        with sqlite3.connect("minerva.db") as conn:
            return conn.execute('''
                SELECT pp.id, c.nombre, r.nombre, pp.cantidad, pp.numero_pedido, pp.fecha, 
                       pp.estado, pp.receta_id, pp.lote, pp.cliente_id
                FROM pedidos_produccion pp
                JOIN clientes c ON pp.cliente_id = c.id
                JOIN recetas r ON pp.receta_id = r.id
                WHERE pp.estado = 'pendiente'
                ORDER BY pp.fecha
            ''').fetchall()

    def obtener_ingredientes(receta_id):
        """Obtiene los ingredientes escalados según la receta"""
        with sqlite3.connect("minerva.db") as conn:
            return conn.execute('''
                SELECT mp.id, mp.nombre, ri.cantidad, ri.unidad
                FROM receta_ingredientes ri
                JOIN materias_primas mp ON ri.materia_prima_id = mp.id
                WHERE ri.receta_id = ?
            ''', (receta_id,)).fetchall()

    def generar_pdf_receta(cliente, receta, cantidad, numero_pedido, fecha_pedido, lote, ingredientes):
        """Genera PDF con la receta escalada"""
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        width, height = letter
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, height - 50, f"Receta de Producción - {receta}")
        c.setFont("Helvetica", 12)
        y = height - 80
        for txt in [f"Cliente: {cliente}", f"Pedido: {numero_pedido}",
                    f"Fecha pedido: {fecha_pedido}", f"Cantidad: {cantidad} litros",
                    f"Lote: {lote or 'No asignado'}"]:
            c.drawString(50, y, txt)
            y -= 18
        c.drawString(50, y, "Ingredientes escalados:")
        y -= 20
        for nombre, cant, unidad in ingredientes:
            if unidad.lower() in ["l", "litros"] and cant < 1:
                cant *= 1000
                unidad = "cm³"
            elif unidad.lower() in ["kg", "kilos"] and cant < 1:
                cant *= 1000
                unidad = "g"
            c.drawString(70, y, f"- {nombre}: {cant:.3f} {unidad}")
            y -= 18
            if y < 50:
                c.showPage()
                y = height - 50
        c.drawString(50, y - 30, "Firma supervisor: _______________________")
        c.showPage()
        c.save()
        buf.seek(0)
        return buf

    def imprimir_rotulo(cliente, receta, lote, fecha):
        """Genera un PDF simple con el rótulo del lote"""
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        height = letter[1]
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 100, f"Producto: {receta}")
        c.drawString(50, height - 130, f"Número de Lote: {lote}")
        c.drawString(50, height - 160, f"Fecha producida: {fecha}")
        c.drawString(50, height - 190, f"Cliente: {cliente}")
        c.showPage()
        c.save()
        buf.seek(0)
        return buf

    # --- Cargar pedidos pendientes ---
    pedidos = obtener_pedidos()
    if not pedidos:
        st.info("ℹ️ No hay pedidos pendientes para producción.")
        st.stop()

    pedido_labels = [f"{p[1]} - {p[2]} - Pedido N°: {p[4]} - Estado: {p[6].capitalize()}" for p in pedidos]
    seleccion = st.selectbox("Seleccionar pedido", pedido_labels)
    pedido = pedidos[pedido_labels.index(seleccion)]
    pedido_id, cliente, receta, cantidad, numero_pedido, fecha_pedido, estado, receta_id, lote, cliente_id = pedido

    # Escalar ingredientes
    ingredientes_raw = obtener_ingredientes(receta_id)
    factor = cantidad / 200
    ingredientes = [(i[1], i[2]*factor, i[3]) for i in ingredientes_raw]

    col1, col2 = st.columns([2, 3])
    with col1:
        st.markdown("### 🧾 Información del Pedido")
        st.write(f"**Cliente:** {cliente}")
        st.write(f"**Receta:** {receta}")
        st.write(f"**Cantidad:** {cantidad} litros")
        st.write(f"**N° Pedido:** {numero_pedido}")
        st.write(f"**Fecha pedido:** {fecha_pedido}")
        st.write(f"**Estado actual:** `{estado}`")

    with col2:
        st.markdown("### 🧪 Ingredientes Escalados")
        st.dataframe(
            pd.DataFrame(ingredientes, columns=["Ingrediente", "Cantidad", "Unidad"])
            .style.format({"Cantidad": "{:.3f}"}),
            use_container_width=True
        )

    st.markdown("---")

    # --- Selector de fecha ---
    st.markdown("### 📅 Seleccionar fecha de producción")
    fecha_produccion = st.date_input("Fecha de producción", value=date.today())
    fecha_formateada = f"{fecha_produccion.strftime('%Y-%m-%d')} 00:00:00"

    # --- Confirmar producción ---
    if st.button("✅ Confirmar producción"):
        lote_gen = generar_numero_lote()

        with sqlite3.connect("minerva.db") as conn:
            cur = conn.cursor()

            # Insertar en producciones con estado PRODUCIDO
            cur.execute("""
                INSERT INTO producciones (pedido_id, fecha, lote, estado, cantidad_litros, litros_envasados, cantidad_real_litros)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (pedido_id, fecha_formateada, lote_gen, 'producido', cantidad, 0, cantidad))

            # Actualizar el pedido a PRODUCIDO
            cur.execute("""
                UPDATE pedidos_produccion 
                SET lote = ?, estado = 'producido'
                WHERE id = ?
            """, (lote_gen, pedido_id))

            conn.commit()

        st.success(f"✅ Producción registrada correctamente como 'producido'.\n\n📦 Lote: {lote_gen}\n📅 Fecha: {fecha_formateada}")

        # Botón de descarga del rótulo
        st.download_button(
            "🏷️ Imprimir rótulo",
            imprimir_rotulo(cliente, receta, lote_gen, fecha_formateada),
            file_name=f"rotulo_{lote_gen}.pdf",
            mime="application/pdf"
        )

gestionar_produccion()
