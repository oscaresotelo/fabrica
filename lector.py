import streamlit as st
import pandas as pd
import sqlite3
import re
import io
from difflib import SequenceMatcher
import os

# Try importing pypdf for PDF text extraction
try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

st.set_page_config(
    page_title="Calculador de Materia Prima Bekim",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_PATH = "minerva.db"

# List of keywords that belong to non-recipe invoice lines (to be filtered out)
NON_RECIPE_KEYWORDS = [
    'flete', 'fletes', 'transporte', 'envio', 'envios', 'gastos', 'cargo', 'cargos',
    'comision', 'comisiones', 'interes', 'intereses', 'telefono', 'telefonos', 
    'honorarios', 'servicio', 'servicios', 'percepcion', 'percepciones', 
    'impuesto', 'impuestos', 'retencion', 'retenciones', 'descuento', 'recargo',
    'subtotal', 'total (neto)', 'impuesto total', 'total (incl. imp.)', 'total', 
    'iva', 'cuit', 'cae', 'vencimiento', 'factura', 'remito',
    'condicion', 'pagina', 'ingresos brutos', 'i.v.a.', 'i.v.a', 'bonificacion',
    'sucursal', 'orden de compra', 'pago', 'contado', 'cuenta corriente',
    'descripción', 'prec. unit.', 'monto en la moneda'
]

# Words to ignore when matching recipe strings to filter out noise
NOISE_WORDS = {
    'bekim', 'capilar', 'litros', 'litro', 'lts', 'lt', 'x', 'kilo', 'kilos', 
    'kg', '1k', '500ml', '1l', '5l', 'dto', 'iva', 'mp', 'mat', 'materia', 
    'prima', 'matprima', 'prod', 'producto', 'bidon', 'tambor', 'botella',
    'c', 's', 'frag', 'fragancia', 'c/frag', 's/frag', 'sh', 'af', 'color'
}

def is_non_recipe_keyword(text_lower):
    """Checks if text contains non-recipe keywords using word boundaries for single words."""
    for kw in NON_RECIPE_KEYWORDS:
        if ' ' in kw or '(' in kw or '.' in kw:
            if kw in text_lower:
                return True
        else:
            if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                return True
    return False

def get_db_connection():
    """Returns a connection to the local SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def populate_sample_bekim_data(conn):
    """Populates standard Bekim recipes and raw materials if database is blank."""
    cursor = conn.cursor()
    
    # Clientes
    cursor.execute("INSERT OR IGNORE INTO clientes (id, nombre, contacto) VALUES (1, 'BEKIM CAPILAR', 'contacto@bekim.com');")
    
    # Raw materials catalog
    mats = [
        (1, "Base Shampoo Sulfatada", "kg"),
        (2, "Aceite de Argan Puro", "kg"),
        (3, "Manteca de Karite", "kg"),
        (4, "Pigmento Violeta Capilar", "kg"),
        (5, "Pigmento Azul Capilar", "kg"),
        (6, "Agua Desmineralizada", "kg"),
        (7, "Conservante DMDM", "kg"),
        (8, "Fragancia Argan", "kg"),
        (9, "Fragancia Coco/Karite", "kg"),
        (10, "Acido Citrico", "kg"),
        (11, "Keratina Hidrolizada", "kg"),
        (12, "Aceite de Cacao Capilar", "kg"),
        (13, "Agente Alisante Glioxilico", "kg"),
        (14, "Silicona Acondicionadora", "kg")
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO materias_primas (id, nombre, unidad) 
        VALUES (?, ?, ?);
    """, mats)
    
    stocks = [
        (1, 10000.0, 8500.0),
        (2, 500.0, 320.0),
        (3, 500.0, 210.0),
        (4, 200.0, 110.0),
        (5, 200.0, 95.0),
        (6, 50000.0, 42000.0),
        (7, 300.0, 180.0),
        (8, 200.0, 120.0),
        (9, 200.0, 100.0),
        (10, 300.0, 250.0),
        (11, 400.0, 280.0),
        (12, 300.0, 190.0),
        (13, 1000.0, 750.0),
        (14, 500.0, 380.0)
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO stock_materias_primas (materia_prima_id, cantidad, cantidad_actual)
        VALUES (?, ?, ?);
    """, stocks)
    
    # Recipes matching products from Bekim invoices (including SI2609-1230 items)
    recipes = [
        (1, "SHAMPOO ARGAN - BEKIM CAPILAR", 1, "Bekim Capilar"),
        (2, "MASCARA ARGAN - BEKIM CAPILAR", 1, "Bekim Capilar"),
        (3, "MASCARA KARITE - BEKIM CAPILAR", 1, "Bekim Capilar"),
        (4, "SHAMPOO KARITE - BEKIM CAPILAR", 1, "Bekim Capilar"),
        (5, "MASCARA MATIZADORA VIOLETA", 1, "Bekim Capilar"),
        (6, "SHAMPOO MATIZADOR VIOLETA BEKIM", 1, "Bekim Capilar"),
        (7, "SHAMPOO EQUILIBRIO PH", 1, "Bekim Capilar"),
        (8, "MASCARA AFTER COLOR", 1, "Bekim Capilar"),
        (9, "SHAMPOO AFTER COLOR", 1, "Bekim Capilar"),
        (10, "SHAMPOO CONTROL", 1, "Bekim Capilar"),
        (11, "MASCARA CONTROL", 1, "Bekim Capilar"),
        (12, "ARGAN LISS", 1, "Bekim Capilar"),
        (13, "ALISADO PLASTIFICADO", 1, "Bekim Capilar"),
        (14, "BOTTOX CAPILAR", 1, "Bekim Capilar"),
        (15, "COMPLEX KERATIN", 1, "Bekim Capilar"),
        (16, "TRATAMIENTO CACAO", 1, "Bekim Capilar"),
        (17, "LIX PLEX TRATAMIENTO", 1, "Bekim Capilar"),
        (18, "MASCARA 5.4", 1, "Bekim Capilar"),
        (19, "SHAMPOO 5.4", 1, "Bekim Capilar"),
        (20, "CREMA DE PEINAR 5.4", 1, "Bekim Capilar"),
        (21, "ACONDICIONADOR 5.4", 1, "Bekim Capilar")
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO recetas (id, nombre, cliente_id, linea) VALUES (?, ?, ?, ?);
    """, recipes)
    
    # Formula proportions per liter of finished product
    ings = [
        (1, 1, 0.25, "kg"), (1, 2, 0.03, "kg"), (1, 6, 0.70, "kg"), (1, 8, 0.01, "kg"),
        (2, 14, 0.15, "kg"), (2, 2, 0.04, "kg"), (2, 6, 0.78, "kg"), (2, 8, 0.01, "kg"),
        (3, 3, 0.12, "kg"), (3, 6, 0.80, "kg"), (3, 9, 0.015, "kg"),
        (4, 1, 0.25, "kg"), (4, 3, 0.02, "kg"), (4, 6, 0.71, "kg"),
        (5, 4, 0.025, "kg"), (5, 14, 0.15, "kg"), (5, 6, 0.80, "kg"),
        (6, 1, 0.25, "kg"), (6, 4, 0.020, "kg"), (6, 6, 0.71, "kg"),
        (7, 1, 0.28, "kg"), (7, 10, 0.015, "kg"), (7, 6, 0.70, "kg"),
        (12, 13, 0.10, "kg"), (12, 2, 0.03, "kg"), (12, 6, 0.85, "kg"),
        (13, 13, 0.15, "kg"), (13, 11, 0.05, "kg"), (13, 6, 0.78, "kg"),
        (14, 11, 0.08, "kg"), (14, 14, 0.10, "kg"), (14, 6, 0.80, "kg"),
        (15, 11, 0.12, "kg"), (15, 6, 0.86, "kg"),
        (16, 12, 0.08, "kg"), (16, 14, 0.10, "kg"), (16, 6, 0.80, "kg"),
        (17, 11, 0.10, "kg"), (17, 13, 0.08, "kg"), (17, 6, 0.80, "kg"),
        (18, 14, 0.15, "kg"), (18, 6, 0.80, "kg"),
        (19, 1, 0.25, "kg"), (19, 6, 0.72, "kg"),
        (21, 14, 0.12, "kg"), (21, 6, 0.85, "kg")
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO receta_ingredientes (receta_id, materia_prima_id, cantidad, unidad)
        VALUES (?, ?, ?, ?);
    """, ings)
    
    conn.commit()

def init_database_tables():
    """Ensures database tables exist and checks schema integrity."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Clientes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            contacto TEXT
        )
    """)
    
    # 2. Recetas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cliente_id INTEGER,
            uso TEXT,
            linea TEXT,
            procedimientos TEXT,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        )
    """)
    
    # 3. Materias Primas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materias_primas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            unidad TEXT NOT NULL,
            UNIQUE(nombre, unidad)
        )
    """)
    
    # 4. Receta Ingredientes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS receta_ingredientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receta_id INTEGER NOT NULL,
            materia_prima_id INTEGER NOT NULL,
            cantidad REAL NOT NULL,
            unidad TEXT NOT NULL,
            FOREIGN KEY(materia_prima_id) REFERENCES materias_primas(id),
            FOREIGN KEY(receta_id) REFERENCES recetas(id)
        )
    """)
    
    # 5. Stock Materias Primas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_materias_primas (
            materia_prima_id INTEGER PRIMARY KEY,
            cantidad REAL NOT NULL,
            cantidad_actual REAL DEFAULT 0,
            FOREIGN KEY(materia_prima_id) REFERENCES materias_primas(id)
        )
    """)
    
    # 6. Alias Recetas PDF (Memory table for persistent invoice mapping)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alias_recetas_pdf (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descripcion_pdf TEXT NOT NULL UNIQUE,
            receta_id INTEGER NOT NULL,
            receta_nombre TEXT NOT NULL,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(receta_id) REFERENCES recetas(id)
        )
    """)

    conn.commit()
    
    # Populate initial sample data if recipes table is empty
    cursor.execute("SELECT COUNT(*) FROM recetas;")
    if cursor.fetchone()[0] == 0:
        populate_sample_bekim_data(conn)

    conn.close()

