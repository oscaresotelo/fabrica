import streamlit as st
import sqlite3
import pandas as pd
from datetime import date
import calendar 
from fpdf import FPDF # <-- Importación para PDF
import io # <-- Importación para manejar bytes

# =================================================================================================
# CONFIG
# =================================================================================================
DB_PATH = "minerva.db"
LITROS_BASE_RECETA = 200 
DIAS_HABILES_FIJOS_MENSUAL = 20 

# =================================================================================================
# UTILIDADES DB
# =================================================================================================
def get_connection():
    """Establece la conexión a la base de datos."""
    conn = sqlite3.connect(DB_PATH)
    # FIX ANTERIOR MANTENIDO: Corregido el typo sqliteite3 a sqlite3
    conn.row_factory = sqlite3.Row 
    return conn

def fetch_df(query, params=()):
    """Ejecuta una consulta SELECT y devuelve los resultados como un DataFrame de Pandas."""
    conn = get_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
    except sqlite3.Error as e:
        # Se muestra un error en la app si la consulta falla
        st.error(f"Error al ejecutar la consulta: {e}")
        return pd.DataFrame()
    finally:
        conn.close()
    return df

# =================================================================================================
# LÓGICA CORE DE COSTOS (NUEVAS FUNCIONES DE BÚSQUEDA DE ID)
# =================================================================================================

def get_categoria_id_by_name(category_name):
    """Busca el ID de una categoría por su nombre."""
    query = "SELECT id FROM categorias_imputacion WHERE nombre = ?"
    df = fetch_df(query, (category_name,))
    if df.empty:
        return None
    return df.iloc[0, 0]

def get_costo_flete_ars():
    """
    Recupera el costo fijo de flete por receta (200L) desde la tabla 'gastos',
    filtrando por el ID de categoría especial (PARAMETRO).
    """
    # 1. Obtener el ID dinámicamente
    FLETE_CATEGORIA_ID_PARAMETRO = get_categoria_id_by_name('FLETE_BASE_RECETA')

    if FLETE_CATEGORIA_ID_PARAMETRO is None:
        return 0.0, "❌ Error de Configuración: La categoría 'FLETE_BASE_RECETA' no existe en la base de datos. Por favor, asegúrese de haber ejecutado el SQL de configuración."
        
    # 2. Usar el ID dinámico para buscar el importe en gastos
    query = f"""
        SELECT importe_total 
        FROM gastos 
        WHERE categoria_id = {FLETE_CATEGORIA_ID_PARAMETRO}
        LIMIT 1;
    """
    df_flete = fetch_df(query)
    
    if df_flete.empty:
        return 0.0, f"❌ Error: No se encontró el registro de costo base de flete en la tabla 'gastos' con la Categoría ID {FLETE_CATEGORIA_ID_PARAMETRO}. Por favor, verifique el registro de parámetros en su base de datos."
        
    return df_flete.iloc[0, 0], None


def get_recetas():
    """Recupera todas las recetas disponibles."""
    return fetch_df("SELECT id, nombre FROM recetas ORDER BY nombre")

def get_ultimo_costo_materia_prima():
    """
    Obtiene el último precio unitario (en USD) de cada materia prima 
    basado en la fecha de la compra más reciente.
    """
    query = """
        SELECT 
            t1.materia_prima_id, 
            t1.precio_unitario
        FROM compras_materia_prima t1
        INNER JOIN (
            SELECT materia_prima_id, MAX(fecha) AS max_fecha 
            FROM compras_materia_prima
            GROUP BY materia_prima_id
        ) t2 ON t1.materia_prima_id = t2.materia_prima_id AND t1.fecha = t2.max_fecha;
    """
    df_costos = fetch_df(query)
    # Devolver un diccionario para acceso rápido: {mp_id: precio_USD}
    return dict(zip(df_costos['materia_prima_id'], df_costos['precio_unitario']))

def calcular_costo_materia_prima_usd(receta_id, litros_a_fabricar):
    """Calcula el costo total de MP para una receta y cantidad de litros dada (en USD)."""
    
    query_ingredientes = """
        SELECT 
            ri.materia_prima_id, 
            ri.cantidad
        FROM receta_ingredientes ri
        WHERE ri.receta_id = ?
    """
    df_ingredientes = fetch_df(query_ingredientes, (receta_id,))
    
    if df_ingredientes.empty:
        return 0, "No se encontraron ingredientes para esta receta."

    precios_usd = get_ultimo_costo_materia_prima()
    
    costo_total_mp_usd = 0.0
    factor_escala = litros_a_fabricar / LITROS_BASE_RECETA
    
    for index, row in df_ingredientes.iterrows():
        mp_id = row['materia_prima_id']
        cantidad_base = row['cantidad'] 
        
        if mp_id not in precios_usd:
            return 0, f"Falta el precio de la materia prima ID: {mp_id}. Registre una compra reciente."
            
        precio_unitario_usd = precios_usd[mp_id]
        
        costo_ingrediente_usd = cantidad_base * factor_escala * precio_unitario_usd
        costo_total_mp_usd += costo_ingrediente_usd
        
    return costo_total_mp_usd, None

def get_detalle_gastos_mensual(mes_simulacion, anio_simulacion):
    """
    Recupera el detalle de los gastos fijos para el mes y año seleccionado,
    EXCLUYENDO el registro de parámetro de flete.
    """
    mes_str = f"{anio_simulacion:04d}-{mes_simulacion:02d}"
    
    FLETE_CATEGORIA_ID_PARAMETRO = get_categoria_id_by_name('FLETE_BASE_RECETA')

    # Filtra la consulta solo si la categoría existe
    filtro_flete = f"AND g.categoria_id != {FLETE_CATEGORIA_ID_PARAMETRO}" if FLETE_CATEGORIA_ID_PARAMETRO is not None else ""
    
    query = f"""
        SELECT 
            g.id,  -- Necesario para la clave única en el simulador
            g.fecha_factura, 
            g.beneficiario_nombre AS Beneficiario,
            c.nombre AS Categoria,
            g.numero_comprobante AS Comprobante,
            g.importe_total AS Importe_ARS
        FROM gastos g
        JOIN categorias_imputacion c ON g.categoria_id = c.id
        WHERE (g.fecha_pago LIKE '{mes_str}-%' OR g.fecha_factura LIKE '{mes_str}-%')
           {filtro_flete} -- Aplicar el filtro dinámico
        ORDER BY g.fecha_factura DESC
    """
    df_detalle = fetch_df(query)
    return df_detalle

def calcular_costo_indirecto_batch_ars(recetas_diarias, gasto_total_mensual_ars):
    """
    Calcula el costo indirecto asignado por cada batch (receta de 200L) en PESOS (ARS),
    utilizando el gasto total (real o simulado) y 20 días hábiles fijos al mes.
    """
    
    dias_habiles = DIAS_HABILES_FIJOS_MENSUAL 
    
    if recetas_diarias <= 0:
        return 0, dias_habiles, "Debe simular al menos 1 receta diaria para asignar gastos indirectos."
    
    if gasto_total_mensual_ars <= 0:
        return 0, dias_habiles, "El gasto fijo total es cero o negativo, el costo indirecto se asume como $0.00 ARS."
    
    # Calcular el total de Batches Mensuales Simulado
    total_batches_mensuales = recetas_diarias * dias_habiles
    
    # Costo Indirecto por Batch (200L) en ARS
    costo_indirecto_por_batch_ars = gasto_total_mensual_ars / total_batches_mensuales
    
    return costo_indirecto_por_batch_ars, dias_habiles, None

# =================================================================================================
# LÓGICA DE PRESUPUESTO (Simulación de guardado)
# =================================================================================================

def save_final_budget(company_name, budget_lines):
    """
    *** Placeholder para la LÓGICA DE GUARDADO EN BASE DE DATOS ***
    """
    if not budget_lines:
        st.error("No hay líneas para guardar.")
        return False
        
    # Calcular el total para la nota de cabecera
    total_presupuesto_ars = sum(item['Precio Venta (ARS)'] for item in budget_lines)
    
    # Limpiar el estado después de "guardar"
    st.session_state['budget_lines'] = []
    st.session_state['company_name_value'] = ""
    st.session_state['last_result'] = None # Asegurar que la última visualización se borre

    st.success(f"🎉 Presupuesto para **{company_name}** guardado con éxito. Total: ARS {total_presupuesto_ars:,.2f}. El formulario ha sido limpiado.")
    return True

# =================================================================================================
# LÓGICA DE GENERACIÓN DE PDF (MODIFICADO)
# =================================================================================================

class PDF(FPDF):
    """Clase personalizada de FPDF para añadir encabezado y pie de página."""
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'NOTA DE PRESUPUESTO COMERCIAL', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', 0, 0, 'C')

def create_budget_pdf(company_name, budget_lines, cotizacion_dolar):
    """Genera el contenido del PDF como un objeto BytesIO."""
    pdf = PDF('P', 'mm', 'A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.alias_nb_pages()
    
    # 1. Información General
    today = date.today().strftime("%d/%m/%Y")
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 5, f"Fecha: {today}", 0, 1, 'L')
    pdf.cell(0, 5, f"Cliente: {company_name}", 0, 1, 'L')
    pdf.cell(0, 5, f"Cotización USD:ARS: ARS {cotizacion_dolar:,.2f}", 0, 1, 'L')
    pdf.ln(10)
    
    # 2. Encabezado de la Tabla (Se elimina la columna de Margen)
    pdf.set_fill_color(200, 220, 255)
    pdf.set_font('Arial', 'B', 9) 
    # Nuevos anchos: 65 (Receta), 20 (Litros), 25 (P/Litro), 70 (Precio Venta Total) = 180mm
    col_widths = [65, 20, 25, 70] 
    
    pdf.cell(col_widths[0], 7, 'Producto (Receta)', 1, 0, 'C', 1)
    pdf.cell(col_widths[1], 7, 'Litros', 1, 0, 'C', 1)
    pdf.cell(col_widths[2], 7, 'Precio x Litro (ARS)', 1, 0, 'C', 1) # Se etiqueta mejor
    pdf.cell(col_widths[3], 7, 'Precio Venta Total (ARS)', 1, 1, 'C', 1) # Se utiliza el ancho restante
    

    # 3. Contenido de la Tabla
    pdf.set_font('Arial', '', 9)
    total_presupuesto_ars = 0
    
    for item in budget_lines:
        receta = item["Receta"]
        litros = f"{item['Litros']:,.0f}"
        precio_x_litro = "ARS {:,.2f}".format(item['Precio x Litro (ARS)'])
        # margen = f"{item['Margen (%)']:,.2f}%" # ELIMINADO
        precio_venta = "ARS {:,.2f}".format(item['Precio Venta (ARS)'])
        total_presupuesto_ars += item['Precio Venta (ARS)']
        
        # Usar multi_cell para recetas largas y obtener la altura de la fila
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        
        # Receta
        pdf.multi_cell(col_widths[0], 6, receta, 1, 'L', 0)
        max_height = pdf.get_y() - y_start
        
        # Restaurar posición y dibujar celdas restantes para que coincidan con la altura
        pdf.set_xy(x_start + col_widths[0], y_start)
        pdf.cell(col_widths[1], max_height, litros, 1, 0, 'R', 0)
        pdf.cell(col_widths[2], max_height, precio_x_litro, 1, 0, 'R', 0)
        # Se omite la celda de Margen
        pdf.cell(col_widths[3], max_height, precio_venta, 1, 1, 'R', 0) # Celda de Precio Total
        
    pdf.ln(5)

    # 4. Total
    pdf.set_font('Arial', 'B', 12)
    # Ajustar ancho de celda de etiqueta para el total (suma de las 3 primeras columnas)
    ancho_etiqueta_total = col_widths[0] + col_widths[1] + col_widths[2]
    ancho_valor_total = col_widths[3] # Ancho de la columna de Precio Venta Total
    
    pdf.cell(ancho_etiqueta_total, 7, 'TOTAL PRESUPUESTO:', 1, 0, 'R', 1)
    pdf.cell(ancho_valor_total, 7, "ARS {:,.2f}".format(total_presupuesto_ars), 1, 1, 'R', 1)
    
    # 5. Generar Byte Stream
    pdf_output = pdf.output(dest='S')
    return io.BytesIO(pdf_output)


# =================================================================================================
# INTERFAZ STREAMLIT
# =================================================================================================

