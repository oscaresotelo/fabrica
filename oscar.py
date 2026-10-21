import streamlit as st
import sqlite3
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
import os

# Configuración de página de Streamlit
st.set_page_config(
    page_title="Minerva - Planificador de Producción",
    page_icon="🧪",
    layout="wide"
)

# Ruta base de datos
DB_PATH = "minerva.db"

# CONSTANTE DE ESCALA: Las recetas en la base de datos están formuladas para un lote de 200 Litros
BASE_RECETA_LITROS = 200.0

# Inicialización del estado de la sesión para almacenar el plan de producción actual
if "plan_produccion" not in st.session_state:
    st.session_state.plan_produccion = []

def check_db_exists():
    """Verifica si el archivo de la base de datos existe."""
    return os.path.exists(DB_PATH)

def run_query(query, params=()):
    """Ejecuta una consulta SQL y retorna un DataFrame."""
    if not check_db_exists():
        return pd.DataFrame()
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(query, conn, params=params)

def execute_action(query, params=()):
    """Ejecuta una acción de inserción, actualización o eliminación en la BD."""
    if not check_db_exists():
        return False
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid if query.strip().upper().startswith("INSERT") else True
    except Exception as e:
        st.error(f"Error en la base de datos: {e}")
        return False

def get_recetas():
    """Obtiene el listado de recetas disponibles."""
    query = "SELECT id, nombre, uso, linea FROM recetas ORDER BY nombre ASC"
    return run_query(query)

def get_ingredientes_receta(receta_id):
    """Obtiene los ingredientes de una receta con sus proporciones en la base de 200L."""
    query = """
    SELECT 
        mp.id as materia_prima_id,
        mp.nombre as materia_prima, 
        ri.cantidad as cantidad_base, 
        mp.unidad
    FROM receta_ingredientes ri
    JOIN materias_primas mp ON ri.materia_prima_id = mp.id
    WHERE ri.receta_id = ?
    """
    return run_query(query, (int(receta_id),))

def get_costos_materia_prima():
    """Obtiene el último costo registrado para cada materia prima."""
    query = """
    SELECT materia_prima_id, monto as costo_unitario 
    FROM costos_asociados 
    WHERE id IN (
        SELECT MAX(id) 
        FROM costos_asociados 
        GROUP BY materia_prima_id
    )
    """
    return run_query(query)

def get_clientes():
    """Obtiene el listado de clientes registrados."""
    query = "SELECT id, nombre FROM clientes ORDER BY nombre ASC"
    return run_query(query)

