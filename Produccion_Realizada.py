import streamlit as st
import sqlite3
import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

# --- Control de acceso ---
if "usuario" not in st.session_state:
    st.error("❌ Acceso denegado. Inicie sesión.")
    st.stop()
elif st.session_state.usuario.get("rol") != "Administrador":
    st.error("🚫 Acceso restringido. Solo para Administradores.")
    st.stop()

def cargar_producciones():
    conn = sqlite3.connect("minerva.db")
    query = """
        SELECT 
            pr.id AS produccion_id,
            pr.fecha,
            pr.lote,
            pp.numero_pedido,
            pp.cantidad AS cantidad_litros,
            c.nombre AS cliente,
            r.nombre AS receta,
            COALESCE((
                SELECT SUM(oe.cantidad_unidades)
                FROM ordenes_envasado oe
                WHERE oe.produccion_id = pr.id
            ), 0) AS cantidad_envasada,
            (pp.cantidad - COALESCE((
                SELECT SUM(oe.cantidad_unidades)
                FROM ordenes_envasado oe
                WHERE oe.produccion_id = pr.id
            ), 0)) AS cantidad_pendiente_envasar,
            CASE WHEN EXISTS (
                SELECT 1 FROM ordenes_envasado oe WHERE oe.produccion_id = pr.id
            ) THEN 'Sí' ELSE 'No' END AS envasada
        FROM producciones pr
        JOIN pedidos_produccion pp ON pr.pedido_id = pp.id
        JOIN recetas r ON pp.receta_id = r.id
        JOIN clientes c ON pp.cliente_id = c.id
        ORDER BY pr.fecha DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def generar_pdf_rotulo(nombre_producto, numero_lote, fecha_produccion, nombre_cliente):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    margin = 20 * mm
    x = margin
    y = height - margin

    c.setFont("Helvetica-Bold", 18)
    c.drawString(x, y, "RÓTULO DE PRODUCCIÓN")
    y -= 20 * mm

    c.setFont("Helvetica", 14)
    c.drawString(x, y, f"Nombre de producto: {nombre_producto}")
    y -= 15 * mm

    c.drawString(x, y, f"Número de lote: {numero_lote}")
    y -= 15 * mm

    c.drawString(x, y, f"Fecha producida: {fecha_produccion}")
    y -= 15 * mm

    c.drawString(x, y, f"Nombre cliente: {nombre_cliente}")
    y -= 15 * mm

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

def mostrar_producciones():
    st.markdown("## 📦 Producciones Realizadas")
    st.markdown("---")

    df = cargar_producciones()
    if df.empty:
        st.info("No hay producciones registradas.")
        return
    
    # --- Filtros alineados ---
    with st.expander("🔍 Filtros de búsqueda", expanded=True):
        col1, col2, col3, col4 = st.columns(4)

        clientes = sorted(df["cliente"].unique())
        recetas = sorted(df["receta"].unique())
        envasada_options = ["Todos", "Sí", "No"]
        pendiente_options = ["Todos", "Con pendiente de envasar", "Sin pendiente"]

        with col1:
            cliente_sel = st.selectbox("Cliente", ["Todos"] + clientes, key="cliente_filter")
        with col2:
            receta_sel = st.selectbox("Receta", ["Todos"] + recetas, key="receta_filter")
        with col3:
            envasada_sel = st.selectbox("Estado Envasado", envasada_options, key="envasada_filter")
        with col4:
            pendiente_sel = st.selectbox("Pendiente de Envasar", pendiente_options, key="pendiente_filter")

        fecha_min = pd.to_datetime(df["fecha"]).min()
        fecha_max = pd.to_datetime(df["fecha"]).max()
        fecha_ini, fecha_fin = st.date_input("Rango de Fecha", [fecha_min, fecha_max], key="fecha_filter")

        df_filtrado = df.copy()
        if cliente_sel != "Todos":
            df_filtrado = df_filtrado[df_filtrado["cliente"] == cliente_sel]
        if receta_sel != "Todos":
            df_filtrado = df_filtrado[df_filtrado["receta"] == receta_sel]
        if envasada_sel != "Todos":
            df_filtrado = df_filtrado[df_filtrado["envasada"] == envasada_sel]
        if pendiente_sel == "Con pendiente de envasar":
            df_filtrado = df_filtrado[df_filtrado["cantidad_pendiente_envasar"] > 0]
        elif pendiente_sel == "Sin pendiente":
            df_filtrado = df_filtrado[df_filtrado["cantidad_pendiente_envasar"] <= 0]

        df_filtrado["fecha_dt"] = pd.to_datetime(df_filtrado["fecha"])
        df_filtrado = df_filtrado[
            (df_filtrado["fecha_dt"] >= pd.to_datetime(fecha_ini)) & 
            (df_filtrado["fecha_dt"] <= pd.to_datetime(fecha_fin))
        ]

    if df_filtrado.empty:
        st.warning("⚠️ No hay producciones con esos filtros.")
        return

    # --- Selector de producción + opción "Todos" ---
    opciones = df_filtrado.apply(
        lambda r: f"ID {r['produccion_id']} | {r['receta']} | Lote: {r['lote']} | Fecha: {pd.to_datetime(r['fecha']).strftime('%d/%m/%Y')} | Cliente: {r['cliente']} | Envasada: {r['envasada']} | Pendiente: {r['cantidad_pendiente_envasar']:.2f}",
        axis=1
    ).tolist()
    opciones = ["Todos"] + opciones

    seleccion = st.selectbox("Seleccione una producción para ver detalle y opciones", opciones, key="produccion_select")

    st.divider()

    if seleccion != "Todos":
        idx = opciones.index(seleccion) - 1  # Ajuste por la opción "Todos"
        produccion = df_filtrado.iloc[idx]

        # --- Caja informativa con fondo y sombra simulada ---
        card_style = """
            <style>
                .card {
                    background-color: #f9fafb;
                    border-radius: 10px;
                    padding: 20px;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                    margin-bottom: 25px;
                }
                .card h3 {
                    margin-top: 0;
                    color: #0d6efd;
                }
                .card p {
                    font-size: 16px;
                    margin: 5px 0;
                }
            </style>
        """

        card_content = f"""
            <div class="card">
                <h3>Detalle de la producción seleccionada</h3>
                <p><b>Producto:</b> {produccion['receta']}</p>
                <p><b>Número de lote:</b> {produccion['lote']}</p>
                <p><b>Fecha producida:</b> {pd.to_datetime(produccion['fecha']).strftime('%d/%m/%Y')}</p>
                <p><b>Cliente:</b> {produccion['cliente']}</p>
                <p><b>Cantidad producida (litros):</b> {produccion['cantidad_litros']}</p>
                <p><b>Cantidad envasada (unidades):</b> {produccion['cantidad_envasada']}</p>
                <p><b>Cantidad pendiente de envasar (unidades):</b> {produccion['cantidad_pendiente_envasar']:.2f}</p>
                <p><b>Envasada:</b> {produccion['envasada']}</p>
            </div>
        """
        st.markdown(card_style + card_content, unsafe_allow_html=True)

        if st.button("🖨️ Imprimir Rótulo de esta producción", key="btn_imprimir_rotulo"):
            pdf_buffer = generar_pdf_rotulo(
                nombre_producto=produccion["receta"],
                numero_lote=produccion["lote"],
                fecha_produccion=pd.to_datetime(produccion["fecha"]).strftime("%d/%m/%Y"),
                nombre_cliente=produccion["cliente"]
            )
            st.success("✅ PDF generado. Descarga a continuación:")
            st.download_button(
                label="Descargar Rótulo PDF",
                data=pdf_buffer,
                file_name=f"rotulo_{produccion['lote']}.pdf",
                mime="application/pdf"
            )
    else:
        st.info("Seleccione una producción para ver detalle o elija 'Todos' para ver la tabla completa abajo.")

    # --- Tabla resumen ---
    with st.expander("📊 Mostrar tabla resumen de producciones filtradas", expanded=True):
        st.dataframe(
            df_filtrado.drop(columns=["fecha_dt"]).rename(columns={
                "produccion_id": "ID",
                "fecha": "Fecha",
                "lote": "Lote",
                "numero_pedido": "Número Pedido",
                "cantidad_litros": "Cantidad (litros)",
                "cliente": "Cliente",
                "receta": "Producto",
                "cantidad_envasada": "Cantidad Envasada",
                "cantidad_pendiente_envasar": "Cantidad Pendiente de Envasar",
                "envasada": "Envasada"
            }),
            use_container_width=True
        )
    
    # --- Descargar CSV ---
    csv = df_filtrado.drop(columns=["fecha_dt"]).to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Descargar CSV con producciones filtradas",
        csv,
        file_name="producciones_filtradas.csv",
        mime="text/csv"
    )

mostrar_producciones()
