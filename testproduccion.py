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

    def obtener_ingredientes_modificados_db(pedido_id):
        with sqlite3.connect("minerva.db") as conn:
            return conn.execute('''
                SELECT mp.id, mp.nombre, rm.cantidad, rm.unidad, rm.materia_prima_id
                FROM receta_modificada rm
                JOIN materias_primas mp ON rm.materia_prima_id = mp.id
                WHERE rm.pedido_id = ?
            ''', (pedido_id,)).fetchall()

    def obtener_stock():
        with sqlite3.connect("minerva.db") as conn:
            rows = conn.execute("SELECT materia_prima_id, cantidad FROM stock_materias_primas").fetchall()
            return {r[0]: {"stock": r[1]} for r in rows}

    def obtener_materias_primas():
        with sqlite3.connect("minerva.db") as conn:
            return conn.execute("SELECT id, nombre, unidad FROM materias_primas").fetchall()

    def descontar_stock(conn, ingredientes, cantidad_a_producir, cur):
        ingredientes_escala = {}
        faltantes = []
        stock = obtener_stock()

        for ingr_id, ingr_nombre, cantidad_base, unidad, materia_prima_id in ingredientes:
            cantidad_escalada = (cantidad_a_producir / 200) * cantidad_base
            ingredientes_escala[materia_prima_id] = cantidad_escalada

        for materia_prima_id, cantidad_escalada in ingredientes_escala.items():
                stock_actual = stock.get(materia_prima_id, {"stock": 0})["stock"]
                if stock_actual < cantidad_escalada:
                    cur.execute("SELECT nombre FROM materias_primas WHERE id = ?", (materia_prima_id,))
                    ingrediente_nombre = cur.fetchone()[0]
                    faltantes.append((ingrediente_nombre, cantidad_escalada, stock_actual))
                else:
                    nuevo_stock = max(stock_actual - cantidad_escalada, 0)
                    cur.execute("""
                        UPDATE stock_materias_primas SET cantidad = ? WHERE materia_prima_id = ?
                    """, (nuevo_stock, materia_prima_id))

        if faltantes:
            return faltantes
        return None

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

    if 'current_selections' not in st.session_state:
        st.session_state.current_selections = []

    pedidos = obtener_pedidos()
    if not pedidos:
        st.info("ℹ️ No hay pedidos pendientes ni en proceso.")
        st.stop()

    pedido_labels = [f"{p[1]} - {p[2]} - {p[4]} - Estado: {p[6].capitalize()}" for p in pedidos]

    st.multiselect("Seleccionar pedido",
                    pedido_labels,
                    default=st.session_state.current_selections,
                    key="multiselect_key",
                    on_change=handle_multiselect_change)

    for i, seleccion in enumerate(st.session_state.current_selections):
        try:
            pedido = pedidos[pedido_labels.index(seleccion)]
            pedido_id, cliente, receta, cantidad, numero_pedido, fecha, estado, receta_id, lote, cliente_id = pedido

            lote_gen = generar_numero_lote()
            # FIX: Mover la inicialización de 'stock' aquí para que esté disponible para todo el bloque
            stock = obtener_stock()

            ingredientes_modificados = obtener_ingredientes_modificados_db(pedido_id)
            if ingredientes_modificados:
                ingredientes_raw = ingredientes_modificados
            else:
                ingredientes_raw = obtener_ingredientes(receta_id)

            factor = cantidad / 200
            ingredientes = [(i[1], i[2]*factor, i[3]) for i in ingredientes_raw]
            ingr_dict = {i[4]: i[2]*factor for i in ingredientes_raw}

            materias_primas = obtener_materias_primas()
            materias_primas_dict = {mp[0]: mp[1] for mp in materias_primas}
            materias_primas_labels = {mp[0]: f"{mp[1]} ({mp[2]})" for mp in materias_primas}

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

                with st.form(key=f"form_ingredientes_{pedido_id}"):
                    st.markdown("#### ✏️ Editar Ingredientes")
                    modificaciones = {}
                    for ingr_id, ingr_nombre, cantidad_base, unidad, materia_prima_id in ingredientes_raw:
                        col_ingr1, col_ingr2, col_ingr3 = st.columns(3)

                        with col_ingr1:
                            nueva_materia_prima_id = st.selectbox(
                                f"MP - {ingr_nombre} ({unidad})",
                                options=materias_primas_labels.keys(),
                                format_func=lambda x: materias_primas_labels[x],
                                index=list(materias_primas_labels.keys()).index(materia_prima_id),
                                key=f"materia_prima_{pedido_id}_{ingr_id}"
                            )
                        with col_ingr2:
                            nueva_cantidad = st.number_input(
                                "Cantidad",
                                value=float(cantidad_base),
                                format="%.3f",
                                key=f"cantidad_{pedido_id}_{ingr_id}"
                            )
                        with col_ingr3:
                            nueva_unidad = st.text_input(
                                "Unidad",
                                value=unidad,
                                key=f"unidad_{pedido_id}_{ingr_id}"
                            )

                        modificaciones[ingr_id] = {
                            'materia_prima_id': nueva_materia_prima_id,
                            'materia_prima_nombre': materias_primas_dict[nueva_materia_prima_id],
                            'cantidad': nueva_cantidad,
                            'unidad': nueva_unidad
                        }

                    if st.form_submit_button("Guardar cambios en ingredientes"):
                        with sqlite3.connect("minerva.db") as conn:
                            cur = conn.cursor()
                            try:
                                conn.execute("BEGIN")
                                cur.execute("DELETE FROM receta_modificada WHERE pedido_id = ?", (pedido_id,))
                                for ingr_id, mod in modificaciones.items():
                                    cur.execute("""
                                        INSERT INTO receta_modificada (pedido_id, receta_id, materia_prima_id, cantidad, unidad)
                                        VALUES (?, ?, ?, ?, ?)
                                    """, (pedido_id, receta_id, mod['materia_prima_id'], mod['cantidad'], mod['unidad']))
                                conn.commit()
                                st.success("✅ Cambios en ingredientes guardados en la base de datos.")
                                st.rerun()
                            except sqlite3.Error as e:
                                conn.rollback()
                                st.error(f"Ocurrió un error al guardar los cambios: {e}")

                factor = cantidad / 200
                ingredientes_mostrar = [(materias_primas_dict.get(i[4], "N/A"), i[2]*factor, i[3]) for i in ingredientes_raw]
                st.dataframe(pd.DataFrame(ingredientes_mostrar, columns=["Ingrediente", "Cantidad", "Unidad"])
                                .style.format({"Cantidad": "{:.3f}"}), use_container_width=True)

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
                            ingredientes_simulacion = obtener_ingredientes_modificados_db(pedido_id)
                            if not ingredientes_simulacion:
                                ingredientes_simulacion = obtener_ingredientes(receta_id)

                            for ingr_id, ingr_nombre, cantidad_base, unidad, materia_prima_id in ingredientes_simulacion:
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
                                st.session_state.current_selections.remove(seleccion)
                                st.rerun()
                            except sqlite3.Error as e:
                                conn.rollback()
                                st.error(f"Ocurrió un error al confirmar la producción: {e}")

            elif estado == "en_proceso":
                st.subheader("⚙️ Opciones para estado En Proceso")
                cantidad_real = st.number_input("Cantidad real producida (litros):", min_value=0.0, value=float(cantidad), step=0.01, key=f"cantidad_real_{pedido_id}")
                opcion = st.selectbox("Operación:", ["Simular descontando stock y mostrar faltantes", "Producir descontando stock"], key=f"opcion_en_proceso_{pedido_id}")
                if st.button(f"Ejecutar operación para {numero_pedido}", key=f"button_en_proceso_{pedido_id}"):
                    with sqlite3.connect("minerva.db") as conn:
                        cur = conn.cursor()
                        fecha_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        try:
                            conn.execute("BEGIN")

                            ingredientes_finales = obtener_ingredientes_modificados_db(pedido_id)
                            if not ingredientes_finales:
                                ingredientes_finales = obtener_ingredientes(receta_id)

                            ingredientes_escala = {}
                            for ingr_id, ingr_nombre, cantidad_base, unidad, materia_prima_id in ingredientes_finales:
                                cantidad_escalada = (cantidad / 200) * cantidad_base
                                ingredientes_escala[materia_prima_id] = cantidad_escalada

                            if opcion == "Simular descontando stock y mostrar faltantes":
                                # La función descontar_stock ya se encarga de obtener el stock internamente
                                faltantes = descontar_stock(conn, ingredientes_finales, cantidad, cur)
                                if faltantes:
                                    st.warning("⚠️ Ingredientes faltantes:")
                                    for nombre, req, disp in faltantes:
                                        st.write(f"- {nombre}: requiere {req:.3f}, disponible {disp:.3f}")
                                conn.rollback()
                            elif opcion == "Producir descontando stock":
                                faltantes = descontar_stock(conn, ingredientes_finales, cantidad, cur)
                                if faltantes:
                                    st.warning("⚠️ No se puede completar la producción debido a ingredientes faltantes:")
                                    for nombre, req, disp in faltantes:
                                        st.write(f"- {nombre}: requiere {req:.3f}, disponible {disp:.3f}")
                                    conn.rollback()
                                    st.stop()

                                for materia_prima_id, cantidad_ingrediente in ingredientes_escala.items():
                                    cur.execute("""
                                        INSERT INTO movimientos_materia_prima
                                        (materia_prima_id, fecha, cantidad, tipo_movimiento, destino, lote)
                                        VALUES (?, ?, ?, 'egreso', 'produccion', ?)
                                    """, (materia_prima_id, fecha_now, -cantidad_ingrediente, lote_gen))
                                
                                cur.execute("""
                                    INSERT OR IGNORE INTO lotes (numero, fecha, cliente_id, receta_id)
                                    VALUES (?, ?, ?, ?)
                                """, (lote, fecha_now.split()[0], cliente_id, receta_id))
                                cur.execute("""
                                    INSERT INTO producciones (pedido_id, fecha, lote, estado, cantidad_litros, litros_envasados, cantidad_real_litros)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (pedido_id, fecha_now, lote, 'producido', cantidad, 0, cantidad_real))
                                cur.execute("UPDATE pedidos_produccion SET estado = 'producido' WHERE id = ?", (pedido_id,))

                                cur.execute("DELETE FROM receta_modificada WHERE pedido_id = ?", (pedido_id,))
                                
                                conn.commit()
                                st.success(f"✅ Producción registrada. Lote: {lote} - Cantidad real: {cantidad_real} litros")
                                if seleccion in st.session_state.current_selections:
                                    st.session_state.current_selections.remove(seleccion)
                                st.rerun()

                        except sqlite3.Error as e:
                            conn.rollback()
                            st.error(f"Ocurrió un error al registrar la producción: {e}")
            else:
                st.info("ℹ️ Este pedido no está en estado pendiente ni en proceso.")
        except ValueError:
            st.warning(f"El pedido '{seleccion}' ya no está disponible.")
            if seleccion in st.session_state.current_selections:
                st.session_state.current_selections.remove(seleccion)
            st.rerun()

gestionar_produccion()