def app_calculadora_presupuestos():
    st.title("💰 Calculadora de Costos y Presupuestos (ARS)")
    st.markdown("Costo de Materia Prima en USD **convertido a ARS** + Flete + Gastos Operativos en ARS.")
    st.markdown("---")
    
    # --- INICIALIZACIÓN DEL ESTADO DE LA NOTA DE PRESUPUESTO ---
    if 'budget_lines' not in st.session_state:
        st.session_state['budget_lines'] = []
    if 'company_name_value' not in st.session_state:
        st.session_state['company_name_value'] = ""
    # AÑADIDO: Almacén de resultados de la última simulación
    if 'last_result' not in st.session_state:
        st.session_state['last_result'] = None
    # -----------------------------------------------------------

    recetas_df = get_recetas()
    if recetas_df.empty:
        st.warning("⚠️ No hay recetas registradas en la base de datos.")
        return

    recetas_dict = dict(zip(recetas_df['nombre'], recetas_df['id']))
    nombres_recetas = list(recetas_dict.keys())

    # --- INPUTS PRINCIPALES ---
    st.header("1. Datos del Presupuesto y Cotización")

    # Nuevo Input: Nombre de la Empresa
    st.session_state['company_name_value'] = st.text_input(
        "Nombre de la Empresa a Presupuestar:",
        value=st.session_state['company_name_value'],
        key='company_name_input'
    )

    # Usamos st.session_state para persistir el valor de los inputs
    col_coti, col_litros = st.columns(2)
    with col_coti:
        cotizacion_dolar = st.number_input(
            "Cotización del Dólar (USD:ARS):", 
            min_value=0.01, 
            value=st.session_state.get('cotizacion_dolar_value', 900.00), 
            step=1.0, 
            format="%.2f",
            key="cotizacion_dolar_value"
        )
    with col_litros:
        litros_a_fabricar = st.number_input(
            "Cantidad de Litros a Presupuestar:", 
            min_value=LITROS_BASE_RECETA, 
            value=st.session_state.get('litros_a_fabricar_value', LITROS_BASE_RECETA), 
            step=100,
            key="litros_a_fabricar_value"
        )

    col1, col2, col3 = st.columns(3)
    with col1:
        # Se necesita encontrar el índice correcto para el valor guardado
        default_receta_index = nombres_recetas.index(st.session_state.get('receta_seleccionada_value', nombres_recetas[0])) if st.session_state.get('receta_seleccionada_value') in nombres_recetas else 0
        receta_seleccionada = st.selectbox("Seleccione la Receta:", nombres_recetas, key="receta_seleccionada_value", index=default_receta_index)
        
    with col2:
        today = date.today()
        mes_simulacion = st.selectbox("Mes de Gasto Fijo a Simular:", range(1, 13), index=today.month - 1, format_func=lambda x: calendar.month_name[x], key="mes_simulacion_value")
        anio_simulacion = st.number_input("Año de Gasto Fijo a Simular:", min_value=2020, value=today.year, step=1, key="anio_simulacion_value")
        
    with col3:
        recetas_diarias = st.number_input(
            "Simulación: Recetas de 200L producidas **diariamente**:", 
            min_value=1, 
            value=st.session_state.get('recetas_diarias_value', 2), 
            step=1,
            key="recetas_diarias_value"
        )
        margen_ganancia_porc = st.number_input(
            "Margen de Ganancia deseado (%) sobre Costo Total:", 
            min_value=0.0, 
            value=st.session_state.get('margen_ganancia_porc_value', 30.0), 
            step=1.0, 
            format="%.2f",
            key="margen_ganancia_porc_value"
        )
    
    # --- EXPANDER PARA AJUSTE INDIVIDUAL DE GASTOS ---
    df_gastos_detalle = get_detalle_gastos_mensual(mes_simulacion, anio_simulacion)
    
    # *** FIX: Inicialización y cálculo de variables necesarias fuera del botón ***
    # 1. Obtener el costo de flete base (necesario para la ayuda del st.metric en la sección 2)
    costo_flete_x_receta_ars, error_flete = get_costo_flete_ars()
    if error_flete:
        st.warning(f"⚠️ {error_flete}") # Cambiamos a warning para no detener la app
        costo_flete_x_receta_ars = 0.0

    # 2. Calcular el gasto fijo simulado (necesario para la ayuda del st.metric en la sección 2)
    gasto_fijo_simulado = 0.0
    
    # La lógica para sumar los inputs simulados DEBE estar aquí para que Streamlit los recalcule
    if not df_gastos_detalle.empty:
        for index, row in df_gastos_detalle.iterrows():
            expense_id = row['id']
            # Inicializar el estado si es la primera carga (movido desde el expander)
            if f"sim_gasto_{expense_id}" not in st.session_state:
                st.session_state[f"sim_gasto_{expense_id}"] = row['Importe_ARS']
            
            # Sumar el valor actual del widget (que está en st.session_state)
            gasto_fijo_simulado += st.session_state.get(f"sim_gasto_{expense_id}", row['Importe_ARS'])

    # El Expander solo muestra la interfaz de input, pero el cálculo de 'gasto_fijo_simulado' ya se hizo arriba
    with st.expander(f"👁️ Detalle y Ajuste Individual de Gastos Fijos (Gastos Operativos) - ({calendar.month_name[mes_simulacion]} / {anio_simulacion})"):
        
        if not df_gastos_detalle.empty:
            st.markdown("---")
            st.info("💡 **Modifique el importe** del gasto individual para simular un nuevo Gasto Fijo Total.")
            
            total_real = 0.0
            
            col_label_header, col_input_header = st.columns([3, 1])
            with col_label_header:
                st.markdown("**Gasto**")
            with col_input_header:
                st.markdown("**Importe (ARS)**")
            st.markdown("---") 

            # Iterar sobre los gastos reales y crear un input para cada uno
            for index, row in df_gastos_detalle.iterrows():
                expense_id = row['id']
                original_importe = row['Importe_ARS']
                total_real += original_importe
                
                label = f"[{row['Categoria']}] {row['Beneficiario']} ({row['fecha_factura']})"
                
                col_label, col_input = st.columns([3, 1])
                
                with col_label:
                    st.caption(label)
                
                with col_input:
                    # Input de simulación. El valor inicial se carga desde el st.session_state
                    st.number_input(
                        "Importe:",
                        min_value=0.0,
                        value=st.session_state[f"sim_gasto_{expense_id}"], 
                        step=100.0,
                        format="%.2f",
                        key=f"sim_gasto_{expense_id}", 
                        label_visibility="collapsed",
                        help=f"Gasto real: {original_importe:,.2f} ARS"
                    )
                
            st.markdown("---")
            st.success(f"**Gasto Operativo Total REAL (ARS): {total_real:,.2f}**")
            
        else:
            st.info("No hay detalle de gastos fijos registrados para este mes. El gasto simulado será 0.")
    
    # --- BOTÓN DE CÁLCULO Y LÓGICA DE CÁLCULO ---
    if st.button("🚀 Calcular Costos y Precio de Venta"):
        
        if litros_a_fabricar <= 0 or cotizacion_dolar <= 0:
            st.error("La cantidad de litros y la cotización del dólar deben ser mayores que cero.")
            return

        receta_id = recetas_dict[receta_seleccionada]
        
        # --- PASO 1: OBTENER VALOR FIJO DE FLETE (YA CALCULADO ARRIBA) ---
        # Si hubo un error de DB, costo_flete_x_receta_ars ya es 0.0

        # --- PASO 2: CALCULAR COSTO DIRECTO (MP) EN USD Y CONVERTIR A ARS ---
        costo_mp_total_usd, error_mp = calcular_costo_materia_prima_usd(receta_id, litros_a_fabricar)
        
        if error_mp:
            st.error(f"❌ Error al calcular costo de Materia Prima: {error_mp}")
            # Limpiar resultados anteriores en caso de error
            st.session_state['last_result'] = None
            return
        
        costo_mp_total_ars = costo_mp_total_usd * cotizacion_dolar
        
        # --- PASO 3: CÁLCULO DE FLETE (COSTO DIRECTO ADICIONAL) ---
        factor_escala = litros_a_fabricar / LITROS_BASE_RECETA
        costo_flete_total_ars = costo_flete_x_receta_ars * factor_escala
        
        # --- PASO 4: CALCULAR COSTO INDIRECTO (GASTOS) EN ARS ---
        
        # gasto_fijo_simulado ya está calculado arriba
        
        costo_indirecto_x_batch_ars, dias_habiles, error_indirecto = calcular_costo_indirecto_batch_ars(
            recetas_diarias, gasto_fijo_simulado
        )
        
        if error_indirecto:
            st.warning(f"⚠️ Asignación de Gastos: {error_indirecto}")
        
        # Escalar el Costo Indirecto (ARS) al volumen presupuestado
        costo_indirecto_total_ars = costo_indirecto_x_batch_ars * factor_escala
        
        # --- PASO 5: CÁLCULO FINAL Y GUARDADO EN ESTADO ---
        costo_total_unitario_ars = costo_mp_total_ars + costo_flete_total_ars + costo_indirecto_total_ars
        
        margen_factor = 1 + (margen_ganancia_porc / 100)
        precio_venta_final_ars = costo_total_unitario_ars * margen_factor
        precio_por_litro_ars = precio_venta_final_ars / litros_a_fabricar
        
        # *** FIX CLAVE: Guardar resultados en el estado ***
        st.session_state['last_result'] = {
            "Receta": receta_seleccionada,
            "Litros": litros_a_fabricar,
            "Costo MP (ARS)": costo_mp_total_ars,
            "Flete (ARS)": costo_flete_total_ars,
            "Indirecto (ARS)": costo_indirecto_total_ars,
            "Costo Total (ARS)": costo_total_unitario_ars,
            "Precio Venta (ARS)": precio_venta_final_ars,
            "Precio x Litro (ARS)": precio_por_litro_ars,
            "Margen (%)": margen_ganancia_porc,
            "Dólar": cotizacion_dolar
        }
        # FIN DE LA LÓGICA DE CALCULO

    # ==============================================================================================
    # SECCIONES 2 Y 3: Resultados (Leen del estado)
    # ==============================================================================================
    if st.session_state['last_result'] is not None:
        # Recuperar resultados del estado de sesión
        result = st.session_state['last_result']
        
        st.markdown("---")
        st.header("2. Resultados del Costeo")
        
        # COLUMNAS PRINCIPALES (3 columnas)
        col_directo, col_indirecto, col_total_final = st.columns(3) 
        
        # Columna 1: Costo Directo (MP + Flete)
        with col_directo:
            st.subheader("Costo Directo")
            st.metric(label="Materia Prima", 
                      value="ARS {:,.2f}".format(result['Costo MP (ARS)']), 
                      help=f"Costo MP en USD convertido a ARS a una cotización de {result['Dólar']:,.2f}.")
            st.metric(label="Flete", 
                      value="ARS {:,.2f}".format(result['Flete (ARS)']), 
                      help=f"Flete base: ARS {costo_flete_x_receta_ars:,.2f} por batch (200L).") 
            st.markdown(f"**Subtotal Directo:** ARS {(result['Costo MP (ARS)'] + result['Flete (ARS)']):,.2f}") 
        
        # Columna 2: Costo Indirecto
        with col_indirecto:
            st.subheader("Costo Indirecto")
            st.metric(label="Asignado (Gastos)", 
                      value="ARS {:,.2f}".format(result['Indirecto (ARS)']), 
                      help=f"Asignación basada en el total simulado de gastos operativos (ARS {gasto_fijo_simulado:,.2f}).")
            
        # Columna 3: Costo Total y Margen (Destacado)
        with col_total_final:
            st.subheader("COSTO TOTAL")
            st.metric(label="Total (ARS)", 
                      value="ARS {:,.2f}".format(result['Costo Total (ARS)'])) 
            st.metric(label="Margen de Ganancia", 
                      value=f"{result['Margen (%)']}%")

            
        st.markdown("---")
        
        # Resultados de Venta (3 columnas)
        st.subheader("3. Resultados de Venta")
        col_margen, col_precio_total, col_precio_litro = st.columns(3)
        
        with col_margen:
            st.caption("Costo por Litro Base:")
            st.metric(label="Costo Unitario (ARS)", 
                      value="ARS {:,.2f}".format(result['Costo Total (ARS)'] / result['Litros']), 
                      help="Costo Total / Litros a Fabricar")

        with col_precio_total:
            st.caption("Precio Final (Total):")
            st.metric("PRECIO DE VENTA (Total)", 
                      value="ARS {:,.2f}".format(result['Precio Venta (ARS)'])) 
            
        with col_precio_litro:
            st.caption("Precio Final (Unitario):")
            st.metric("PRECIO POR LITRO", 
                      value="ARS {:,.2f}".format(result['Precio x Litro (ARS)'])) 
        
        # --- BOTÓN AGREGAR (Usa el last_result guardado en el estado) ---
        st.markdown("---")
        if st.button("➕ Agregar esta Receta a la Nota de Presupuesto", type="secondary", key="add_to_budget_btn"):
            if not st.session_state['company_name_value']:
                st.error("Por favor, ingrese el nombre de la empresa antes de agregar recetas.")
            else:
                # El resultado ya está en 'result' (last_result), lo usamos directamente.
                new_line = {
                    "Receta": result["Receta"],
                    "Litros": result["Litros"],
                    "Costo Total (ARS)": result["Costo Total (ARS)"],
                    "Precio Venta (ARS)": result["Precio Venta (ARS)"],
                    "Precio x Litro (ARS)": result["Precio x Litro (ARS)"],
                    "Margen (%)": result["Margen (%)"],
                    # Añadir la cotización del dólar a la línea para el PDF si es necesario, 
                    # aunque se usa la más reciente del input.
                    "Dólar": result["Dólar"]
                }
                st.session_state['budget_lines'].append(new_line)
                st.session_state['last_result'] = None # Ocultar resultados después de agregar
                st.success(f"✅ Receta '{result['Receta']}' agregada al presupuesto para {st.session_state['company_name_value']}.")
                st.rerun() 

