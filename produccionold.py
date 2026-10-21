import streamlit as st
import sqlite3
from datetime import datetime
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
        return f"Lote-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

    def obtener_pedidos():
        with sqlite3.connect("minerva.db") as conn:
            return conn.execute('''
                SELECT pp.id, c.nombre, r.nombre, pp.cantidad, pp.numero_pedido, pp.fecha, pp.estado, pp.receta_id, pp.lote, pp.cliente_id
                FROM pedidos_produccion pp
                JOIN clientes c ON pp.cliente_id = c.id
                JOIN recetas r ON pp.receta_id = r.id
                WHERE pp.estado IN ('pendiente', 'en_proceso')
                ORDER BY pp.fecha
            ''').fetchall()

    def obtener_ingredientes(receta_id):
        with sqlite3.connect("minerva.db") as conn:
            return conn.execute('''
                SELECT mp.id, mp.nombre, ri.cantidad, ri.unidad, ri.materia_prima_id
                FROM receta_ingredientes ri
                JOIN materias_primas mp ON ri.materia_prima_id = mp.id
                WHERE ri.receta_id = ?
            ''', (receta_id,)).fetchall()

    def obtener_stock():
        with sqlite3.connect("minerva.db") as conn:
            rows = conn.execute("SELECT materia_prima_id, cantidad FROM stock_materias_primas").fetchall()
            return {r[0]: {"stock": r[1]} for r in rows}

    def obtener_composicion_colorante(conn, colorante_combinado_id):
        """Obtiene la composición de un colorante combinado desde la base de datos."""
        cur = conn.cursor()
        cur.execute("""
            SELECT colorante_primario_id, proporcion
            FROM composicion_colorantes
            WHERE colorante_combinado_id = ?
        """, (colorante_combinado_id,))
        return cur.fetchall()

    def descontar_stock(conn, receta_id, cantidad_a_producir, cur):
        """Descuenta el stock de materias primas, incluyendo los colorantes combinados."""
        cur.execute("""
            SELECT mp.id, mp.nombre, ri.cantidad, ri.unidad, ri.materia_prima_id
            FROM receta_ingredientes ri
            JOIN materias_primas mp ON ri.materia_prima_id = mp.id
            WHERE ri.receta_id = ?
        """, (receta_id,))
        ingredientes = cur.fetchall()

        ingredientes_escala = {}
        faltantes = []
        stock = obtener_stock() # Obtener stock actualizado

        for ingr_id, ingr_nombre, cantidad_base, unidad, materia_prima_id in ingredientes:
            cantidad_escalada = (cantidad_a_producir / 200) * cantidad_base
            ingredientes_escala[materia_prima_id] = cantidad_escalada

        # Descontar del stock
        for materia_prima_id, cantidad_escalada in ingredientes_escala.items():
            # Primero, verificar si el ingrediente es un colorante combinado
            cur.execute("""
                SELECT 1 FROM composicion_colorantes WHERE colorante_combinado_id = ?
            """, (materia_prima_id,))
            es_colorante_combinado = cur.fetchone() is not None

            if es_colorante_combinado:
                # Si es un colorante combinado, obtener su composición
                composicion = obtener_composicion_colorante(conn, materia_prima_id)
                if composicion:
                    for componente_id, proporcion in composicion:
                        # Calcular la cantidad del componente a descontar
                        cantidad_componente = cantidad_escalada * proporcion

                        # Validar stock del componente
                        stock_componente = stock.get(componente_id, {"stock": 0})["stock"]
                        if stock_componente < cantidad_componente:
                            # Si no hay suficiente stock, agregar a la lista de faltantes
                            cur.execute("SELECT nombre FROM materias_primas WHERE id = ?", (componente_id,))
                            ingrediente_nombre = cur.fetchone()[0]
                            faltantes.append((ingrediente_nombre, cantidad_componente, stock_componente))
                        else:
                            # Si hay suficiente stock, descontar del stock
                            nuevo_stock = max(stock_componente - cantidad_componente, 0)
                            cur.execute("""
                                UPDATE stock_materias_primas SET cantidad = ? WHERE materia_prima_id = ?
                            """, (nuevo_stock, componente_id))
                else:
                    st.warning(f"No se encontró la composición del colorante combinado con ID: {materia_prima_id}. Se omitirá el descuento de stock para este colorante.")
            else:
                # Si no es un colorante combinado, descontar directamente del stock
                stock_actual = stock.get(materia_prima_id, {"stock": 0})["stock"]
                if stock_actual < cantidad_escalada:
                    # Si no hay suficiente stock, agregar a la lista de faltantes
                    cur.execute("SELECT nombre FROM materias_primas WHERE id = ?", (materia_prima_id,))
                    ingrediente_nombre = cur.fetchone()[0]
                    faltantes.append((ingrediente_nombre, cantidad_escalada, stock_actual))
                else:
                    # Si hay suficiente stock, descontar del stock
                    nuevo_stock = max(stock_actual - cantidad_escalada, 0)
                    cur.execute("""
                        UPDATE stock_materias_primas SET cantidad = ? WHERE materia_prima_id = ?
                    """, (nuevo_stock, materia_prima_id))

        if faltantes:
            return faltantes
        return None # Indicar que no hay faltantes

    def generar_pdf_receta(cliente, receta, cantidad, numero_pedido, fecha_pedido, lote, ingredientes):
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        width, height = letter
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, height - 50, f"Receta de Producción - {receta}")
        c.setFont("Helvetica", 12)
        y = height - 80
        for txt in [f"Cliente: {cliente}", f"Pedido: {numero_pedido}", f"Fecha pedido: {fecha_pedido}", f"Cantidad: {cantidad} litros", f"Lote: {lote or 'No asignado'}"]:
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

    def imprimir_rotulo(cliente, receta, lote):
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        height = letter[1]
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 100, f"Producto: {receta}")
        c.drawString(50, height - 130, f"Número de Lote: {lote}")
        c.drawString(50, height - 160, f"Fecha producida: {datetime.now().strftime('%Y-%m-%d')}")
        c.drawString(50, height - 190, f"Cliente: {cliente}")
        c.showPage()
        c.save()
        buf.seek(0)
        return buf

    # --- Lógica de la interfaz ---

    def handle_multiselect_change():
        """Callback para guardar la selección en el estado de la sesión."""
        st.session_state.current_selections = st.session_state.multiselect_key

    # Inicializar el estado de la sesión si no existe
    if 'current_selections' not in st.session_state:
        st.session_state.current_selections = []

    pedidos = obtener_pedidos()
    if not pedidos:
        st.info("ℹ️ No hay pedidos pendientes ni en proceso.")
        #st.stop()

    pedido_labels = [f"{p[1]} - {p[2]} - {p[4]} - Estado: {p[6].capitalize()}" for p in pedidos]

    # Usar el estado de la sesión para mantener la selección
    st.multiselect("Seleccionar pedido",
                    pedido_labels,
                    default=st.session_state.current_selections,
                    key="multiselect_key",
                    on_change=handle_multiselect_change)

    # El bucle ahora opera sobre los pedidos almacenados en la sesión
    for i, seleccion in enumerate(st.session_state.current_selections):
        try:
            pedido = pedidos[pedido_labels.index(seleccion)]
            pedido_id, cliente, receta, cantidad, numero_pedido, fecha, estado, receta_id, lote, cliente_id = pedido

            # Generar un número de lote ÚNICO para cada pedido
            lote_gen = generar_numero_lote()

            ingredientes_raw = obtener_ingredientes(receta_id)
            factor = cantidad / 200
            ingredientes = [(i[1], i[2]*factor, i[3]) for i in ingredientes_raw]
            ingr_dict = {i[4]: i[2]*factor for i in ingredientes_raw}

            col1, col2 = st.columns([2,3])
            with col1:
                st.markdown("### 🧾 Información del Pedido")
                st.write(f"**Cliente:** {cliente}")
                st.write(f"**Receta:** {receta}")
                st.write(f"**Cantidad:** {cantidad} litros")
                st.write(f"**N° Pedido:** {numero_pedido}")
                st.write(f"**Fecha:** {fecha}")
                st.write(f"**Estado:** `{estado}`")
                st.write(f"**Nuevo Lote:** `{lote_gen}`")
            with col2:
                st.markdown("### 🧪 Ingredientes Escalados")
                st.dataframe(pd.DataFrame(ingredientes, columns=["Ingrediente", "Cantidad", "Unidad"])
                                .style.format({"Cantidad": "{:.3f}"}), use_container_width=True)

            stock = obtener_stock()
            colA, colB = st.columns(2)
            with colA:
                st.download_button(label=f"📄 Descargar receta PDF - {numero_pedido}", data=generar_pdf_receta(cliente, receta, cantidad, numero_pedido, fecha, lote_gen, ingredientes),
                                    file_name=f"receta_{numero_pedido}_{lote_gen or 'sin_lote'}.pdf", mime="application/pdf")
            with colB:
                if lote_gen:
                    st.download_button(label=f"🏷️ Imprimir rótulo - {numero_pedido}", data=imprimir_rotulo(cliente, receta, lote_gen),
                                         file_name=f"rotulo_{numero_pedido}_{lote_gen}.pdf", mime="application/pdf")

            st.markdown("---")

            if estado == "pendiente":
                st.subheader("⚙️ Opciones para estado Pendiente")
                opcion = st.selectbox(f"Operación para {numero_pedido}:", ["Simular sin descontar stock", "Simular descontando y mostrar faltantes", "Confirmar producción"], key=f"opcion_{pedido_id}")
                if st.button(f"Ejecutar operación para {numero_pedido}", key=f"button_{pedido_id}"):
                    if opcion.startswith("Simular"):
                        with sqlite3.connect("minerva.db") as conn:
                            cur = conn.cursor()
                            faltantes = []
                            for ingr_id, ingr_nombre, cantidad_base, unidad, materia_prima_id in obtener_ingredientes(receta_id):
                                cantidad_escalada = (cantidad / 200) * cantidad_base
                                stock_actual = stock.get(materia_prima_id, {"stock": 0})["stock"]
                                if stock_actual < cantidad_escalada:
                                    faltantes.append((ingr_nombre, cantidad_escalada, stock_actual))

                        if faltantes:
                            st.warning("⚠️ Ingredientes faltantes:")
                            for nombre, req, disp in faltantes:
                                st.write(f"- {nombre}: requiere {req:.3f}, disponible {disp:.3f}")
                        else:
                            st.success("✅ Suficiente stock disponible.")
                    elif opcion == "Confirmar producción":
                        with sqlite3.connect("minerva.db") as conn:
                            cur = conn.cursor()
                            try:
                                conn.execute("BEGIN")
                                conn.execute("""
                                    INSERT OR IGNORE INTO lotes (numero, fecha, cliente_id, receta_id)
                                    VALUES (?, ?, ?, ?)
                                """, (lote_gen, datetime.now().strftime("%Y-%m-%d"), cliente_id, receta_id))
                                conn.execute("UPDATE pedidos_produccion SET estado = 'en_proceso', lote = ? WHERE id = ?", (lote_gen, pedido_id))
                                conn.commit()
                                st.success(f"✅ Pedido en proceso. Lote: {lote_gen}")
                                # Eliminar el pedido procesado de la lista en session_state
                                st.session_state.current_selections.remove(seleccion)
                                st.rerun() # Fuerza la recarga de la página
                            except sqlite3.Error as e:
                                conn.rollback()
                                st.error(f"Ocurrió un error al confirmar la producción: {e}")

            elif estado == "en_proceso":
                st.subheader("⚙️ Opciones para estado En Proceso")
                cantidad_real = st.number_input("Cantidad real producida (litros):", min_value=0.0, value=float(cantidad), step=0.01, key=f"cantidad_real_{pedido_id}")
                opcion = st.selectbox("Operación:", ["Simular descontando stock y mostrar faltantes", "Producir descontando stock"], key=f"opcion_en_proceso_{pedido_id}")
                if st.button(f"Ejecutar operación para {numero_pedido}", key=f"button_en_proceso_{pedido_id}"):
                    if opcion == "Simular descontando stock y mostrar faltantes":
                        with sqlite3.connect("minerva.db") as conn:
                            cur = conn.cursor()
                            # Simular el descuento y verificar faltantes sin persistir cambios
                            faltantes = descontar_stock(conn, receta_id, cantidad, cur)
                            if faltantes:
                                st.warning("⚠️ Ingredientes faltantes:")
                                for nombre, req, disp in faltantes:
                                    st.write(f"- {nombre}: requiere {req:.3f}, disponible {disp:.3f}")
                                conn.rollback() # Deshacer los cambios de la simulación
                            else:
                                st.success("✅ Suficiente stock disponible para la producción.")

                    elif opcion == "Producir descontando stock":
                        with sqlite3.connect("minerva.db") as conn:
                            cur = conn.cursor()
                            try:
                                conn.execute("BEGIN")
                                fecha_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                                # Descontar stock
                                faltantes = descontar_stock(conn, receta_id, cantidad, cur)
                                if faltantes:
                                    st.warning("⚠️ No se puede completar la producción debido a ingredientes faltantes:")
                                    for nombre, req, disp in faltantes:
                                        st.write(f"- {nombre}: requiere {req:.3f}, disponible {disp:.3f}")
                                    conn.rollback()
                                    st.stop()

                                # Insertar movimientos de materia prima
                                for materia_prima_id, cantidad_ingrediente in ingr_dict.items():
                                    cur.execute("""
                                        INSERT INTO movimientos_materia_prima
                                        (materia_prima_id, fecha, cantidad, tipo_movimiento, destino, lote)
                                        VALUES (?, ?, ?, 'egreso', 'produccion', ?)
                                    """, (materia_prima_id, fecha_now, -cantidad_ingrediente, lote_gen))
                                # Actualizar la tabla de lotes (por si no se insertó antes)
                                cur.execute("""
                                    INSERT OR IGNORE INTO lotes (numero, fecha, cliente_id, receta_id)
                                    VALUES (?, ?, ?, ?)
                                """, (lote, fecha_now.split()[0], cliente_id, receta_id))
                                cur.execute("""
                                    INSERT INTO producciones (pedido_id, fecha, lote, estado, cantidad_litros, litros_envasados, cantidad_real_litros)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (pedido_id, fecha_now, lote, 'producido', cantidad, 0, cantidad_real))
                                cur.execute("UPDATE pedidos_produccion SET estado = 'producido' WHERE id = ?", (pedido_id,))
                                conn.commit()
                                st.success(f"✅ Producción registrada. Lote: {lote} - Cantidad real: {cantidad_real} litros")
                                # Eliminar el pedido procesado de la lista en session_state
                                if seleccion in st.session_state.current_selections:
                                    st.session_state.current_selections.remove(seleccion)
                                st.rerun()  # Fuerza la recarga de la página
                            except sqlite3.Error as e:
                                conn.rollback()
                                st.error(f"Ocurrió un error al registrar la producción: {e}")
            else:
                st.info("ℹ️ Este pedido no está en estado pendiente ni en proceso.")
        except ValueError:
            # Manejar el caso de que el pedido ya no esté en la lista original
            # Esto puede pasar si un pedido se procesa en otra pestaña, por ejemplo
            st.warning(f"El pedido '{seleccion}' ya no está disponible.")
            if seleccion in st.session_state.current_selections:
                st.session_state.current_selections.remove(seleccion)
            st.rerun()