def get_remembered_aliases():
    """Loads previously saved PDF string mappings from database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT descripcion_pdf, receta_id, receta_nombre FROM alias_recetas_pdf")
        rows = cursor.fetchall()
        aliases = {row['descripcion_pdf'].strip().upper(): (row['receta_id'], row['receta_nombre']) for row in rows}
    except Exception:
        aliases = {}
    finally:
        conn.close()
    return aliases

def save_alias(descripcion_pdf, receta_id, receta_nombre):
    """Saves or updates a PDF description to recipe binding in the database."""
    if not descripcion_pdf or receta_id is None:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO alias_recetas_pdf (descripcion_pdf, receta_id, receta_nombre)
            VALUES (?, ?, ?)
            ON CONFLICT(descripcion_pdf) DO UPDATE SET
                receta_id=excluded.receta_id,
                receta_nombre=excluded.receta_nombre,
                fecha_creacion=CURRENT_TIMESTAMP
        """, (descripcion_pdf.strip().upper(), receta_id, receta_nombre))
        conn.commit()
    except Exception as e:
        st.warning(f"No se pudo guardar el alias en memoria: {e}")
    finally:
        conn.close()

def extract_text_from_pdf_file(uploaded_file):
    """Extracts plain text content from an uploaded PDF invoice file."""
    text_content = ""
    try:
        # Try PyPDF / pypdf
        import pypdf
        reader = pypdf.PdfReader(uploaded_file)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text_content += extracted + "\n"
    except Exception:
        try:
            # Fallback to PyPDF2
            import PyPDF2
            uploaded_file.seek(0)
            reader = PyPDF2.PdfReader(uploaded_file)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text_content += extracted + "\n"
        except Exception:
            try:
                # Fallback to pdfplumber
                import pdfplumber
                uploaded_file.seek(0)
                with pdfplumber.open(uploaded_file) as pdf:
                    for page in pdf.pages:
                        extracted = page.extract_text()
                        if extracted:
                            text_content += extracted + "\n"
            except Exception as e:
                st.error(f"Error al leer el archivo PDF: {e}")
                return ""
    return text_content

def clean_number(num_str):
    """Converts Argentine number formats (e.g., '1.250,50' or '200,00') to float."""
    if not num_str:
        return None
    num_str = num_str.strip().replace('$', '').replace('%', '')
    if ',' in num_str and '.' in num_str:
        if num_str.rfind(',') > num_str.rfind('.'):  # 1.250,50 -> 1250.50
            num_str = num_str.replace('.', '').replace(',', '.')
        else:  # 1,250.50 -> 1250.50
            num_str = num_str.replace(',', '')
    elif ',' in num_str:  # 200,00 -> 200.00
        num_str = num_str.replace(',', '.')
    
    try:
        val = float(num_str)
        return val
    except ValueError:
        return None

def is_known_header_or_footer(line):
    """Checks if line is header, footer, table column header or metadata in invoices."""
    line_lower = line.lower().strip()
    
    # Check table column header specific patterns
    if 'descripción' in line_lower and ('prec. unit.' in line_lower or 'cantidad' in line_lower or 'iva' in line_lower):
        return True
        
    headers_footers = [
        'factura', 'ref. proveedor', 'código de proveedor', 'ref. pedido',
        'teléfono', 'correo', 'dolar a', 'monto en la moneda',
        'total (neto)', 'impuesto total', 'total (incl. imp.)', 'ingresos brutos',
        'hoja', 'página', 'subtotal', 'cuit', 'cae', 'vencimiento', 'calle 132',
        'berazategui', 'bekim cosmetica capilar'
    ]
    
    # Exact totals at bottom of table
    if line_lower.startswith('| total') or line_lower.startswith('| impuesto') or line_lower.startswith('total (neto)'):
        return True

    return any(hf in line_lower for hf in headers_footers)

