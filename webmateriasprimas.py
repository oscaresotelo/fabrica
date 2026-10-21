import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from io import BytesIO

# Importar ReportLab para la generación del PDF con control de fallos
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Configuración de la página
st.set_page_config(
    page_title="Minerva - Control de Stock Capilar e Importancia",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo personalizado Premium
st.markdown("""
    <style>
        .main {
            background-color: #f9fafb;
        }
        div.block-container {
            padding-top: 2rem;
        }
        .metric-card {
            background-color: white;
            padding: 1.2rem;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.04);
            border-left: 5px solid #3B82F6;
            margin-bottom: 1rem;
        }
        .metric-card-alert {
            border-left-color: #EF4444;
        }
        .metric-card-warning {
            border-left-color: #F59E0B;
        }
    </style>
""", unsafe_allow_html=True)

# Ruta por defecto de la base de datos
DEFAULT_DB_PATH = "minerva.db"

# --- CATEGORIZADOR INTELIGENTE (Adaptado al sector de Cosmética y Cuidado Capilar) ---
def categorizar_materia_prima(nombre):
    """Clasifica dinámicamente los insumos químicos, esencias y activos capilares."""
    nombre_lower = str(nombre).lower()
    if any(x in nombre_lower for x in ['lauril', 'sulfato', 'betaina', 'anionico', 'cationico', 'anfotero', 'tensioactivo', 'surfactante', 'glucosido', 'glucoside', 'les', 'adeg', 'detergente', 'anionicos']):
        return "🧼 Surfactantes y Tensioactivos (Aniónicos/Catiónicos)"
    elif any(x in nombre_lower for x in ['esencia', 'fragancia', 'aroma', 'perfume', 'mentol', 'limoneno', 'linalool']):
        return "🌸 Esencias, Perfumes y Fragancias"
    elif any(x in nombre_lower for x in ['silicona', 'dimethicone', 'dimeticona', 'ciclometicona', 'aceite', 'argan', 'ricino', 'almendra', 'mineral', 'glicerina', 'vaselina', 'emoliente']):
        return "💧 Siliconas, Aceites y Emolientes"
    elif any(x in nombre_lower for x in ['queratina', 'keratina', 'pantenol', 'vitamina', 'acido', 'activo', 'extracto', 'aloe', 'colageno', 'proteina', 'aminoacido', 'colageno', 'ceramida']):
        return "✨ Activos Cosméticos y Vitaminas Tratantes"
    elif any(x in nombre_lower for x in ['conservante', 'parabeno', 'benzoato', 'sorbato', 'estabilizante', 'fenoxietanol', 'bht', 'acido citrico', 'ph']):
        return "🛡️ Conservantes, Reguladores de pH y Estabilizadores"
    elif any(x in nombre_lower for x in ['espesante', 'emulsionante', 'alcohol cetilico', 'goma', 'carbopol', 'cera', 'cetearil', 'viscosidad']):
        return "🧬 Espesantes, Emulsionantes y Ceras"
    elif any(x in nombre_lower for x in ['envase', 'pote', 'botella', 'tapa', 'etiqueta', 'caja', 'embalaje', 'vacio', 'valvula', 'spray', 'pomo']):
        return "📦 Envases, Packaging y Etiquetas"
    else:
        return "🧩 Otros Componentes y Aditivos Capilares"

# --- GENERACIÓN DE PDF PROFESIONAL COSMPÉTICO ---
def generate_pdf(df):
    """Genera un reporte PDF profesional agrupando materias primas cosméticas por categoría sin incluir el agua."""
    # Filtrar el DataFrame de entrada para omitir la materia prima "agua" (búsqueda insensible a mayúsculas/minúsculas)
    df_clean = df[~df['nombre'].str.lower().str.contains('agua', na=False)].copy()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter, 
        rightMargin=36, 
        leftMargin=36, 
        topMargin=36, 
        bottomMargin=36
    )
    story = []
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=colors.HexColor('#1E3A8A'),
        spaceAfter=5
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#4B5563'),
        spaceAfter=15
    )
    
    category_title_style = ParagraphStyle(
        'CategoryHeader',
        parent=styles['Heading2'],
        fontSize=13,
        textColor=colors.HexColor('#2563EB'),
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )
    
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontSize=8.5,
        textColor=colors.white,
        fontName='Helvetica-Bold'
    )
    
    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#1F2937')
    )
    
    table_cell_bold_style = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontSize=8,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#111827')
    )

    # 1. Cabecera del Documento
    story.append(Paragraph("MINERVA - CONTROL DE INVENTARIO CAPILAR", title_style))
    story.append(Paragraph(f"<b>Reporte Técnico de Materias Primas por Categoría Química</b><br/>Fecha de Auditoría: {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M:%S')}<br/><i>*Nota: Se excluyen del reporte las cantidades de agua de proceso.</i>", subtitle_style))
    story.append(Spacer(1, 5))
    
    # 2. Resumen Ejecutivo
    story.append(Paragraph("<b>Resumen Ejecutivo de Planta Capilar</b>", category_title_style))
    
    total_items = len(df_clean)
    criticos_items = len(df_clean[df_clean['estado_stock'] == "🚨 CRÍTICO (Falta Stock)"])
    alerta_items = len(df_clean[df_clean['estado_stock'] == "⚠️ ATENCIÓN (Stock Justo)"])
    cubiertos_items = total_items - (criticos_items + alerta_items)

    summary_data = [
        [Paragraph("<b>Indicador Clave de Almacén</b>", table_header_style), Paragraph("<b>Estado Actual</b>", table_header_style)],
        [Paragraph("Total de Materias Primas Evaluadas", table_cell_style), Paragraph(str(total_items), table_cell_bold_style)],
        [Paragraph("Insumos en Estado Crítico (Déficit de Stock)", table_cell_style), Paragraph(f"{criticos_items} (Requiere adquisición urgente)", table_cell_bold_style)],
        [Paragraph("Insumos en Alerta (Nivel Justo de Operación)", table_cell_style), Paragraph(str(alerta_items), table_cell_bold_style)],
        [Paragraph("Insumos con Cobertura Óptima para Producción", table_cell_style), Paragraph(str(cubiertos_items), table_cell_bold_style)]
    ]
    
    summary_table = Table(summary_data, colWidths=[280, 240])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D1D5DB')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F4F6')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 15))

    # 3. Tablas de Insumos por Categoría Capilar
    categories = df_clean['categoria'].unique()
    for cat in sorted(categories):
        df_cat = df_clean[df_clean['categoria'] == cat]
        if df_cat.empty:
            continue
            
        story.append(Paragraph(f"<b>📂 {cat}</b>", category_title_style))
        
        # Cabeceras
        table_data = [[
            Paragraph("<b>ID</b>", table_header_style),
            Paragraph("<b>Insumo Capilar</b>", table_header_style),
            Paragraph("<b>Unidad</b>", table_header_style),
            Paragraph("<b>Stock Disponible</b>", table_header_style),
            Paragraph("<b>Demanda Producción</b>", table_header_style),
            Paragraph("<b>Estado Operativo</b>", table_header_style)
        ]]
        
        for _, row in df_cat.iterrows():
            table_data.append([
                Paragraph(str(row['id']), table_cell_style),
                Paragraph(str(row['nombre']), table_cell_bold_style),
                Paragraph(str(row['unidad']), table_cell_style),
                Paragraph(f"{row['cantidad_actual']:.2f}", table_cell_style),
                Paragraph(f"{row['demanda_total']:.2f}", table_cell_style),
                Paragraph(str(row['estado_stock']), table_cell_style)
            ])
            
        t = Table(table_data, colWidths=[35, 175, 60, 80, 80, 110])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')]),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))
        
    doc.build(story)
    buffer.seek(0)
    return buffer