# ----------------------------------------------------------------------------------
# SECCIÓN 4: NOTA DE PRESUPUESTO EN CONSTRUCCIÓN
# ----------------------------------------------------------------------------------
    st.markdown("---")
    st.header("4. Nota de Presupuesto en Construcción")

    if not st.session_state['budget_lines']:
        st.info("Aún no se han agregado recetas a la nota de presupuesto. Calcule un costo y presione 'Agregar'.")
    else:
        st.subheader(f"Presupuesto para: **{st.session_state['company_name_value']}**")
        
        # Formatear datos para mostrar
        budget_df = pd.DataFrame(st.session_state['budget_lines'])
        
        # Formatear columnas numéricas para mejor visualización
        budget_df_display = budget_df.copy()
        
        # Seleccionar y renombrar columnas para una visualización más limpia
        # **NOTA: Se mantiene Margen(%) aquí para visualización interna, solo se elimina del PDF.**
        budget_df_display = budget_df_display[[
            "Receta", 
            "Litros", 
            "Precio Venta (ARS)", 
            "Precio x Litro (ARS)", 
            "Margen (%)"
        ]]
        
        for col in ["Precio Venta (ARS)", "Precio x Litro (ARS)"]:
            budget_df_display[col] = budget_df_display[col].apply(lambda x: "ARS {:,.2f}".format(x)) 
        budget_df_display["Margen (%)"] = budget_df_display["Margen (%)"].apply(lambda x: f"{x:,.2f}%")
        
        st.dataframe(
            budget_df_display, 
            use_container_width=True, 
            hide_index=True
        )

        # Calcular el total para mostrar en el botón de guardar
        total_presupuesto_ars = sum(item['Precio Venta (ARS)'] for item in st.session_state['budget_lines'])
        
        # NUEVO: Añadir columna para el botón de descarga
        col_save, col_clear, col_download = st.columns([2, 1, 1]) 
        
        with col_save:
            if st.button(f"💾 Guardar Nota de Presupuesto Final (Total: ARS {total_presupuesto_ars:,.2f})", type="primary", key="save_final_btn"):
                if save_final_budget(st.session_state['company_name_value'], st.session_state['budget_lines']):
                    pass
                
        with col_clear:
            if st.button("🗑️ Limpiar Nota de Presupuesto (Borrar Líneas)", key="clear_budget_btn"):
                st.session_state['budget_lines'] = []
                st.session_state['company_name_value'] = ""
                st.session_state['last_result'] = None
                st.rerun()

        # LÓGICA DE DESCARGA DE PDF (CORREGIDA)
        with col_download: 
            # Datos necesarios para el PDF
            company_name = st.session_state['company_name_value']
            budget_lines = st.session_state['budget_lines']
            # Usa la cotización actual del input (puede no ser la de la línea, pero es la que se usó en el cálculo reciente)
            cotizacion_dolar = st.session_state.get('cotizacion_dolar_value', 0.0) 
            
            # Generar el PDF y obtener el byte stream
            pdf_bytes_io = create_budget_pdf(company_name, budget_lines, cotizacion_dolar)
            
            # Botón de descarga
            st.download_button(
                label="⬇️ Descargar Presupuesto (PDF)",
                data=pdf_bytes_io,
                file_name=f"Presupuesto_{company_name.replace(' ', '_')}_{date.today().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                type="secondary"
            )


# =================================================================================================
# RUN (Para probar el archivo directamente)
# =================================================================================================
if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="Calculadora de Presupuestos (ARS)")
    app_calculadora_presupuestos()