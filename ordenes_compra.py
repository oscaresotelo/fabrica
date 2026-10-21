# ordenes_compra_final_corregido.py

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from streamlit_option_menu import option_menu 
from utils_pdf import generar_pdf_bytes, generar_pdf_remito_transporte

# --- Configuración y Conexión a la base de datos ---
DB_PATH = "minerva.db"

def conectar_db():
    """Establece la conexión a la base de datos SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def obtener_datos_mapeados(tabla):
    """Obtiene datos (id, nombre) y crea mapeos de nombre a id y viceversa."""
    with conectar_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT id, nombre FROM {tabla}")
        resultados = cursor.fetchall()

        datos = [{'id': r['id'], 'nombre': r['nombre']} for r in resultados]

        # Mapeos para facilitar el uso en Streamlit
        map_nombre_a_id = {item['nombre']: item['id'] for item in datos}
        map_id_a_nombre = {item['id']: item['nombre'] for item in datos}

        return datos, map_nombre_a_id, map_id_a_nombre

def fetch_data(query, params=()):
    """Ejecuta una consulta SELECT y devuelve los resultados como un DataFrame de Pandas."""
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
    """Obtiene el último precio_unitario registrado en compras_materias_primas para una materia prima."""
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
    """Crea una nueva orden de compra (encabezado y detalles) de forma transaccional."""
    conn = None 
    try:
        conn = conectar_db()
        cursor = conn.cursor()

        # 1. Insertar encabezado de la orden
        cursor.execute("""
            INSERT INTO ordenes_de_compra (proveedor_id, fecha_orden, fecha_entrega, estado)
            VALUES (?, ?, ?, ?)
        """, (proveedor_id, fecha_orden.strftime('%Y-%m-%d'), fecha_entrega.strftime('%Y-%m-%d'), 'pendiente'))
        orden_compra_id = cursor.lastrowid

        # 2. Insertar detalles de la orden
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
    """Actualiza el estado de una orden de compra a 'anulada'."""
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
            # Podría ser que ya estaba anulada o no se encontró
            st.warning(f"⚠️ La Orden No. {orden_id} no pudo ser anulada (puede que ya estuviera en otro estado o no exista).")
            return False
            
    except sqlite3.Error as e:
        st.error(f"❌ Error al anular la orden de compra {orden_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# ----------------------------------------------------------------------
# Lógica de Streamlit (UI) y Session State
# ----------------------------------------------------------------------

def inicializar_session_state():
    """Inicializa el estado de la sesión de Streamlit para la gestión de ítems."""
    if 'orden_items' not in st.session_state:
        st.session_state.orden_items = [{
            'materia_prima_nombre': None,
            'cantidad': 1.0,
            'precio_unitario': 0.01
        }]

def agregar_item_vacio():
    """Añade un diccionario de item vacío."""
    st.session_state.orden_items.append({
        'materia_prima_nombre': None,
        'cantidad': 1.0, 
        'precio_unitario': 0.01
    })

def eliminar_item(index):
    """Elimina un item por su índice de la lista de items en session_state."""
    if 0 <= index < len(st.session_state.orden_items):
        st.session_state.orden_items.pop(index)
        
def agregar_orden_compra(proveedores_map, materias_map):
    st.markdown("### 📝 Nueva Orden de Compra")

    # Asegurar que haya al menos un item si la lista está vacía
    

    proveedores_nombres = list(proveedores_map['nombre_a_id'].keys())
    materias_nombres = list(materias_map['nombre_a_id'].keys())
    
    # --- BOTÓN DE AGREGAR ITEM (FUERA DEL FORMULARIO PARA FORZAR RERUN) ---
    if st.button("➕ Agregar otro item", type="secondary", use_container_width=True, key="add_item_btn_top"):
        agregar_item_vacio()
        st.rerun()

    st.markdown("---")

    # Estructura visual más limpia con un contenedor
    with st.container(border=True):
        st.subheader("Datos de Encabezado")
        
        # --- INICIO DEL FORMULARIO PRINCIPAL (CAPTURA DE DATOS) ---
        with st.form("nueva_orden", clear_on_submit=False): 
            col1, col2 = st.columns(2)

            with col1:
                proveedor_nombre = st.selectbox("Proveedor", proveedores_nombres, index=None, placeholder="Seleccione un proveedor...")

            with col2:
                fecha_orden = st.date_input("Fecha de Orden", datetime.now().date())

            fecha_entrega = st.date_input("Fecha de Entrega (Estimada)", datetime.now().date() + timedelta(days=7))

            transporte = st.text_input(
                "🚛 Transporte",
                placeholder="Nombre de la empresa o transportista...",
                help="Ingrese el nombre del transporte que retirará la orden."
            )

            st.divider()
            st.subheader("Detalles de la Orden")
            st.caption("Los botones de eliminar se encuentran en la parte inferior de la página.")

            # Iterar y mostrar los items guardados en st.session_state
            # Los INPUTS permanecen dentro del formulario
            for i, item in enumerate(st.session_state.orden_items):
                with st.container(border=True):
                    # Campos de entrada (DENTRO DEL FORMULARIO)
                    cols = st.columns([0.4, 0.3, 0.3])

                    # Calcular índice actual para el selectbox
                    try:
                        current_mp_index = materias_nombres.index(item['materia_prima_nombre']) if item['materia_prima_nombre'] else None
                    except ValueError:
                        current_mp_index = None

                    with cols[0]:
                        materia_seleccionada = cols[0].selectbox(
                            f"Materia Prima #{i+1}", 
                            materias_nombres, 
                            key=f"mp_name_{i}",
                            index=current_mp_index,
                            placeholder="Seleccione..."
                        )

                        st.session_state.orden_items[i]['materia_prima_nombre'] = materia_seleccionada

                        # 🔹 SUGERIR ÚLTIMO PRECIO AUTOMÁTICAMENTE
                        if materia_seleccionada:
                            materia_id = materias_map['nombre_a_id'].get(materia_seleccionada)
                            ultimo_precio = obtener_ultimo_precio_materia_prima(materia_id)

                            if item['precio_unitario'] == 0.01 and ultimo_precio is not None:
                                st.session_state[f"precio_{i}"] = float(ultimo_precio)

                    with cols[1]:
                        cantidad_valor = cols[1].number_input(
                            f"Cantidad",
                            min_value=0.01,
                            step=0.1,
                            key=f"cant_{i}",
                            value=item['cantidad']
                        )
                        st.session_state.orden_items[i]['cantidad'] = cantidad_valor
                    with cols[2]:
                        precio_actual = item.get('precio_unitario', 0.01)

                        if precio_actual is None or precio_actual <= 0:
                            precio_actual = 0.01

                        precio_input = cols[2].number_input(
                            f"P. Unitario ($)",
                            min_value=0.01,
                            value=float(precio_actual),
                            step=0.01,
                            format="%.2f",
                            key=f"precio_{i}"
                        )

                        st.session_state.orden_items[i]['precio_unitario'] = precio_input

            # Botón de envío del formulario. ESTO DEBE ESTAR DENTRO.
            guardar = st.form_submit_button("💾 Guardar Orden de Compra", type="primary", use_container_width=True,on_click=None
)
            
    # ------------------------------------------------------------------
    # --- LÓGICA DE ELIMINAR (BOTONES FUERA DEL FORMULARIO) ---
    # ------------------------------------------------------------------
    if st.session_state.orden_items:
        st.subheader("Eliminar Ítems")

        for i, item in enumerate(st.session_state.orden_items):
            mp_nombre = item['materia_prima_nombre'] or f"Item #{i+1} (Vacío)"

            col1, col2 = st.columns([0.8, 0.2])

            with col1:
                st.write(f"• {mp_nombre}")

            with col2:
                if st.button(
                    "🗑️ Eliminar",
                    key=f"del_item_{i}",
                    use_container_width=True
                ):
                    eliminar_item(i)
                    st.rerun()
    
    st.markdown("---")

    # --- Lógica de Guardado (Se ejecuta SOLO si el form se envió correctamente) ---
    if guardar: 
        # 1. Validaciones
        if not proveedor_nombre:
            st.error("❌ Por favor, seleccione un proveedor.")
            return

        detalles_a_guardar = []
        items_validos = [item for item in st.session_state.orden_items if item['materia_prima_nombre'] is not None]
        if not items_validos:
            st.error("❌ La orden de compra debe tener al menos un item válido (Materia Prima seleccionada).")
            return
            
        for item in items_validos:
            # 2. Mapear nombres a IDs para la DB
            materia_prima_id = materias_map['nombre_a_id'].get(item['materia_prima_nombre'])
            
            detalles_a_guardar.append({
                'materia_prima_id': materia_prima_id,
                'cantidad': item['cantidad'],
                'precio_unitario': item['precio_unitario']
            })

        proveedor_id = proveedores_map['nombre_a_id'][proveedor_nombre]

        # 3. Llamar a la función transaccional de la DB
        if crear_orden_compra(proveedor_id, fecha_orden, fecha_entrega, detalles_a_guardar):
            # Limpiar el estado de los items para la siguiente orden
            st.session_state.orden_items = []
            st.rerun()


def listar_ordenes_compra():
    st.markdown("### 📋 Órdenes de Compra Emitidas")

    # --- Filtros de la lista ---
    with st.expander("Filtros de Búsqueda"):
        col1, col2, col3 = st.columns(3)
        
        # Fecha de Inicio por defecto: Hace 30 días
        default_start_date = datetime.now().date() - timedelta(days=30)
        
        with col1:
            fecha_inicio = st.date_input("📅 Fecha de Inicio", default_start_date)
        with col2:
            fecha_fin = st.date_input("📅 Fecha de Fin", datetime.now().date())
        with col3:
            estado_filtro = st.selectbox("Estado", ['Todos', 'pendiente', 'anulada'], index=0)

    # --- Construir la consulta SQL con el filtro de fecha y estado ---
    query = f"""
    SELECT
        oc.id AS ID,
        p.nombre AS Proveedor,
        oc.fecha_orden AS Fecha,
        oc.fecha_entrega AS Entrega,
        oc.estado AS Estado,
        SUM(doc.cantidad * doc.precio_unitario) AS Total
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
        # --- NUEVA SECCIÓN: Visualización de Contenido ---
        st.subheader("🔍 Detalle de la Orden")
        ids_disponibles = df['ID'].tolist()
        orden_seleccionada = st.selectbox("Seleccione un ID de orden para ver su contenido:", ids_disponibles)
        
        if orden_seleccionada:
            query_detalle = """
            SELECT 
                mp.nombre AS 'Materia Prima',
                doc.cantidad AS Cantidad,
                doc.precio_unitario AS 'Precio Unitario',
                (doc.cantidad * doc.precio_unitario) AS Subtotal
            FROM detalle_orden_compra doc
            JOIN materias_primas mp ON doc.materia_prima_id = mp.id
            WHERE doc.orden_compra_id = ?
            """
            df_detalle = fetch_data(query_detalle, params=(int(orden_seleccionada),))
            st.table(df_detalle)
            datos_orden = df[df['ID'] == orden_seleccionada].iloc[0].to_dict()

            # --- Sección de descarga con transporte ---
            # Usamos session_state para que el valor del transporte persista
            # entre el ingreso del texto y el click del botón de descarga.
            key_transporte = f"transporte_confirmado_{orden_seleccionada}"
            if key_transporte not in st.session_state:
                st.session_state[key_transporte] = ""

            with st.container(border=True):
                st.markdown("##### 📄 Generar PDFs")
                transporte_input = st.text_input(
                    "🚛 Transporte",
                    value=st.session_state[key_transporte],
                    placeholder="Nombre del transportista...",
                    key=f"transporte_input_{orden_seleccionada}"
                )

                if st.button("✅ Confirmar transporte y preparar PDFs", key=f"confirmar_transporte_{orden_seleccionada}", use_container_width=True):
                    st.session_state[key_transporte] = transporte_input
                    st.rerun()

                # Los botones de descarga usan el valor YA CONFIRMADO en session_state
                transporte_confirmado = st.session_state[key_transporte]

                if transporte_confirmado:
                    st.caption(f"Transporte confirmado: **{transporte_confirmado}**")
                else:
                    st.caption("Sin transporte asignado (ingrese el nombre y confirme antes de descargar).")

                col_pdf1, col_pdf2 = st.columns(2)

                with col_pdf1:
                    pdf_data = generar_pdf_bytes(datos_orden, df_detalle, transporte=transporte_confirmado)
                    st.download_button(
                        label="📥 Descargar Orden de Compra (PDF)",
                        data=pdf_data,
                        file_name=f"Orden_Compra_{orden_seleccionada}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

                with col_pdf2:
                    pdf_remito = generar_pdf_remito_transporte(datos_orden, df_detalle, transporte=transporte_confirmado)
                    st.download_button(
                        label="🚛 Descargar Remito de Transporte (PDF)",
                        data=pdf_remito,
                        file_name=f"Remito_Transporte_{orden_seleccionada}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
        st.markdown("---")
        # --- Fin Sección Visualización ---

        # Columna de acción (botón)
        df['Anular'] = False # Columna booleana para el botón/checkbox
        
        # Formato de moneda para la columna 'Total' (usando string)
        df['Total'] = df['Total'].apply(lambda x: f"${x:,.2f}")
        
        # 2. Configuración para st.data_editor
        column_config = {
            "ID": st.column_config.TextColumn("ID", disabled=True),
            "Proveedor": st.column_config.TextColumn("Proveedor", disabled=True),
            "Fecha": st.column_config.DateColumn("Fecha", disabled=True),
            "Entrega": st.column_config.DateColumn("Entrega", disabled=True),
            # FIX: Reemplazamos TagListColumn por TextColumn para compatibilidad
            "Estado": st.column_config.TextColumn("Estado", disabled=True),
            "Total": st.column_config.TextColumn("Total", disabled=True),
            "Anular": st.column_config.CheckboxColumn("Anular OC", help="Marque para anular la orden (solo si está pendiente)", default=False, disabled=False)
        }
        
        # 3. Mostrar el Data Editor (más intuitivo)
        st.caption(f"Se encontraron **{len(df)}** órdenes.")
        
        edited_df = st.data_editor(
            df,
            column_config=column_config,
            disabled=df.columns[:-1], # Deshabilitar todas las columnas excepto el checkbox 'Anular'
            hide_index=True,
            use_container_width=True
        )
        
        # 4. Lógica de Anulación basada en la edición (fuera del data_editor)
        anulaciones_pendientes = edited_df[edited_df['Anular'] == True]

        if not anulaciones_pendientes.empty:
            st.warning("🚨 Confirme la anulación de las órdenes seleccionadas. Solo las órdenes en estado 'pendiente' serán afectadas.")
            if st.button("Confirmar Anulación", type="secondary"):
                for index, row in anulaciones_pendientes.iterrows():
                    orden_id_a_anular = row['ID']
                    if row['Estado'] == 'pendiente':
                        # Llama a la función transaccional de anulación
                        anular_orden_compra(orden_id_a_anular)
                    else:
                        st.info(f"La Orden No. {orden_id_a_anular} ya está en estado '{row['Estado']}'. No se puede anular.")
                
                # Forzar recarga de la lista después de la acción
                st.rerun()

    else:
        st.info("No hay órdenes de compra registradas con esos filtros.")


def mostrar_ordenes_de_compra():
    # Establecer la configuración de la página
    st.set_page_config(
        page_title="Gestión de Órdenes",
        page_icon="🛒",
        layout="wide"
    )
    st.title("🛒 Sistema de Gestión de Órdenes de Compra")

    # Inicializar el Session State
    inicializar_session_state()

    # 1. Obtener datos y mapeos
    proveedores_data, proveedores_n2id, proveedores_id2n = obtener_datos_mapeados("proveedores")
    materias_data, materias_n2id, materias_id2n = obtener_datos_mapeados("materias_primas")

    proveedores_map = {'datos': proveedores_data, 'nombre_a_id': proveedores_n2id, 'id_a_nombre': proveedores_id2n}
    materias_map = {'datos': materias_data, 'nombre_a_id': materias_n2id, 'id_a_nombre': materias_id2n}
    
    if not proveedores_data or not materias_data:
        st.error("⚠️ **ERROR:** Asegúrese de que existen proveedores y materias primas en la base de datos para continuar.")
        return

    # 2. Menú de navegación mejorado
    sub_selected = option_menu(
        menu_title=None,
        options=["Agregar Orden", "Listar/Anular Órdenes"],
        icons=["file-earmark-plus", "table"],
        orientation="horizontal",
    )

    # 3. Mostrar la sección seleccionada
    st.markdown("---")
    if sub_selected == "Agregar Orden":
        agregar_orden_compra(proveedores_map, materias_map)
    elif sub_selected == "Listar/Anular Órdenes":
        listar_ordenes_compra()

# --- Punto de entrada para la aplicación Streamlit ---
if __name__ == '__main__':
    mostrar_ordenes_de_compra()