def get_connection(db_path):
    """Establece conexión con la base de datos SQLite."""
    if not os.path.exists(db_path):
        return None
    try:
        return sqlite3.connect(db_path)
    except Exception as e:
        st.error(f"Error al conectar a la base de datos: {e}")
        return None

def inspect_exact_tables(conn):
    """Obtiene el esquema exacto de las 5 tablas requeridas ignorando mayúsculas y minúsculas."""
    targets = ['recetas', 'receta_ingredientes', 'materias_primas', 'stock_materias_primas', 'pedidos_produccion']
    schema = {}
    cursor = conn.cursor()
    
    # Obtener todas las tablas existentes reales en la base de datos
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    existing_tables = [row[0] for row in cursor.fetchall()]
    
    for target in targets:
        # Búsqueda insensible a mayúsculas/minúsculas
        matched_table = None
        for ext in existing_tables:
            if ext.lower() == target.lower():
                matched_table = ext
                break
        
        if matched_table:
            cursor.execute(f"PRAGMA table_info('{matched_table}')")
            columns = [row[1] for row in cursor.fetchall()]
            schema[target] = {
                'real_name': matched_table,
                'columns': columns
            }
        else:
            schema[target] = {
                'real_name': None,
                'columns': []
            }
    return schema

# --- INTERFAZ SIDEBAR ---
st.sidebar.image("https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&q=80&w=300", caption="Gestión de Planta Capilar", use_container_width=True)
st.sidebar.header("📁 Base de Datos")

db_source = st.sidebar.radio("Selecciona origen de datos:", ["Usar minerva.db local", "Subir archivo .db"])
db_path = DEFAULT_DB_PATH

if db_source == "Subir archivo .db":
    uploaded_file = st.sidebar.file_uploader("Cargar archivo de base de datos", type=["db", "sqlite", "sqlite3"])
    if uploaded_file is not None:
        db_path = f"temp_{uploaded_file.name}"
        with open(db_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

# Validar conexión
conn = get_connection(db_path)

if conn is None:
    st.warning("⚠️ No se pudo cargar la base de datos. Asegúrate de tener el archivo 'minerva.db' en la carpeta de la app o súbelo en la barra lateral.")
    st.stop()

# Obtener esquema de la base de datos para mapeo inteligente
schema = inspect_exact_tables(conn)

# --- DETECTOR INTELIGENTE Y SEGURO DE COLUMNAS (Previene KeyErrors) ---
col_mappings = {}
missing_tables = []

# Validar que existan las tablas indispensables
for t in ['recetas', 'receta_ingredientes', 'materias_primas', 'stock_materias_primas', 'pedidos_produccion']:
    if not schema[t]['real_name']:
        missing_tables.append(t)

if missing_tables:
    st.error(f"❌ Falta una o más tablas requeridas en la base de datos: {', '.join(missing_tables)}")
    st.info("La base de datos debe contener las siguientes tablas para la planta capilar: **recetas** (Fórmulas), **receta_ingredientes** (Composición de Fórmula), **materias_primas** (Insumos Químicos), **stock_materias_primas** and **pedidos_produccion** (Lotes o Pedidos de Productos Capilares).")
    
    # Mostrar las tablas reales que sí existen para ayudar al usuario a diagnosticar
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    real_db_tables = [row[0] for row in cursor.fetchall()]
    st.write("Tablas encontradas actualmente en tu archivo de base de datos:")
    st.code(", ".join(real_db_tables))
    st.stop()

# Si todas las tablas existen, mapeamos sus columnas de manera segura
try:
    # 1. Materias Primas
    mp_info = schema['materias_primas']
    cols_mp = [c.lower() for c in mp_info['columns']]
    col_mappings['mp_id'] = 'id' if 'id' in cols_mp else mp_info['columns'][0]
    col_mappings['mp_nombre'] = 'nombre' if 'nombre' in cols_mp else mp_info['columns'][1] if len(cols_mp) > 1 else mp_info['columns'][0]
    col_mappings['mp_unidad'] = 'unidad' if 'unidad' in cols_mp else (mp_info['columns'][2] if len(cols_mp) > 2 else mp_info['columns'][-1])

    # 2. Stock Materias Primas - Usar estrictamente cantidad_actual para la cantidad real
    stock_info = schema['stock_materias_primas']
    cols_stock = [c.lower() for c in stock_info['columns']]
    
    # Buscar el ID de relación con materia prima
    id_relations = [c for c in stock_info['columns'] if 'materia_prima' in c.lower() or 'mp' in c.lower() or 'id' in c.lower()]
    col_mappings['stock_mp_id'] = id_relations[0] if id_relations else stock_info['columns'][0]
    
    # Campo exacto de cantidad (cantidad_actual solicitado)
    if 'cantidad_actual' in cols_stock:
        col_mappings['stock_cantidad'] = stock_info['columns'][cols_stock.index('cantidad_actual')]
    else:
        cant_cols = [c for c in stock_info['columns'] if 'actual' in c.lower() or 'cant' in c.lower() or 'stock' in c.lower()]
        col_mappings['stock_cantidad'] = cant_cols[0] if cant_cols else (stock_info['columns'][1] if len(stock_info['columns']) > 1 else stock_info['columns'][-1])

    # 3. Recetas (Fórmulas Capilares en la lógica del negocio)
    rec_info = schema['recetas']
    cols_rec = [c.lower() for c in rec_info['columns']]
    col_mappings['receta_id'] = 'id' if 'id' in cols_rec else rec_info['columns'][0]
    col_mappings['receta_nombre'] = 'nombre' if 'nombre' in cols_rec else rec_info['columns'][1] if len(cols_rec) > 1 else rec_info['columns'][0]

    # 4. Receta Ingredientes (Composición de Fórmulas Capilares)
    ri_info = schema['receta_ingredientes']
    cols_ri = [c.lower() for c in ri_info['columns']]
    # Relación con receta
    rec_rel = [c for c in ri_info['columns'] if 'receta' in c.lower()]
    col_mappings['ri_receta_id'] = rec_rel[0] if rec_rel else ri_info['columns'][0]
    # Relación con materia prima
    mp_rel = [c for c in ri_info['columns'] if 'materia_prima' in c.lower() or 'mp' in c.lower()]
    col_mappings['ri_mp_id'] = mp_rel[0] if mp_rel else (ri_info['columns'][1] if len(ri_info['columns']) > 1 else ri_info['columns'][0])
    # Cantidad
    cant_ri = [c for c in ri_info['columns'] if 'cant' in c.lower() or 'peso' in c.lower() or 'vol' in c.lower()]
    col_mappings['ri_cantidad'] = cant_ri[0] if cant_ri else (ri_info['columns'][2] if len(ri_info['columns']) > 2 else ri_info['columns'][-1])

    # 5. Pedidos de Producción
    ped_info = schema['pedidos_produccion']
    cols_ped = [c.lower() for c in ped_info['columns']]
    # Relación con receta en pedidos_produccion
    ped_rec_rel = [c for c in ped_info['columns'] if 'receta' in c.lower()]
    col_mappings['pedido_receta_id'] = ped_rec_rel[0] if ped_rec_rel else ped_info['columns'][0]
    # Cantidad en pedidos_produccion
    ped_cant_cols = [c for c in ped_info['columns'] if 'cant' in c.lower() or 'vol' in c.lower() or 'total' in c.lower() or 'unid' in c.lower()]
    col_mappings['pedido_cantidad'] = ped_cant_cols[0] if ped_cant_cols else (ped_info['columns'][2] if len(ped_info['columns']) > 2 else ped_info['columns'][-1])

except Exception as e:
    st.error(f"❌ Error al mapear de forma automática las columnas de tu base de datos: {e}")
    st.info("Asegúrate de que tus tablas contengan los identificadores correspondientes para relacionarse (ej. receta_id, materia_prima_id).")
    st.stop()

# Mostrar estado de conexión y mapeo exitoso en el Sidebar
st.sidebar.success("✅ Base de Datos Mapeada con Éxito")
with st.sidebar.expander("🔍 Ver Estructura del Modelo Capilar"):
    for t in ['recetas', 'receta_ingredientes', 'materias_primas', 'stock_materias_primas', 'pedidos_produccion']:
        st.write(f"Tabla: **{schema[t]['real_name']}**")
        st.code(", ".join(schema[t]['columns']))

# --- CARGAR Y ANALIZAR DATOS REALES DE MANERA SEGURA ---
try:
    # Comprobación de si existe columna 'categoria' física en la base de datos
    cols_mp = [c.lower() for c in schema['materias_primas']['columns']]
    has_categoria_col = 'categoria' in cols_mp or 'category' in cols_mp
    
    category_select_sql = ""
    if has_categoria_col:
        real_cat_col = 'categoria' if 'categoria' in cols_mp else 'category'
        category_select_sql = f", mp.{real_cat_col} AS categoria"
        
    # 1. Cargar Materias Primas y sus Stocks
    query_stock = f"""
        SELECT 
            mp.{col_mappings['mp_id']} AS id,
            mp.{col_mappings['mp_nombre']} AS nombre,
            mp.{col_mappings['mp_unidad']} AS unidad
            {category_select_sql}
            , COALESCE(smp.{col_mappings['stock_cantidad']}, 0) AS cantidad_actual
        FROM {schema['materias_primas']['real_name']} mp
        LEFT JOIN {schema['stock_materias_primas']['real_name']} smp ON mp.{col_mappings['mp_id']} = smp.{col_mappings['stock_mp_id']}
    """
    df_stock_mp = pd.read_sql_query(query_stock, conn)
    # FORZAR conversión de stock_actual a numérico
    df_stock_mp['cantidad_actual'] = pd.to_numeric(df_stock_mp['cantidad_actual'], errors='coerce').fillna(0.0)

    # 2. Cargar Recetas (Fórmulas Cosméticas)
    df_recetas = pd.read_sql_query(f"SELECT * FROM {schema['recetas']['real_name']}", conn)

    # 3. Cargar Receta_Ingredientes (Composición química por lote)
    df_receta_ingredientes = pd.read_sql_query(f"SELECT * FROM {schema['receta_ingredientes']['real_name']}", conn)
    df_receta_ingredientes[col_mappings['ri_cantidad']] = pd.to_numeric(df_receta_ingredientes[col_mappings['ri_cantidad']], errors='coerce').fillna(0.0)

    # 4. Cargar Pedidos de Producción Capilar y calcular Demanda Real
    query_pedidos = f"""
        SELECT 
            {col_mappings['pedido_receta_id']} AS receta_id,
            SUM({col_mappings['pedido_cantidad']}) AS total_pedido
        FROM {schema['pedidos_produccion']['real_name']}
        GROUP BY {col_mappings['pedido_receta_id']}
    """
    df_pedidos_agrupados = pd.read_sql_query(query_pedidos, conn)
    df_pedidos_agrupados['total_pedido'] = pd.to_numeric(df_pedidos_agrupados['total_pedido'], errors='coerce').fillna(0.0)

    # 5. Calcular la demanda exacta de materia prima capilar basada en los lotes solicitados
    df_demanda = pd.merge(
        df_pedidos_agrupados,
        df_receta_ingredientes,
        left_on='receta_id',
        right_on=col_mappings['ri_receta_id'],
        how='inner'
    )
    
    # Calcular cantidad requerida total de cada insumo químico: (dosificación por lote * cantidad total de lotes)
    df_demanda['demanda_total'] = df_demanda[col_mappings['ri_cantidad']] * df_demanda['total_pedido']
    
    # Agrupar demanda por ID de materia prima
    df_demanda_mp = df_demanda.groupby(col_mappings['ri_mp_id'])['demanda_total'].sum().reset_index()
    df_demanda_mp.rename(columns={col_mappings['ri_mp_id']: 'id'}, inplace=True)

    # Contar cuántas formulaciones activas en pedidos consumen cada insumo químico
    df_frecuencia_mp = df_demanda.groupby(col_mappings['ri_mp_id'])['receta_id'].nunique().reset_index()
    df_frecuencia_mp.rename(columns={col_mappings['ri_mp_id']: 'id', 'receta_id': 'frecuencia_recetas'}, inplace=True)

    # 6. Combinar Stock con la Demanda e Importancia Calculada
    df_final = pd.merge(df_stock_mp, df_demanda_mp, on='id', how='left')
    df_final = pd.merge(df_final, df_frecuencia_mp, on='id', how='left')
    
    df_final['demanda_total'] = pd.to_numeric(df_final['demanda_total'], errors='coerce').fillna(0.0)
    df_final['frecuencia_recetas'] = df_final['frecuencia_recetas'].fillna(0).astype(int)

    # Aplicar categorización inteligente capilar (física de DB o dinámica)
    if 'categoria' in df_stock_mp.columns:
        df_final['categoria'] = df_final['categoria'].fillna("🧩 Otros Componentes y Aditivos Capilares")
    else:
        df_final['categoria'] = df_final['nombre'].apply(categorizar_materia_prima)

    # Calcular indicador de Cobertura de Lotes (Stock / Demanda)
    df_final['factor_cobertura'] = df_final.apply(
        lambda row: float(row['cantidad_actual']) / float(row['demanda_total']) if row['demanda_total'] > 0 else float('inf'),
        axis=1
    )

    # Definir Estados de Abastecimiento en Planta Capilar
    def evaluar_estado(row):
        if row['demanda_total'] > 0:
            if row['cantidad_actual'] < row['demanda_total']:
                return "🚨 CRÍTICO (Falta Stock)"
            elif row['factor_cobertura'] <= 1.3:
                return "⚠️ ATENCIÓN (Stock Justo)"
            else:
                return "✅ CUBIERTO"
        return "ℹ️ Sin demanda activa"

    df_final['estado_stock'] = df_final.apply(evaluar_estado, axis=1)

    # Calcular Importancia Operativa (Prioridad Cosmética) basada en la demanda de lotes activos
    max_demanda = df_final['demanda_total'].max()
    def evaluar_importancia(demanda):
        if max_demanda == 0 or demanda == 0:
            return "Prioridad Baja"
        pct = demanda / max_demanda
        if pct >= 0.6:
            return "🔥 Máxima Prioridad (Bloqueante de Línea)"
        elif pct >= 0.2:
            return "⚡ Importancia Regular"
        else:
            return "💤 Aditivos Secundarios"

    df_final['importancia_produccion'] = df_final['demanda_total'].apply(evaluar_importancia)

except Exception as e:
    st.error(f"❌ Error procesando las relaciones lógicas de la base de datos: {e}")
    st.info("Asegúrate de que los IDs y claves foráneas coincidan entre las tablas de recetas, pedidos_produccion e ingredientes.")
    st.stop()


# --- PANEL DE CONTROL PRINCIPAL (UI) ---

st.title("🧪 Minerva - Control de Inventario Capilar e Importancia")
st.write("Análisis dinámico de materias primas cosméticas (esencias, tensioactivos, activos) basado en los lotes de producción actuales de tus fórmulas.")

# Métricas rápidas
m1, m2, m3, m4 = st.columns(4)
total_mp = len(df_final)
insumos_faltantes = len(df_final[df_final['estado_stock'] == "🚨 CRÍTICO (Falta Stock)"])
total_pedidos = int(df_pedidos_agrupados['total_pedido'].sum()) if not df_pedidos_agrupados.empty else 0
insumos_activos = len(df_final[df_final['demanda_total'] > 0])

with m1:
    st.markdown(f"""
    <div class="metric-card">
        <small style="color: #6B7280; font-weight: 500;">Insumos Capilares Totales</small>
        <h2 style="margin: 0; color: #1F2937;">{total_mp}</h2>
        <span style="font-size: 0.8rem; color: #3B82F6;">Registrados en almacén</span>
    </div>
    """, unsafe_allow_html=True)

with m2:
    style_class = "metric-card-alert" if insumos_faltantes > 0 else ""
    st.markdown(f"""
    <div class="metric-card {style_class}">
        <small style="color: #6B7280; font-weight: 500;">Insumos en Quiebre (Déficit)</small>
        <h2 style="margin: 0; color: #EF4444;">{insumos_faltantes}</h2>
        <span style="font-size: 0.8rem; color: #EF4444;">Paralizan líneas de producción</span>
    </div>
    """, unsafe_allow_html=True)

with m3:
    st.markdown(f"""
    <div class="metric-card">
        <small style="color: #6B7280; font-weight: 500;">Insumos Comprometidos</small>
        <h2 style="margin: 0; color: #10B981;">{insumos_activos}</h2>
        <span style="font-size: 0.8rem; color: #10B981;">Bajo demanda de formulación</span>
    </div>
    """, unsafe_allow_html=True)

with m4:
    st.markdown(f"""
    <div class="metric-card">
        <small style="color: #6B7280; font-weight: 500;">Lotes Totales Solicitados</small>
        <h2 style="margin: 0; color: #8B5CF6;">{total_pedidos}</h2>
        <span style="font-size: 0.8rem; color: #8B5CF6;">Fórmulas capilares en cola</span>
    </div>
    """, unsafe_allow_html=True)


# --- PESTAÑAS DE NAVEGACIÓN ---
tab1, tab2, tab3 = st.tabs([
    "📋 Inventario Físico de Planta",
    "🎯 Prioridades y Matriz de Abastecimiento",
    "🧪 Simulador de Nuevas Fórmulas y Lotes"
])

# --- PESTAÑA 1: STOCK ACTUAL ---
with tab1:
    st.subheader("📦 Estado de Inventario Químico y Capilar")
    st.write("Visualización directa de la cantidad en existencia (`cantidad_actual`) de tus insumos capilares en planta, categorizados de forma técnica.")
    
    # Buscador, filtros y sección de descarga de Reporte PDF
    f_col1, f_col2, f_col3 = st.columns([2, 1, 1])
    with f_col1:
        search = st.text_input("🔍 Filtrar por nombre de insumo (ej: lauril, esencia, dimeticona):", "").lower()
    with f_col2:
        estado_filter = st.selectbox("Filtrar por Disponibilidad en Planta:", ["Todos", "🚨 CRÍTICO (Falta Stock)", "⚠️ ATENCIÓN (Stock Justo)", "✅ CUBIERTO", "ℹ️ Sin demanda activa"])
    with f_col3:
        st.write("")  # Espaciadores para alinear el botón verticalmente
        st.write("")
        if REPORTLAB_AVAILABLE:
            try:
                pdf_data = generate_pdf(df_final)
                st.download_button(
                    label="📄 Descargar Ficha Técnica PDF",
                    data=pdf_data,
                    file_name="reporte_insumos_capilares_por_categoria.pdf",
                    mime="application/pdf",
                    key="pdf_download_btn",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Fallo al generar el PDF: {e}")
        else:
            # Fallback a CSV
            csv = df_final.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Exportar Reporte Técnico (CSV)",
                data=csv,
                file_name="reporte_insumos_capilares.csv",
                mime="text/csv",
                key="csv_download_btn",
                use_container_width=True
            )

    df_filtered_stock = df_final.copy()
    if search:
        df_filtered_stock = df_filtered_stock[df_filtered_stock['nombre'].str.lower().str.contains(search)]
    if estado_filter != "Todos":
        df_filtered_stock = df_filtered_stock[df_filtered_stock['estado_stock'] == estado_filter]

    # Presentación limpia de la tabla de stock
    df_view_stock = df_filtered_stock[['id', 'nombre', 'categoria', 'unidad', 'cantidad_actual', 'estado_stock']].copy()
    df_view_stock.columns = ["ID Insumo", "Materia Prima / Insumo Capilar", "Categoría Química", "Unidad", "Stock Actual (cantidad_actual)", "Estado Operativo"]
    
    st.dataframe(
        df_view_stock,
        column_config={
            "Stock Actual (cantidad_actual)": st.column_config.NumberColumn(format="%.2f"),
        },
        hide_index=True,
        use_container_width=True
    )

    # Gráfico de barras de Stock Actual agrupado por Categoría
    if not df_filtered_stock.empty:
        fig_stock = px.bar(
            df_filtered_stock,
            x='nombre',
            y='cantidad_actual',
            color='categoria',
            title="Distribución de Niveles de Stock por Categoría Capilar",
            labels={'nombre': 'Insumo Capilar', 'cantidad_actual': 'Cantidad en Existencia', 'categoria': 'Grupo Técnico'}
        )
        st.plotly_chart(fig_stock, use_container_width=True)

# --- PESTAÑA 2: IMPORTANCIA Y DEMANDA ---
with tab2:
    st.subheader("🎯 Matriz de Prioridad e Importancia Operativa")
    st.write("""
    Esta vista identifica qué componentes son estratégicamente determinantes según la demanda generada por tus formulaciones en proceso de fabricación. 
    Cruza los lotes de la tabla **pedidos_produccion** con el desglose porcentual de **receta_ingredientes** para predecir cuellos de botella.
    """)

    # Filtrar solo insumos que tienen demanda real para analizar importancia de producción
    df_active = df_final[df_final['demanda_total'] > 0].sort_values(by='demanda_total', ascending=False)

    if not df_active.empty:
        # Gráfico comparativo de Demanda vs Stock
        fig_compare = go.Figure()
        fig_compare.add_trace(go.Bar(
            name='Demanda Requerida para Lotes',
            x=df_active['nombre'],
            y=df_active['demanda_total'],
            marker_color='#3B82F6'
        ))
        fig_compare.add_trace(go.Bar(
            name='Stock Físico Disponible',
            x=df_active['nombre'],
            y=df_active['cantidad_actual'],
            marker_color='#10B981'
        ))
        fig_compare.update_layout(
            barmode='group',
            title='Consumo Esperado de Insumos vs Stock Actual en Almacén',
            xaxis_title='Insumo Capilar',
            yaxis_title='Cantidad',
            xaxis_tickangle=-45
        )
        st.plotly_chart(fig_compare, use_container_width=True)

        # Matriz de prioridades
        st.subheader("📋 Plan de Abastecimiento de Insumos Críticos")
        df_view_active = df_active[[
            'id', 'nombre', 'categoria', 'unidad', 'frecuencia_recetas', 'demanda_total', 
            'cantidad_actual', 'importancia_produccion', 'estado_stock'
        ]].copy()
        
        df_view_active.columns = [
            "ID Insumo", "Insumo Capilar", "Categoría Química", "Unidad", "Formulaciones que lo Utilizan", 
            "Cantidad Requerida", "Stock Disponible", "Prioridad Operativa", "Estado de Abasto"
        ]

        st.dataframe(
            df_view_active,
            column_config={
                "Cantidad Requerida": st.column_config.NumberColumn(format="%.2f"),
                "Stock Disponible": st.column_config.NumberColumn(format="%.2f")
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("No se registran lotes o pedidos activos en el sistema para calcular la demanda de materias primas.")

# --- PESTAÑA 3: SIMULADOR DE PRODUCCIÓN ---
with tab3:
    st.subheader("🧪 Simulador de Nuevos Lotes Capilares")
    st.write("Planifica la fabricación de nuevas formulaciones capilares para evaluar instantáneamente qué insumos químicos y envases se agotarán, y calcula el déficit de compra.")

    if not df_recetas.empty and not df_receta_ingredientes.empty:
        st.markdown("### 1. Establece la cantidad de lotes a simular por cada Fórmula Capilar:")
        col_s1, col_s2 = st.columns(2)
        sim_inputs = {}

        # Generar controles dinámicos para simular la producción de cada formulación capilar
        for i, row in df_recetas.iterrows():
            r_id = row[col_mappings['receta_id']]
            r_name = row[col_mappings['receta_nombre']]
            
            with (col_s1 if i % 2 == 0 else col_s2):
                sim_inputs[r_id] = st.number_input(
                    f"Fórmula: {r_name} (Lotes a Fabricar)",
                    min_value=0,
                    value=0,
                    step=1,
                    key=f"sim_rec_{r_id}"
                )

        if st.button("🚀 Simular Demanda de Lote y Analizar Viabilidad", type="primary"):
            # Generar lista de simulación
            sim_list = [{'receta_id': r_id, 'cantidad': qty} for r_id, qty in sim_inputs.items() if qty > 0]
            df_sim_pedidos = pd.DataFrame(sim_list)

            if not df_sim_pedidos.empty:
                # Cruzar con fórmulas e ingredientes
                df_sim_merged = pd.merge(
                    df_sim_pedidos,
                    df_receta_ingredientes,
                    left_on='receta_id',
                    right_on=col_mappings['ri_receta_id'],
                    how='inner'
                )
                
                # Calcular consumo proyectado
                df_sim_merged[col_mappings['ri_cantidad']] = pd.to_numeric(df_sim_merged[col_mappings['ri_cantidad']], errors='coerce').fillna(0.0)
                df_sim_merged['cantidad'] = pd.to_numeric(df_sim_merged['cantidad'], errors='coerce').fillna(0.0)
                
                df_sim_merged['consumo_simulado'] = df_sim_merged[col_mappings['ri_cantidad']] * df_sim_merged['cantidad']
                df_sim_res = df_sim_merged.groupby(col_mappings['ri_mp_id'])['consumo_simulado'].sum().reset_index()
                df_sim_res.rename(columns={col_mappings['ri_mp_id']: 'id'}, inplace=True)

                # Cruzar con stock actual
                df_sim_final = pd.merge(df_stock_mp, df_sim_res, on='id', how='left')
                df_sim_final['consumo_simulado'] = pd.to_numeric(df_sim_final['consumo_simulado'], errors='coerce').fillna(0.0)
                df_sim_final['cantidad_actual'] = pd.to_numeric(df_sim_final['cantidad_actual'], errors='coerce').fillna(0.0)
                
                # Calcular inventario final proyectado
                df_sim_final['stock_proyectado'] = df_sim_final['cantidad_actual'] - df_sim_final['consumo_simulado']
                df_sim_final['deficit'] = df_sim_final['stock_proyectado'].apply(lambda x: abs(x) if x < 0 else 0.0)
                df_sim_final['viabilidad'] = df_sim_final['stock_proyectado'].apply(lambda x: "✅ Stock Suficiente" if x >= 0 else "❌ Faltante")

                # Mostrar resultados filtrando solo las materias primas consumidas
                df_sim_activos = df_sim_final[df_sim_final['consumo_simulado'] > 0]

                if not df_sim_activos.empty:
                    faltantes_count = len(df_sim_activos[df_sim_activos['stock_proyectado'] < 0])
                    if faltantes_count == 0:
                        st.success("🎉 ¡Viabilidad Exitosa! Tienes suficiente stock en planta para fabricar todos los lotes simulados sin compras adicionales.")
                    else:
                        st.error(f"⚠️ Alerta de Suministro: Tienes {faltantes_count} insumos químicos/envases en desabastecimiento para cumplir con la producción.")

                    # Tabla de resultados
                    df_sim_view = df_sim_activos[['nombre', 'unidad', 'cantidad_actual', 'consumo_simulado', 'stock_proyectado', 'deficit', 'viabilidad']].copy()
                    df_sim_view.columns = ["Insumo / Materia Prima", "Unidad", "Stock Inicial", "Consumo en Simulación", "Stock Final Proyectado", "Déficit a Comprar", "Evaluación"]
                    
                    st.dataframe(
                        df_sim_view,
                        column_config={
                            "Stock Inicial": st.column_config.NumberColumn(format="%.2f"),
                            "Consumo en Simulación": st.column_config.NumberColumn(format="%.2f"),
                            "Stock Final Proyectado": st.column_config.NumberColumn(format="%.2f"),
                            "Déficit a Comprar": st.column_config.NumberColumn(format="%.2f")
                        },
                        hide_index=True,
                        use_container_width=True
                    )

                    # Gráfico de simulación
                    fig_sim = go.Figure()
                    fig_sim.add_trace(go.Bar(
                        name='Stock Físico',
                        x=df_sim_activos['nombre'],
                        y=df_sim_activos['cantidad_actual'],
                        marker_color='#10B981'
                    ))
                    fig_sim.add_trace(go.Bar(
                        name='Consumo de Lotes Proyectado',
                        x=df_sim_activos['nombre'],
                        y=df_sim_activos['consumo_simulado'],
                        marker_color='#EF4444'
                    ))
                    fig_sim.update_layout(
                        barmode='group',
                        title='Simulación de Consumo Químico sobre el Stock de Planta',
                        xaxis_title='Insumo Capilar',
                        yaxis_title='Cantidad'
                    )
                    st.plotly_chart(fig_sim, use_container_width=True)

                else:
                    st.info("La simulación no requiere materias primas configuradas.")
            else:
                st.warning("Por favor introduce una cantidad de lotes mayor a cero en alguna fórmula.")
    else:
        st.warning("No hay formulaciones capilares disponibles en la base de datos para simular.")

# Cerrar conexión de base de datos de forma limpia
conn.close()