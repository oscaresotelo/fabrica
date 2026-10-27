# ordenes_compra.py

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from utils_pdf import generar_pdf_bytes, generar_pdf_remito_transporte

DB_PATH = "minerva.db"

def conectar_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def obtener_datos_mapeados(tabla):
    with conectar_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT id, nombre FROM {tabla}")
        resultados = cursor.fetchall()
        datos = [{'id': r['id'], 'nombre': r['nombre']} for r in resultados]
        map_nombre_a_id = {item['nombre']: item['id'] for item in datos}
        map_id_a_nombre = {item['id']: item['nombre'] for item in datos}
        return datos, map_nombre_a_id, map_id_a_nombre

def fetch_data(query, params=()):
    conn = None 
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(query, conn, params=params)
        return df
    except sqlite3.Error as e:
        st.error(f"Error al ejecutar la consulta: {e}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def obtener_ultimo_precio_materia_prima(materia_prima_id):
    with conectar_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT precio_unitario
            FROM compras_materia_prima
            WHERE materia_prima_id = ?
            ORDER BY fecha DESC, id DESC
            LIMIT 1
        """, (materia_prima_id,))
        resultado = cursor.fetchone()
        return resultado["precio_unitario"] if resultado else None

def crear_orden_compra(proveedor_id, fecha_orden, fecha_entrega, detalles):
    conn = None 
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ordenes_de_compra (proveedor_id, fecha_orden, fecha_entrega, estado)
            VALUES (?, ?, ?, ?)
        """, (proveedor_id, fecha_orden.strftime('%Y-%m-%d'), fecha_entrega.strftime('%Y-%m-%d'), 'pendiente'))
        orden_compra_id = cursor.lastrowid

        for detalle in detalles:
            cursor.execute("""
                INSERT INTO detalle_orden_compra (orden_compra_id, materia_prima_id, cantidad, precio_unitario)
                VALUES (?, ?, ?, ?)
            """, (orden_compra_id, detalle['materia_prima_id'], detalle['cantidad'], detalle['precio_unitario']))

        conn.commit()
        st.success(f"✅ ¡Orden de compra No. **{orden_compra_id}** creada exitosamente!")
        return True
    except sqlite3.Error as e:
        st.error(f"❌ Error al crear la orden de compra: {e}")
        if conn:
            conn.rollback() 
        return False
    finally:
        if conn:
            conn.close()