def prepare_invoice_lines(raw_text):
    """
    Cleans raw PDF text, strips table pipes (|), and joins multi-line item descriptions.
    Handles both standard text layouts and markdown table formats (SI2609-1230 design).
    """
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
    merged_lines = []
    buffer = ""

    num_end_pattern = re.compile(
        r'-?\$?\d{1,3}(?:[\.,]\d{3})*(?:[\.,]\d+)?%?\s+-?\$?\d{1,3}(?:[\.,]\d{3})*(?:[\.,]\d+)?%?\s*$'
    )

    for line in lines:
        # Strip table markdown pipes if present (e.g. "| MP-019-MAT... | 0% | 2.019,60 | 1800 | 3.635.280,00 |")
        clean_line = line.strip()
        if clean_line.startswith('|') and clean_line.endswith('|'):
            # Replace inner pipes with space for uniform parsing
            clean_line = " ".join([seg.strip() for seg in clean_line.split('|') if seg.strip()])
        elif clean_line.startswith('|'):
            clean_line = clean_line.lstrip('|').strip()

        if is_known_header_or_footer(clean_line):
            if buffer:
                merged_lines.append(buffer)
                buffer = ""
            continue

        if buffer:
            line_to_check = buffer + " " + clean_line
        else:
            line_to_check = clean_line

        if num_end_pattern.search(line_to_check):
            merged_lines.append(line_to_check)
            buffer = ""
        else:
            # If line doesn't end with numeric columns, check if it starts a new item code
            if buffer and re.match(r'^(?:MP|mp|mat)[-_\s]?\d+', clean_line, re.I):
                merged_lines.append(buffer)
                buffer = clean_line
            else:
                buffer = line_to_check

    if buffer:
        merged_lines.append(buffer)

    return merged_lines

def extract_recipe_item_from_line(line):
    """
    Parses a single invoice line from right to left (Columns -> Quantity -> Description).
    Handles both 5-column layout [IVA, Price, Cant, Dto, Total] and 4-column layout [IVA, Price, Cant, Total].
    """
    # Remove remaining pipes and clean string
    line_str = line.replace('|', ' ').strip()
    line_str = re.sub(r'\s+', ' ', line_str)
    
    if not line_str or len(line_str) < 5:
        return None
    
    line_lower = line_str.lower()
    
    # 1. Filter non-recipe lines (flete, honorarios, servicios, etc.)
    if is_non_recipe_keyword(line_lower):
        return None

    tokens = line_str.split()
    if len(tokens) < 2:
        return None

    # Collect numeric column tokens starting from the RIGHT side of line
    num_pattern = re.compile(r'^-?\$?\d{1,3}(?:[\.,]\d{3})*(?:[\.,]\d+)?%?$|^\d+(?:[\.,]\d+)?%?$')
    
    num_tokens = []
    desc_tokens = list(tokens)
    
    while desc_tokens:
        last_tok = desc_tokens[-1]
        if num_pattern.match(last_tok):
            num_tokens.insert(0, desc_tokens.pop())
        else:
            break
            
    if not num_tokens:
        return None
        
    raw_desc = " ".join(desc_tokens).strip()
    if not raw_desc or len(raw_desc) < 3:
        return None
        
    desc_lower = raw_desc.lower()
    if is_non_recipe_keyword(desc_lower):
        return None

    # Clean product code prefixes (e.g., "MP-019-", "MP-040 - ", "mp-44 - ")
    clean_desc = re.sub(r'^(?:MP|mp|mat|prod)[-_\s]*\d+[-_\s]*', '', raw_desc, flags=re.I).strip()
    clean_desc = re.sub(r'^[a-zA-Z0-9_-]+\s*[-–:]\s*', '', clean_desc).strip()
    if not clean_desc:
        clean_desc = raw_desc

    # Parse column values
    parsed_vals = []
    for t in num_tokens:
        clean_t = t.replace('%', '').replace('$', '')
        v = clean_number(clean_t)
        if v is not None:
            parsed_vals.append({'raw': t, 'val': v, 'is_pct': '%' in t})

    if not parsed_vals:
        return None

    cantidad_litros = None

    # Layout parsing logic:
    # Format A (5 values): [IVA%, Price, Cantidad, Dto%, Total]
    # Format B (4 values): [IVA%, Price, Cantidad, Total]
    if len(parsed_vals) >= 5:
        p_price = parsed_vals[-4]['val']
        p_cant = parsed_vals[-3]['val']
        p_dto = parsed_vals[-2]['val']
        p_total = parsed_vals[-1]['val']
        
        # Validation: Price * Cant * (1 - Dto/100) ~= Total
        if abs(p_price * p_cant * (1.0 - p_dto / 100.0) - p_total) < 100.0 or abs(p_price * p_cant - p_total) < 100.0:
            cantidad_litros = p_cant
        else:
            cantidad_litros = p_cant
            
    elif len(parsed_vals) == 4:
        v0, v1, v2, v3 = [p['val'] for p in parsed_vals]
        # Check Design SI2609-1230: [IVA% (0), Price (2019.60), Cantidad (1800), Total (3635280.00)]
        if abs(v1 * v2 - v3) < 100.0:
            cantidad_litros = v2
        # Alternative [Price, Cantidad, Dto%, Total]
        elif abs(v0 * v1 * (1.0 - v2 / 100.0) - v3) < 100.0 or abs(v0 * v1 - v3) < 100.0:
            cantidad_litros = v1
        else:
            # Default to 3rd column if 4 columns present [IVA, UnitPrice, Quantity, Total]
            cantidad_litros = v2
            
    elif len(parsed_vals) == 3:
        v0, v1, v2 = [p['val'] for p in parsed_vals]
        # Check [UnitPrice, Cantidad, Total]
        if abs(v0 * v1 - v2) < 100.0:
            cantidad_litros = v1
        else:
            cantidad_litros = v1
            
    elif len(parsed_vals) == 2:
        cantidad_litros = parsed_vals[0]['val']
    else:
        cantidad_litros = parsed_vals[0]['val']

    if clean_desc and cantidad_litros is not None and cantidad_litros > 0:
        return {
            'descripcion': clean_desc,
            'cantidad': cantidad_litros,
            'linea_original': line_str
        }
        
    return None

