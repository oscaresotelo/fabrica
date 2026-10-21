import streamlit as st
import sqlite3
import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

def mostrar_stock_sin_envasar():
    # --- Control de acceso (opcional, puedes quitar si ya lo haces en app.py) ---
    if "usuario" not in st.session_state:
        st.error("❌ Acceso denegado. Inicie sesión.")
        st.stop()

    st.markdown("## 📦 Stock de Productos Realizados Sin Envasar")
    st.markdown("---")

    conn = sqlite3.connect("minerva.db")
    # --- Consulta SQL Modificada para usar las columnas de la tabla producciones ---
    query = """
        SELECT 
            pr.id AS produccion_id,
            pr.fecha,
            pr.lote,
            pp.numero_pedido,
            pr.cantidad_real_litros AS cantidad_litros, -- Cantidad total producida
            c.nombre AS cliente,
            r.nombre AS receta,
            pr.litros_envasados AS cantidad_envasada, -- Cantidad ya envasada
            (pr.cantidad_real_litros - pr.litros_envasados) AS cantidad_pendiente_envasar -- ¡La nueva lógica!
        FROM producciones pr
        JOIN pedidos_produccion pp ON pr.pedido_id = pp.id
        JOIN recetas r ON pp.receta_id = r.id
        JOIN clientes c ON pp.cliente_id = c.id
        WHERE 
            pr.estado = 'producido' 
            -- Filtramos directamente en el WHERE para mostrar solo lo pendiente
            AND pr.cantidad_real_litros > pr.litros_envasados 
        ORDER BY pr.fecha DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        st.info("No hay productos realizados sin envasar.")
        return

    # Filtros
    with st.expander("🔍 Filtros de búsqueda", expanded=True):
        clientes = sorted(df["cliente"].unique())
        recetas = sorted(df["receta"].unique())
        col1, col2 = st.columns(2)
        with col1:
            cliente_sel = st.selectbox("Cliente", ["Todos"] + clientes)
        with col2:
            receta_sel = st.selectbox("Receta", ["Todos"] + recetas)
        df_filtrado = df.copy()
        if cliente_sel != "Todos":
            df_filtrado = df_filtrado[df_filtrado["cliente"] == cliente_sel]
        if receta_sel != "Todos":
            df_filtrado = df_filtrado[df_filtrado["receta"] == receta_sel]

    if df_filtrado.empty:
        st.warning("⚠️ No hay resultados con esos filtros.")
        return

    st.dataframe(df_filtrado, use_container_width=True)

    # Descargar CSV
    csv = df_filtrado.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Descargar CSV",
        csv,
        file_name="stock_sin_envasar.csv",
        mime="text/csv"
    )

    # Generar rótulo PDF para una producción seleccionada
    opciones = df_filtrado.apply(
        lambda r: f"ID {r['produccion_id']} | {r['receta']} | Lote: {r['lote']} | Cliente: {r['cliente']}", axis=1
    ).tolist()
    opciones = ["Ninguno"] + opciones
    seleccion = st.selectbox("Seleccione una producción para imprimir rótulo", opciones)
    if seleccion != "Ninguno":
        idx = opciones.index(seleccion) - 1
        prod = df_filtrado.iloc[idx]
        if st.button("🖨️ Imprimir Rótulo PDF"):
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
            c.drawString(x, y, f"Nombre de producto: {prod['receta']}")
            y -= 15 * mm
            c.drawString(x, y, f"Número de lote: {prod['lote']}")
            y -= 15 * mm
            c.drawString(x, y, f"Fecha producida: {prod['fecha']}")
            y -= 15 * mm
            c.drawString(x, y, f"Nombre cliente: {prod['cliente']}")
            y -= 15 * mm
            c.showPage()
            c.save()
            buffer.seek(0)
            st.success("✅ PDF generado. Descarga a continuación:")
            st.download_button(
                label="Descargar Rótulo PDF",
                data=buffer,
                file_name=f"rotulo_{prod['lote']}.pdf",
                mime="application/pdf"
            )

# Ejecutar la función principal
if __name__ == "__main__":
    mostrar_stock_sin_envasar()