def anular_orden_compra(orden_id):
    conn = None
    try:
        conn = conectar_db()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE ordenes_de_compra
            SET estado = 'anulada'
            WHERE id = ? AND estado = 'pendiente'
        """, (orden_id,))
        
        if cursor.rowcount > 0:
            conn.commit()
            st.success(f"🗑️ Orden de compra No. **{orden_id}** anulada correctamente.")
            return True
        else:
            st.warning(f"⚠️ La Orden No. {orden_id} no pudo ser anulada.")
            return False
    except sqlite3.Error as e:
        st.error(f"❌ Error al anular la orden de compra {orden_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def inicializar_session_state_oc():
    if 'orden_items' not in st.session_state:
        st.session_state.orden_items = [{
            'materia_prima_nombre': None,
            'cantidad': 1.0,
            'precio_unitario': 0.01
        }]

def agregar_item_vacio():
    st.session_state.orden_items.append({
        'materia_prima_nombre': None,
        'cantidad': 1.0, 
        'precio_unitario': 0.01
    })

def eliminar_item(index):
    if 0 <= index < len(st.session_state.orden_items):
        st.session_state.orden_items.pop(index)

def agregar_orden_compra(proveedores_map, materias_map):
    st.markdown("### 📝 Nueva Orden de Compra")
    proveedores_nombres = list(proveedores_map['nombre_a_id'].keys())
    materias_nombres = list(materias_map['nombre_a_id'].keys())
    
    if st.button("➕ Agregar otro item", type="secondary", use_container_width=True, key="add_item_btn_top"):
        agregar_item_vacio()
        st.rerun()

    st.markdown("---")
    with st.container(border=True):
        st.subheader("Datos de Encabezado")
        with st.form("nueva_orden_mod", clear_on_submit=False): 
            col1, col2 = st.columns(2)
            with col1:
                proveedor_nombre = st.selectbox("Proveedor", proveedores_nombres, index=None, placeholder="Seleccione un proveedor...")
            with col2:
                fecha_orden = st.date_input("Fecha de Orden", datetime.now().date())

            fecha_entrega = st.date_input("Fecha de Entrega (Estimada)", datetime.now().date() + timedelta(days=7))
            st.text_input("🚛 Transporte", placeholder="Nombre de la empresa o transportista...", key="transporte_nuevo")

            st.divider()
            st.subheader("Detalles de la Orden")

            for i, item in enumerate(st.session_state.orden_items):
                with st.container(border=True):
                    cols = st.columns([0.4, 0.3, 0.3])
                    try:
                        current_mp_index = materias_nombres.index(item['materia_prima_nombre']) if item['materia_prima_nombre'] else None
                    except ValueError:
                        current_mp_index = None

                    with cols[0]:
                        materia_seleccionada = cols[0].selectbox(f"Materia Prima #{i+1}", materias_nombres, key=f"mp_name_{i}", index=current_mp_index, placeholder="Seleccione...")
                        st.session_state.orden_items[i]['materia_prima_nombre'] = materia_seleccionada
                        if materia_seleccionada:
                            materia_id = materias_map['nombre_a_id'].get(materia_seleccionada)
                            ultimo_precio = obtener_ultimo_precio_materia_prima(materia_id)
                            if item['precio_unitario'] == 0.01 and ultimo_precio is not None:
                                st.session_state[f"precio_{i}"] = float(ultimo_precio)

                    with cols[1]:
                        cantidad_valor = cols[1].number_input(f"Cantidad", min_value=0.01, step=0.1, key=f"cant_{i}", value=item['cantidad'])
                        st.session_state.orden_items[i]['cantidad'] = cantidad_valor

                    with cols[2]:
                        precio_actual = item.get('precio_unitario', 0.01)
                        if precio_actual is None or precio_actual <= 0:
                            precio_actual = 0.01
                        precio_input = cols[2].number_input(f"P. Unitario ($)", min_value=0.01, value=float(precio_actual), step=0.01, format="%.2f", key=f"precio_{i}")
                        st.session_state.orden_items[i]['precio_unitario'] = precio_input

            guardar = st.form_submit_button("💾 Guardar Orden de Compra", type="primary", use_container_width=True)
            
    if st.session_state.orden_items:
        st.subheader("Eliminar Ítems")
        for i, item in enumerate(st.session_state.orden_items):
            mp_nombre = item['materia_prima_nombre'] or f"Item #{i+1} (Vacío)"
            col1, col2 = st.columns([0.8, 0.2])
            with col1:
                st.write(f"• {mp_nombre}")
            with col2:
                if st.button("🗑️ Eliminar", key=f"del_item_{i}", use_container_width=True):
                    eliminar_item(i)
                    st.rerun()

    if guardar: 
        if not proveedor_nombre:
            st.error("❌ Por favor, seleccione un proveedor.")
            return

        detalles_a_guardar = []
        items_validos = [item for item in st.session_state.orden_items if item['materia_prima_nombre'] is not None]
        if not items_validos:
            st.error("❌ La orden de compra debe tener al menos un item válido.")
            return
            
        for item in items_validos:
            materia_prima_id = materias_map['nombre_a_id'].get(item['materia_prima_nombre'])
            detalles_a_guardar.append({
                'materia_prima_id': materia_prima_id,
                'cantidad': item['cantidad'],
                'precio_unitario': item['precio_unitario']
            })

        proveedor_id = proveedores_map['nombre_a_id'][proveedor_nombre]
        if crear_orden_compra(proveedor_id, fecha_orden, fecha_entrega, detalles_a_guardar):
            st.session_state.orden_items = []
            st.rerun()

def listar_ordenes_compra():
    st.markdown("### 📋 Órdenes de Compra Emitidas")
    with st.expander("Filtros de Búsqueda"):
        col1, col2, col3 = st.columns(3)
        default_start_date = datetime.now().date() - timedelta(days=30)
        with col1:
            fecha_inicio = st.date_input("📅 Fecha de Inicio", default_start_date, key="f_inicio_oc")
        with col2:
            fecha_fin = st.date_input("📅 Fecha de Fin", datetime.now().date(), key="f_fin_oc")
        with col3:
            estado_filtro = st.selectbox("Estado", ['Todos', 'pendiente', 'anulada'], index=0, key="estado_oc_filtro")

    query = f"""
    SELECT oc.id AS ID, p.nombre AS Proveedor, oc.fecha_orden AS Fecha, oc.fecha_entrega AS Entrega, oc.estado AS Estado, SUM(doc.cantidad * doc.precio_unitario) AS Total
    FROM ordenes_de_compra oc
    JOIN proveedores p ON oc.proveedor_id = p.id
    JOIN detalle_orden_compra doc ON oc.id = doc.orden_compra_id
    WHERE oc.fecha_orden BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
    """
    if estado_filtro != 'Todos':
        query += f" AND oc.estado = '{estado_filtro}'"
    query += " GROUP BY oc.id ORDER BY oc.fecha_orden DESC"

    df = fetch_data(query)

    if not df.empty:
        st.subheader("🔍 Detalle de la Orden")
        ids_disponibles = df['ID'].tolist()
        orden_seleccionada = st.selectbox("Seleccione un ID de orden para ver su contenido:", ids_disponibles, key="sel_id_oc_detalle")
        
        if orden_seleccionada:
            query_detalle = """
            SELECT mp.nombre AS 'Materia Prima', doc.cantidad AS Cantidad, doc.precio_unitario AS 'Precio Unitario', (doc.cantidad * doc.precio_unitario) AS Subtotal
            FROM detalle_orden_compra doc JOIN materias_primas mp ON doc.materia_prima_id = mp.id
            WHERE doc.orden_compra_id = ?
            """
            df_detalle = fetch_data(query_detalle, params=(int(orden_seleccionada),))
            st.table(df_detalle)
            datos_orden = df[df['ID'] == orden_seleccionada].iloc[0].to_dict()

            key_transporte = f"transporte_confirmado_{orden_seleccionada}"
            if key_transporte not in st.session_state:
                st.session_state[key_transporte] = ""

            with st.container(border=True):
                st.markdown("##### 📄 Generar PDFs")
                transporte_input = st.text_input("🚛 Transporte", value=st.session_state[key_transporte], placeholder="Nombre del transportista...", key=f"transporte_input_{orden_seleccionada}")

                if st.button("✅ Confirmar transporte y preparar PDFs", key=f"confirmar_transporte_{orden_seleccionada}", use_container_width=True):
                    st.session_state[key_transporte] = transporte_input
                    st.rerun()

                transporte_confirmado = st.session_state[key_transporte]
                col_pdf1, col_pdf2 = st.columns(2)
                with col_pdf1:
                    pdf_data = generar_pdf_bytes(datos_orden, df_detalle, transporte=transporte_confirmado)
                    st.download_button(label="📥 Descargar Orden de Compra (PDF)", data=pdf_data, file_name=f"Orden_Compra_{orden_seleccionada}.pdf", mime="application/pdf", use_container_width=True, key=f"dl_oc_{orden_seleccionada}")
                with col_pdf2:
                    pdf_remito = generar_pdf_remito_transporte(datos_orden, df_detalle, transporte=transporte_confirmado)
                    st.download_button(label="🚛 Descargar Remito de Transporte (PDF)", data=pdf_remito, file_name=f"Remito_Transporte_{orden_seleccionada}.pdf", mime="application/pdf", use_container_width=True, key=f"dl_rem_{orden_seleccionada}")
        
        st.markdown("---")
        df['Anular'] = False 
        df['Total'] = df['Total'].apply(lambda x: f"${x:,.2f}")
        
        column_config = {
            "ID": st.column_config.TextColumn("ID", disabled=True),
            "Proveedor": st.column_config.TextColumn("Proveedor", disabled=True),
            "Fecha": st.column_config.DateColumn("Fecha", disabled=True),
            "Entrega": st.column_config.DateColumn("Entrega", disabled=True),
            "Estado": st.column_config.TextColumn("Estado", disabled=True),
            "Total": st.column_config.TextColumn("Total", disabled=True),
            "Anular": st.column_config.CheckboxColumn("Anular OC", default=False)
        }
        
        edited_df = st.data_editor(df, column_config=column_config, disabled=df.columns[:-1], hide_index=True, use_container_width=True, key="editor_anular_ocs")
        anulaciones_pendientes = edited_df[edited_df['Anular'] == True]

        if not anulaciones_pendientes.empty:
            st.warning("🚨 Confirme la anulación de las órdenes seleccionadas.")
            if st.button("Confirmar Anulación", type="secondary", key="btn_conf_anular_oc"):
                for _, row in anulaciones_pendientes.iterrows():
                    if row['Estado'] == 'pendiente':
                        anular_orden_compra(row['ID'])
                st.rerun()
    else:
        st.info("No hay órdenes de compra registradas con esos filtros.")

def mostrar_gestion_ordenes_compra():
    """Función principal para importar y mostrar el módulo dentro de otra vista"""
    inicializar_session_state_oc()

    proveedores_data, proveedores_n2id, proveedores_id2n = obtener_datos_mapeados("proveedores")
    materias_data, materias_n2id, materias_id2n = obtener_datos_mapeados("materias_primas")

    proveedores_map = {'datos': proveedores_data, 'nombre_a_id': proveedores_n2id, 'id_a_nombre': proveedores_id2n}
    materias_map = {'datos': materias_data, 'nombre_a_id': materias_n2id, 'id_a_nombre': materias_id2n}
    
    if not proveedores_data or not materias_data:
        st.error("⚠️ **ERROR:** Asegúrese de que existen proveedores y materias primas en la base de datos.")
        return

    sub_selected = st.radio(
        "Acción en Órdenes de Compra:",
        ["Listar / Anular Órdenes", "Agregar Orden"],
        horizontal=True
    )
    st.markdown("---")

    if sub_selected == "Agregar Orden":
        agregar_orden_compra(proveedores_map, materias_map)
    elif sub_selected == "Listar / Anular Órdenes":
        listar_ordenes_compra()