def parse_invoice_text(text):
    """Iterates through invoice text and extracts valid recipe order lines."""
    items = []
    lines = prepare_invoice_lines(text)
    for line in lines:
        parsed = extract_recipe_item_from_line(line)
        if parsed:
            items.append(parsed)
    return items

def normalize_text(text):
    """Normalizes string for comparison by removing accents, codes, and noise words."""
    if not text:
        return ""
    text = text.lower()
    # Remove product codes like mp-040, mp-44, mp_01, mp-019
    text = re.sub(r'\bmp[-_.\s]?\d+\b', '', text)
    # Remove volume indicators like x 1l, x 1k, x1l, x 1 l, x1k
    text = re.sub(r'\bx\s*\d+\s*[lkg]+\b', '', text)
    # Remove accents
    replacements = (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"))
    for a, b in replacements:
        text = text.replace(a, b)
    # Standardize punctuation
    text = text.replace('-', ' ').replace('_', ' ')
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    # Remove noise words
    tokens = text.split()
    filtered_tokens = [w for w in tokens if w not in NOISE_WORDS and len(w) > 1]
    return " ".join(filtered_tokens)

def calculate_similarity(pdf_text, recipe_name):
    """Calculates fuzzy similarity score between PDF description and recipe name."""
    norm_pdf = normalize_text(pdf_text)
    norm_recipe = normalize_text(recipe_name)
    
    if not norm_pdf or not norm_recipe:
        return 0.0

    # Exact normalized match
    if norm_pdf == norm_recipe:
        return 1.0

    # Sequence matcher ratio
    seq_ratio = SequenceMatcher(None, norm_pdf, norm_recipe).ratio()
    
    # Token subset score
    tokens_pdf = set(norm_pdf.split())
    tokens_recipe = set(norm_recipe.split())
    
    if not tokens_pdf or not tokens_recipe:
        return seq_ratio

    intersection = tokens_pdf.intersection(tokens_recipe)
    token_score = len(intersection) / max(len(tokens_pdf), len(tokens_recipe))
    
    # Give higher weight to matching key words
    final_score = (seq_ratio * 0.4) + (token_score * 0.6)
    return round(final_score, 2)

def calculate_raw_materials(mapped_items):
    """
    Multiplies required recipe liters by formula ingredient ratios in database
    and aggregates total raw material demand.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    material_totals = {}
    
    for item in mapped_items:
        recipe_id = item.get('receta_id')
        litros = item.get('cantidad', 0)
        
        if not recipe_id or litros <= 0:
            continue
            
        cursor.execute("""
            SELECT 
                ri.materia_prima_id, 
                mp.nombre as materia_prima, 
                COALESCE(ri.unidad, mp.unidad) as unidad, 
                ri.cantidad as cantidad_formula,
                COALESCE(smp.cantidad_actual, smp.cantidad, 0) as stock_actual
            FROM receta_ingredientes ri
            JOIN materias_primas mp ON ri.materia_prima_id = mp.id
            LEFT JOIN stock_materias_primas smp ON smp.materia_prima_id = mp.id
            WHERE ri.receta_id = ?
        """, (recipe_id,))
        
        ingredients = cursor.fetchall()
        
        for ing in ingredients:
            mp_id = ing['materia_prima_id']
            mp_nombre = ing['materia_prima']
            unidad = ing['unidad']
            cant_formula = ing['cantidad_formula']
            stock_actual = ing['stock_actual']
            
            # Total required = litros * formula proportion
            requerido = cant_formula * litros
            
            if mp_id in material_totals:
                material_totals[mp_id]['cantidad_requerida'] += requerido
            else:
                material_totals[mp_id] = {
                    'materia_prima_id': mp_id,
                    'materia_prima': mp_nombre,
                    'unidad': unidad,
                    'cantidad_requerida': requerido,
                    'stock_actual': stock_actual
                }
                
    conn.close()
    
    df = pd.DataFrame(list(material_totals.values()))
    if not df.empty:
        df['diferencia_stock'] = df['stock_actual'] - df['cantidad_requerida']
        df['estado_stock'] = df['diferencia_stock'].apply(
            lambda x: "🟢 OK" if x >= 0 else "🔴 DEFICIT"
        )
    return df

def main():
    init_database_tables()
    
    st.title("🧪 Calculador de Materia Prima Bekim")
    st.caption("Sistema multidiseño de mapeo de facturas PDF a recetas de base de datos y cálculo de stock")
    
    # Load database statistics and recipes
    conn = get_db_connection()
    try:
        db_recipes = pd.read_sql_query("SELECT id, nombre FROM recetas ORDER BY nombre ASC", conn)
        total_recipes = len(db_recipes)
        total_materials = conn.execute("SELECT COUNT(*) FROM materias_primas").fetchone()[0]
    except Exception as e:
        st.error(f"Error al leer la base de datos `minerva.db`: {e}")
        db_recipes = pd.DataFrame(columns=['id', 'nombre'])
        total_recipes = 0
        total_materials = 0
    finally:
        conn.close()

    # Sidebar stats
    st.sidebar.markdown("### 📌 Panel Minerva DB")
    col_sb1, col_sb2 = st.sidebar.columns(2)
    col_sb1.metric("Recetas DB", total_recipes)
    col_sb2.metric("Materias Primas", total_materials)
    
    similarity_threshold = st.sidebar.slider(
        "Umbral Mínimo de Coincidencia (%)",
        min_value=10, max_value=100, value=30, step=5
    ) / 100.0

    remembered_aliases = get_remembered_aliases()

    tab1, tab2, tab3 = st.tabs([
        "📄 1. Cargar PDF / Factura", 
        "🔍 2. Validar Mapeo de Recetas", 
        "📊 3. Explosión de Materia Prima"
    ])
    
    with tab1:
        st.subheader("Cargar Factura de Pedido")
        st.write("Sube el archivo PDF de la factura (soporta tanto el diseño clásico como el diseño en tabla SI2609-1230).")
        
        uploaded_pdf = st.file_uploader("Subir Archivo PDF de Factura", type=["pdf"])
        
        sample_choice = st.radio(
            "O probar con un texto de factura de ejemplo:",
            ["Factura Ejemplo SI2609-1230 (Nuevo Diseño Tabla)", "Factura Ejemplo SI2608-1211 (Diseño Clásico)"],
            horizontal=True
        )
        
        sample_pdf_new_design = (
            "Factura SI2609-1230\n"
            "Ref. Proveedor: 3-9 parte 2\n"
            "BEKIM COSMETICA CAPILAR S.R.L.\n"
            "| Descripción | IVA | Prec. Unit. | Cantidad | Total (neto) |\n"
            "| MP-019-MAT. PRIMA ARGAN LISS X 1L c/fragancia | 0% | 2.019,60 | 1800 | 3.635.280,00 |\n"
            "| MP-020-MAT. PRIMA ALISADO PLASTIFICADO X 1L c/fragancia | 0% | 2.019,60 | 1400 | 2.827.440,00 |\n"
            "| MP-021-MAT. PRIMA BOTTOX X 1L c/fragancia | 0% | 2.019,60 | 1600 | 3.231.360,00 |\n"
            "| MP-022-MAT. PRIMA COMPLEX KERATIN X 1L c/fragancia | 0% | 2.019,60 | 1400 | 2.827.440,00 |\n"
            "| MP-029-MATERIA PRIMA CACAO C/FRAGANCIA X 1L c/fragancia | 0% | 2.080,80 | 1800 | 3.745.440,00 |\n"
            "| MP-042-MATERIA PRIMA LIX PLEX C/FRAGANCIA X 1 L | 0% | 2.126,70 | 2600 | 5.529.420,00 |\n"
            "| MP-001-MAT. PRIMA MASCARA ARGAN X 1L C/FRAG | 0% | 2.019,60 | 800 | 1.615.680,00 |\n"
            "| MP-005-MAT. PRIMA MASCARA KARITE X 1L C/FRAG. | 0% | 1.989,00 | 200 | 397.800,00 |\n"
            "| MP-006-MAT. PRIMA SHAMPOO KARITE X 1L C/FRAG. | 0% | 2.096,10 | 200 | 419.220,00 |\n"
            "| MP-010-MAT. PRIMA MASCARA A.COLOR X1L C/FRAG. | 0% | 1.958,40 | 200 | 391.680,00 |\n"
            "| MP-011-MAT. PRIMA SHAMPOO AF.COLOR X 1L C/FRAG. | 0% | 2.065,50 | 200 | 413.100,00 |\n"
            "| MP-045-MATERIA PRIMA SHAMPOO 5.4 C/FRAG | 0% | 2.233,80 | 200 | 446.760,00 |\n"
            "| MP-046-MATERIA PRIMA ACONDICIONADOR 5.4 C/FRAG | 0% | 1.683,00 | 200 | 336.600,00 |\n"
            "| mp-44-MATERIA PRIMA SHAMPOO E-QUILIBRID X KILO | 0% | 2.233,80 | 200 | 446.760,00 |\n"
            "| flete productos xxx | 0% | -7.500,00 | 7 | -52.500,00 |\n"
            "| Total (neto) | 26.211.480,00 |\n"
            "| Impuesto total | 0,00 |\n"
            "| Total (incl. imp.) | 26.211.480,00 |"
        )
        
        sample_pdf_classic = (
            "mp-44 - MATERIA PRIMA SHAMPOO E-QUILIBRID X KILO 0% 2.219,20 200 5% 421.648,00\n"
            "MP-040 - MAT.PRIMA MASCARA MATIZADORA VIOLETA X 1K 0% 3.222,40 600 5% 1.836.768,00\n"
            "MP-001 - MAT. PRIMA MASCARA ARGAN X 1L C/FRAG 0% 2.006,40 600 5% 1.143.648,00\n"
            "MP-005 - MAT. PRIMA MASCARA KARITE X 1L C/FRAG. 0% 1.976,00 400 5% 750.880,00\n"
            "flete 0% -7.500,00 11 -82.500,00"
        )
        
        default_text = sample_pdf_new_design if "SI2609-1230" in sample_choice else sample_pdf_classic

        raw_text = ""
        if uploaded_pdf is not None:
            raw_text = extract_text_from_pdf_file(uploaded_pdf)
            st.success(f"✅ Archivo PDF `{uploaded_pdf.name}` leído con éxito.")
        else:
            raw_text = st.text_area("Texto Extraído / Copiado de Factura:", value=default_text, height=220)

        if st.button("🚀 Extraer Ordenes de Recetas del PDF", type="primary"):
            parsed_items = parse_invoice_text(raw_text)
            if not parsed_items:
                st.warning("⚠️ No se encontraron renglones de recetas válidos en la factura. (Servicios y fletes fueron ignorados automáticamente).")
            else:
                st.session_state['parsed_items'] = parsed_items
                st.success(f"✅ Se detectaron {len(parsed_items)} ítems de recetas en la factura.")

        if 'parsed_items' in st.session_state and st.session_state['parsed_items']:
            st.subheader("📋 Ítems detectados en la factura")
            df_parsed = pd.DataFrame([
                {'Descripción en Factura': item['descripcion'], 'Cantidad Extraída (Litros)': item['cantidad']}
                for item in st.session_state['parsed_items']
            ])
            st.dataframe(df_parsed, use_container_width=True)

    with tab2:
        st.subheader("Mapeo de Ítems de Factura a Recetas DB")
        
        if 'parsed_items' not in st.session_state or not st.session_state['parsed_items']:
            st.info("👈 Por favor procesa una factura en la pestaña 1 primero.")
        else:
            parsed_items = st.session_state['parsed_items']
            recipe_options = ["-- No Asignar / Ignorar --"] + db_recipes['nombre'].tolist()
            recipe_id_map = dict(zip(db_recipes['nombre'], db_recipes['id']))
            
            mapped_results = []
            
            st.write("Verifica la asignación automática. Las vinculaciones guardadas en memoria se aplicarán automáticamente con 100% de confianza.")
            
            for idx, item in enumerate(parsed_items):
                pdf_desc = item['descripcion']
                cant_litros = item['cantidad']
                pdf_key = pdf_desc.strip().upper()
                
                st.markdown("---")
                col_info, col_select, col_score = st.columns([2.5, 3, 1.5])
                
                with col_info:
                    st.markdown(f"##### 📄 Ítem #{idx+1}: **{pdf_desc}**")
                    st.markdown(f"**Litros Facturados:** `{cant_litros:,.0f} Lts`".replace(',', '.'))
                
                # Default selection logic
                default_index = 0
                match_score = 0.0
                is_memory_match = False
                
                # Check persistent memory alias
                if pdf_key in remembered_aliases:
                    saved_id, saved_name = remembered_aliases[pdf_key]
                    if saved_name in recipe_options:
                        default_index = recipe_options.index(saved_name)
                        match_score = 1.0
                        is_memory_match = True
                else:
                    # Find best fuzzy match in recipes DB
                    best_match = None
                    highest_score = 0.0
                    
                    for r_name in db_recipes['nombre']:
                        score = calculate_similarity(pdf_desc, r_name)
                        if score > highest_score:
                            highest_score = score
                            best_match = r_name
                            
                    if highest_score >= similarity_threshold and best_match:
                        default_index = recipe_options.index(best_match)
                        match_score = highest_score

                # Unique widget key combining index and hash
                item_stable_key = f"select_recipe_{idx}_{abs(hash(pdf_desc))}"
                
                with col_select:
                    selected_recipe = st.selectbox(
                        "Asignar a Receta DB:",
                        options=recipe_options,
                        index=default_index,
                        key=item_stable_key
                    )
                
                with col_score:
                    if is_memory_match:
                        st.success("💾 Memoria (100%)")
                    elif match_score >= 0.7:
                        st.success(f"🟢 Coincidencia: {int(match_score*100)}%")
                    elif match_score >= similarity_threshold:
                        st.warning(f"🟡 Coincidencia: {int(match_score*100)}%")
                    else:
                        st.error(f"🔴 Sin Coincidencia ({int(match_score*100)}%)")

                if selected_recipe != "-- No Asignar / Ignorar --":
                    r_id = recipe_id_map.get(selected_recipe)
                    mapped_results.append({
                        'descripcion_pdf': pdf_desc,
                        'receta_nombre': selected_recipe,
                        'receta_id': r_id,
                        'cantidad': cant_litros
                    })

            st.session_state['mapped_results'] = mapped_results

            st.markdown("---")
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("💾 Guardar Mapeos Actuales en Memoria DB", type="secondary"):
                    for res in mapped_results:
                        save_alias(res['descripcion_pdf'], res['receta_id'], res['receta_nombre'])
                    st.success("✅ Mapeos memorizados correctamente para futuras facturas.")
            with col_btn2:
                st.write(f"**Total Ítem Mapeados:** {len(mapped_results)} de {len(parsed_items)}")

    with tab3:
        st.subheader("Cálculo Explosión de Materias Primas Requeridas")
        
        mapped_results = st.session_state.get('mapped_results', [])
        
        if not mapped_results:
            st.info("👈 Valida el mapeo de recetas en la pestaña 2 para calcular materias primas.")
        else:
            df_materials = calculate_raw_materials(mapped_results)
            
            if df_materials.empty:
                st.warning("⚠️ No se encontraron ingredientes cargados en la tabla `receta_ingredientes` para las recetas seleccionadas.")
            else:
                deficit_count = len(df_materials[df_materials['diferencia_stock'] < 0])
                
                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.metric("Materias Primas Distintas", len(df_materials))
                col_m2.metric("Materias Primas con Faltante", deficit_count, delta_color="inverse")
                col_m3.metric("Estado General Stock", "OK" if deficit_count == 0 else "DEFICIT", delta_color="inverse")
                
                st.markdown("### Detalle Consolidado de Insumos")
                
                # Format numbers for clean presentation
                df_display = df_materials.copy()
                df_display['cantidad_requerida'] = df_display['cantidad_requerida'].round(2)
                df_display['stock_actual'] = df_display['stock_actual'].round(2)
                df_display['diferencia_stock'] = df_display['diferencia_stock'].round(2)
                
                st.dataframe(
                    df_display[[
                        'materia_prima', 'unidad', 'cantidad_requerida', 
                        'stock_actual', 'diferencia_stock', 'estado_stock'
                    ]],
                    use_container_width=True,
                    hide_index=True
                )
                
                # Export to CSV
                csv_data = df_display.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Descargar Reporte de Materia Prima (CSV)",
                    data=csv_data,
                    file_name="materia_prima_requerida_bekim.csv",
                    mime="text/csv"
                )

if __name__ == "__main__":
    main()