def generar_pdf_produccion_consolidada(lote_num, plan_items, df_consolidado, total_litros):
    """Genera un PDF para la orden de producción con la lista de productos y materias primas consolidadas."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        textColor=colors.HexColor('#1E3A8A'),
        spaceAfter=15
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        textColor=colors.HexColor('#4B5563'),
        spaceAfter=20
    )
    
    section_style = ParagraphStyle(
        'DocSection',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        textColor=colors.HexColor('#1E3A8A'),
        spaceBefore=15,
        spaceAfter=8
    )
    
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#1F2937')
    )
    
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.white
    )
    
    table_text_style = ParagraphStyle(
        'TableText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor('#1F2937')
    )

    # Encabezado principal
    elements.append(Paragraph("MINERVA - ORDEN DE PRODUCCIÓN CONSOLIDADA", title_style))
    elements.append(Paragraph(f"Lote/Plan N°: {lote_num} | Volumen Total Programado: {total_litros:,.2f} L", subtitle_style))
    elements.append(Spacer(1, 5))
    
    # 1. Tabla de Productos Planificados
    elements.append(Paragraph("Productos Incluidos en el Lote", section_style))
    productos_data = [[
        Paragraph("Producto / Receta", table_header_style),
        Paragraph("Cantidad a Producir", table_header_style),
        Paragraph("Factor de Escala", table_header_style)
    ]]
    for item in plan_items:
        productos_data.append([
            Paragraph(item["nombre"], table_text_style),
            Paragraph(f"{item['litros']:,.2f} L", table_text_style),
            Paragraph(f"{item['factor_escala']:.4f}x", table_text_style)
        ])
    t_productos = Table(productos_data, colWidths=[250, 150, 100])
    t_productos.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E3A8A')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#F3F4F6'), colors.white]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D5DB')),
    ]))
    elements.append(t_productos)
    elements.append(Spacer(1, 15))
    
    # 2. Tabla de Materias Primas Consolidadas
    elements.append(Paragraph("Materias Primas Consolidadas (Totales)", section_style))
    consolidado_data = [[
        Paragraph("Materia Prima", table_header_style),
        Paragraph("Cantidad Total Requerida", table_header_style),
        Paragraph("Unidad", table_header_style)
    ]]
    for _, row in df_consolidado.iterrows():
        consolidado_data.append([
            Paragraph(row["materia_prima"], table_text_style),
            Paragraph(f"{row['cantidad_requerida']:,.3f}", table_text_style),
            Paragraph(row["unidad"], table_text_style)
        ])
    t_consolidado = Table(consolidado_data, colWidths=[250, 150, 100])
    t_consolidado.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E3A8A')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#F3F4F6'), colors.white]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D5DB')),
    ]))
    elements.append(t_consolidado)
    
    # Firmas
    elements.append(Spacer(1, 40))
    elements.append(Paragraph("Firma Responsable Producción: __________________________________", body_style))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- INTERFAZ DE STREAMLIT ---

st.title("🧪 Minerva - Planificación Multi-Producto")
st.markdown(
    f"""
    Planifica la producción de **múltiples productos de forma simultánea**. El sistema consolidará 
    automáticamente los ingredientes en común y te dará las compras o retiros totales requeridos.
    *Nota: Las recetas base están diseñadas para un estándar de **{BASE_RECETA_LITROS:.0f} Litros**.*
    """
)

if not check_db_exists():
    st.error("⚠️ No se encontró la base de datos 'minerva.db'. Por favor, asegúrate de tener el archivo en el mismo directorio.")
else:
    # Carga de datos base
    df_recetas = get_recetas()
    df_costos = get_costos_materia_prima()
    df_clientes = get_clientes()
    
    if df_recetas.empty:
        st.warning("No hay recetas registradas en la base de datos.")
    else:
        # Layout principal
        col_inputs, col_results = st.columns([1, 2], gap="large")
        
        with col_inputs:
            st.subheader("Añadir Productos al Plan")
            
            # Selección de Receta
            receta_options = {row['nombre']: row['id'] for _, row in df_recetas.iterrows()}
            receta_seleccionada = st.selectbox("Seleccione la Receta", list(receta_options.keys()))
            receta_id = receta_options[receta_seleccionada]
            
            # Cantidad de litros para esta receta en particular
            litros_a_producir = st.number_input(
                "Cantidad de litros a producir", 
                min_value=1.0, 
                value=200.0, 
                step=10.0,
                help=f"Los insumos de esta receta se escalarán en base a {BASE_RECETA_LITROS:.0f}L."
            )
            
            factor_escala = litros_a_producir / BASE_RECETA_LITROS
            
            # Botón para añadir receta actual al plan activo
            if st.button("➕ Agregar al Plan", use_container_width=True):
                # Evitar duplicados simples o permitir acumular
                existe = False
                for item in st.session_state.plan_produccion:
                    if item["receta_id"] == receta_id:
                        # Si ya existe, le sumamos los litros y recalculamos la escala
                        item["litros"] += litros_a_producir
                        item["factor_escala"] = item["litros"] / BASE_RECETA_LITROS
                        existe = True
                        break
                
                if not existe:
                    st.session_state.plan_produccion.append({
                        "receta_id": receta_id,
                        "nombre": receta_seleccionada,
                        "litros": litros_a_producir,
                        "factor_escala": factor_escala
                    })
                st.success(f"Agregado: {receta_seleccionada} ({litros_a_producir:.0f} L)")

            st.write("---")
            st.subheader("Configuración de Orden")
            lote_codigo = st.text_input("Número de Lote / Orden General", value="LOTE-CONSOLIDADO-001")
            
            cliente_options = {"Sin cliente específico": None}
            if not df_clientes.empty:
                for _, row in df_clientes.iterrows():
                    cliente_options[row['nombre']] = row['id']
            cliente_seleccionado = st.selectbox("Cliente asociado", list(cliente_options.keys()))
            cliente_id = cliente_options[cliente_seleccionado]
            
            st.write("---")
            st.subheader("📋 Lista de Producción Activa")
            
            if len(st.session_state.plan_produccion) == 0:
                st.info("No hay productos en el plan. Utiliza el botón de arriba para agregar productos.")
            else:
                df_plan_ui = pd.DataFrame(st.session_state.plan_produccion)
                st.dataframe(
                    df_plan_ui[["nombre", "litros", "factor_escala"]].rename(columns={
                        "nombre": "Producto",
                        "litros": "Litros",
                        "factor_escala": "Escala"
                    }),
                    use_container_width=True,
                    hide_index=True
                )
                
                # Botón para limpiar todo el plan actual
                if st.button("🗑️ Limpiar Plan Completo", use_container_width=True, type="secondary"):
                    st.session_state.plan_produccion = []
                    st.rerun()

        with col_results:
            st.subheader("Cálculo Consolidado de Materia Prima")
            
            if len(st.session_state.plan_produccion) == 0:
                st.warning("Agrega al menos un producto a la lista en el panel izquierdo para ver la consolidación de materias primas.")
            else:
                # Recopilar todos los ingredientes de todas las recetas planificadas
                all_ingredients_data = []
                
                for item in st.session_state.plan_produccion:
                    df_ing_receta = get_ingredientes_receta(item["receta_id"])
                    if not df_ing_receta.empty:
                        # Escalar de acuerdo a los litros definidos para esta receta en particular
                        df_ing_receta["cantidad_requerida"] = df_ing_receta["cantidad_base"] * item["factor_escala"]
                        all_ingredients_data.append(df_ing_receta)
                
                if not all_ingredients_data:
                    st.error("No se encontraron ingredientes para las recetas seleccionadas.")
                else:
                    # Unir todos los dataframes
                    df_all_raw = pd.concat(all_ingredients_data, ignore_index=True)
                    
                    # Unir con el último costo unitario de la base de datos
                    if not df_costos.empty:
                        df_all_raw = df_all_raw.merge(df_costos, on="materia_prima_id", how="left")
                    else:
                        df_all_raw["costo_unitario"] = 0.0
                    
                    df_all_raw["costo_unitario"] = df_all_raw["costo_unitario"].fillna(0.0)
                    
                    # Agrupar por materia prima (ID, nombre, unidad, costo) y sumar la cantidad consolidada
                    df_consolidado = df_all_raw.groupby(
                        ["materia_prima_id", "materia_prima", "unidad", "costo_unitario"], 
                        as_index=False
                    ).agg({"cantidad_requerida": "sum"})
                    
                    # Calcular costo total consolidado de cada insumo
                    df_consolidado["costo_total"] = df_consolidado["cantidad_requerida"] * df_consolidado["costo_unitario"]
                    
                    # Mostrar tabla de resultados consolidados
                    st.dataframe(
                        df_consolidado[[
                            "materia_prima", 
                            "cantidad_requerida", 
                            "unidad", 
                            "costo_unitario", 
                            "costo_total"
                        ]].rename(columns={
                            "materia_prima": "Materia Prima",
                            "cantidad_requerida": "Cant. Consolidada",
                            "unidad": "Unidad",
                            "costo_unitario": "Costo Unit. ($)",
                            "costo_total": "Costo Total ($)"
                        }),
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Totales consolidados
                    costo_materia_prima_total = df_consolidado["costo_total"].sum()
                    total_litros_planificados = sum(item["litros"] for item in st.session_state.plan_produccion)
                    costo_promedio_por_litro = costo_materia_prima_total / total_litros_planificados if total_litros_planificados > 0 else 0.0
                    
                    col_c1, col_c2, col_c3 = st.columns(3)
                    with col_c1:
                        st.metric(
                            label="Litros Totales Programados",
                            value=f"{total_litros_planificados:,.1f} L"
                        )
                    with col_c2:
                        st.metric(
                            label="Costo Total Consolidado", 
                            value=f"${costo_materia_prima_total:,.2f}"
                        )
                    with col_c3:
                        st.metric(
                            label="Costo Promedio ponderado/L", 
                            value=f"${costo_promedio_por_litro:,.2f}"
                        )
                    
                    st.write("---")
                    col_b1, col_b2 = st.columns(2)
                    
                    with col_b1:
                        if st.button("💾 Guardar Plan de Producción", use_container_width=True, type="primary"):
                            exito = True
                            # Guardamos una simulación por cada receta del plan actual
                            for item in st.session_state.plan_produccion:
                                # Filtramos los insumos correspondientes a esta receta para guardarlos en su JSON
                                df_ing_item = df_all_raw[df_all_raw["materia_prima_id"].isin(
                                    get_ingredientes_receta(item["receta_id"])["materia_prima_id"]
                                )].copy()
                                
                                df_ing_item["cantidad_requerida"] = df_ing_item["cantidad_base"] * item["factor_escala"]
                                df_ing_item["costo_total"] = df_ing_item["cantidad_requerida"] * df_ing_item["costo_unitario"]
                                
                                resultado_json = df_ing_item[["materia_prima_id", "cantidad_requerida", "costo_total"]].to_json(orient="records")
                                
                                query_insert = """
                                INSERT INTO simulaciones (receta_id, cantidad, fecha, cliente_id, resultado_json)
                                VALUES (?, ?, date('now'), ?, ?)
                                """
                                sim_id = execute_action(query_insert, (int(item["receta_id"]), float(item["litros"]), cliente_id, resultado_json))
                                if not sim_id:
                                    exito = False
                            
                            if exito:
                                st.success(f"✅ ¡Plan consolidado guardado con éxito! Se registraron {len(st.session_state.plan_produccion)} simulaciones de lote.")
                    
                    with col_b2:
                        # Generación de la Orden de Producción en PDF Consolidado
                        pdf_data = generar_pdf_produccion_consolidada(
                            lote_num=lote_codigo,
                            plan_items=st.session_state.plan_produccion,
                            df_consolidado=df_consolidado,
                            total_litros=total_litros_planificados
                        )
                        
                        st.download_button(
                            label="📥 Descargar Orden de Trabajo (PDF)",
                            data=pdf_data,
                            file_name=f"orden_produccion_consolidada_{lote_codigo}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )