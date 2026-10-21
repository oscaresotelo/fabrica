import streamlit as st
import sqlite3
from datetime import datetime, date
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import uuid
import pandas as pd
import re
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch

DB_PATH = "minerva.db"

def init_db():
    """Inicializa la base de datos sqlite con las tablas necesarias y datos de prueba si está vacía."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS materias_primas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                unidad TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recetas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                procedimientos TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS receta_ingredientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receta_id INTEGER,
                materia_prima_id INTEGER,
                cantidad REAL,
                unidad TEXT,
                FOREIGN KEY(receta_id) REFERENCES recetas(id),
                FOREIGN KEY(materia_prima_id) REFERENCES materias_primas(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pedidos_produccion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER,
                receta_id INTEGER,
                cantidad REAL,
                numero_pedido TEXT,
                fecha TEXT,
                estado TEXT,
                lote TEXT,
                FOREIGN KEY(cliente_id) REFERENCES clientes(id),
                FOREIGN KEY(receta_id) REFERENCES recetas(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS receta_modificada (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pedido_id INTEGER,
                receta_id INTEGER,
                materia_prima_id INTEGER,
                cantidad REAL,
                unidad TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_materias_primas (
                materia_prima_id INTEGER PRIMARY KEY,
                cantidad_actual REAL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS composicion_colorantes (
                colorante_combinado_id INTEGER,
                colorante_primario_id INTEGER,
                proporcion REAL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lotes (
                numero TEXT PRIMARY KEY,
                fecha TEXT,
                cliente_id INTEGER,
                receta_id INTEGER
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS movimientos_materia_prima (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                materia_prima_id INTEGER,
                fecha TEXT,
                cantidad REAL,
                tipo_movimiento TEXT,
                destino TEXT,
                lote TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS producciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pedido_id INTEGER,
                fecha TEXT,
                lote TEXT,
                estado TEXT,
                cantidad_litros REAL,
                litros_envasados REAL,
                cantidad_real_litros REAL
            )
        ''')
        
        # Poblar datos demo si no existen pedidos
        cursor.execute("SELECT COUNT(*) FROM pedidos_produccion")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO clientes (nombre) VALUES ('BEKIM')")
            cliente_id = cursor.lastrowid
            
            procedimiento_demo = """2. BITÁCORA DE PROCESO Y PUNTOS CRÍTICOS (PCC)
| Orden | Descripción del Proceso | Control/Parámetro | Registro Operario | Hora |
| 1 | Limpieza: Reactor y bombas | Visual: Sin residuos | [ ] OK | |
| 3 | (A) En el reactor limpio cargar 195 litros de agua, a temperatura de 65 grados, agregar EDTA, luego carbopol en forma lluvia, dejar hidratar. | El líquido debe ser totalmente traslúcido sin partículas | [ ] OK | |
| 4 | En contenedor limpio y desinfectado pesar todos los ingredientes de la formulación. | Control de pesada | [ ] OK | |
| 10 | Mezcla B - En un recipiente auxiliar agregar glicerina, alcohol, esencia y mezclar. | Controlar pasta fluida sin grumos | [ ] OK | |
| 11 | Una vez hidratado el carbopol, agregar activo alisante. | Homogeneizar sin grumos | [ ] OK | |
| 12 | Agregar la mezcla B sobre la mezcla A y homogeneizar. | Homogeneización y viscosidad | [ ] OK | |
| 16 | Verificar que el recipiente y la tapa del mismo se encuentren limpios. | Controlar que recipiente esté limpio | [ ] OK | |
| 17 | Con ayuda de mixer de mano incorporar trietanolamina y batir hasta formación de gel. Sacar contramuestra inicio, medio y final, rotular muestras. | Controlar formación de gel sin grumos y rotulación correcta | [ ] OK | |

3. CONTROL DE CALIDAD FINAL (LIBERACIÓN)
El producto no puede rotularse sin estos valores aprobados.
| Parámetro | Valor de Referencia | Cumple | Observaciones |
| Aspecto | gel viscosidad media | Si/No | |
| Color | ligeramente opalescente | Si/No | |
| Olor | manzana | Si/No | |
| pH Final | 6-7 | Si/No | |
| Viscosidad | Media / Según estándar | Si/No | |
| Yield value | < 1.6 | Si/No | |
"""
            cursor.execute("INSERT INTO recetas (nombre, procedimientos) VALUES ('ALISADO LIX PLEX', ?)", (procedimiento_demo,))
            receta_id = cursor.lastrowid
            
            mps = [
                ('AGUA TEMP AMBIENTE', 'L'),
                ('CARBOPOL', 'KG'),
                ('FORMOL', 'L'),
                ('GLICERINA', 'L'),
                ('TRIETANOLAMINA', 'KG'),
                ('MANZANA', 'L'),
                ('ALCOHOL ETILICO', 'L')
            ]
            
            mp_ids = []
            for nombre, un in mps:
                cursor.execute("INSERT INTO materias_primas (nombre, unidad) VALUES (?, ?)", (nombre, un))
                mp_id = cursor.lastrowid
                mp_ids.append(mp_id)
                cursor.execute("INSERT INTO stock_materias_primas (materia_prima_id, cantidad_actual) VALUES (?, ?)", (mp_id, 1000.0))
                
            ingredientes_base = [
                (mp_ids[0], 190.0, 'LITROS'),
                (mp_ids[1], 0.6, 'KG'),
                (mp_ids[2], 17.6, 'LITROS'),
                (mp_ids[3], 3.0, 'LITROS'),
                (mp_ids[4], 0.6, 'KG'),
                (mp_ids[5], 1.2, 'LITROS'),
                (mp_ids[6], 0.5, 'LITROS')
            ]
            
            for mpid, cant, un in ingredientes_base:
                cursor.execute("INSERT INTO receta_ingredientes (receta_id, materia_prima_id, cantidad, unidad) VALUES (?, ?, ?, ?)",
                               (receta_id, mpid, cant, un))
                
            cursor.execute("""
                INSERT INTO pedidos_produccion (cliente_id, receta_id, cantidad, numero_pedido, fecha, estado, lote)
                VALUES (?, ?, ?, '1176-10', '2026-07-13', 'pendiente', 'PENDIENTE')
            """, (cliente_id, receta_id, 213.5))
            
            conn.commit()

class NumberedCanvas(canvas.Canvas):
    """Canvas de ReportLab que calcula el total de páginas y agrega pie de página limpio."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Pie de página
        page_text = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(612 - 35, 20, page_text)
        self.drawString(35, 20, "Minerva ERP - Documento Oficial de Producción")
        
        # Línea divisoria en pie de página
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(35, 32, 612 - 35, 32)
        
        self.restoreState()

def gestionar_produccion():
    init_db()

    # --- Estilos de Streamlit ---
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
        with sqlite3.connect(DB_PATH) as conn:
            return conn.execute('''
                SELECT pp.id, c.nombre, r.nombre, pp.cantidad, pp.numero_pedido, 
                       pp.fecha, pp.estado, pp.receta_id, pp.lote, pp.cliente_id,
                       r.procedimientos
                FROM pedidos_produccion pp
                JOIN clientes c ON pp.cliente_id = c.id
                JOIN recetas r ON pp.receta_id = r.id
                WHERE pp.estado IN ('pendiente', 'en_proceso')
                ORDER BY pp.fecha
            ''').fetchall()

    def obtener_ingredientes(receta_id):
        with sqlite3.connect(DB_PATH) as conn:
            return conn.execute('''
                SELECT mp.id, mp.nombre, ri.cantidad, ri.unidad, ri.materia_prima_id
                FROM receta_ingredientes ri
                JOIN materias_primas mp ON ri.materia_prima_id = mp.id
                WHERE ri.receta_id = ?
            ''', (receta_id,)).fetchall()

    def obtener_ingredientes_modificados_db(pedido_id):
        with sqlite3.connect(DB_PATH) as conn:
            return conn.execute('''
                SELECT mp.id, mp.nombre, rm.cantidad, rm.unidad, rm.materia_prima_id
                FROM receta_modificada rm
                JOIN materias_primas mp ON rm.materia_prima_id = mp.id
                WHERE rm.pedido_id = ?
            ''', (pedido_id,)).fetchall()

    def obtener_stock():
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT materia_prima_id, cantidad_actual FROM stock_materias_primas").fetchall()
            return {r[0]: {"stock": float(r[1]) if r[1] is not None else 0.0} for r in rows}

    def obtener_materias_primas():
        with sqlite3.connect(DB_PATH) as conn:
            return conn.execute("SELECT id, nombre, unidad FROM materias_primas").fetchall()
    
    def obtener_composicion_colorante(conn, colorante_combinado_id):
        cur = conn.cursor()
        cur.execute("""
            SELECT colorante_primario_id, proporcion
            FROM composicion_colorantes
            WHERE colorante_combinado_id = ?
        """, (colorante_combinado_id,))
        return cur.fetchall()

    def convertir_a_litros(cantidad, unidad):
        if unidad is None:
            unidad = ""
        u = unidad.strip().upper()
        try:
            c = float(cantidad)
        except Exception:
            c = 0.0

        if u in ["L", "LITRO", "LITROS", "LTR", "LTS"]:
            return c
        if u in ["ML", "CM3", "CC"]:
            return c / 1000.0
        if u in ["G", "GR", "GRS"]:
            return c / 1000.0
        if u in ["KG", "KILO", "KILOS", "KILOGRAMO", "KILOGRAMOS"]:
            return c
        if "ML" in u:
            return c / 1000.0
        if "G" in u and "KG" not in u:
            return c / 1000.0
        if "KG" in u:
            return c
        if "L" in u:
            return c
        return c

    def calcular_batch_base(receta_id):
        filas = obtener_ingredientes(receta_id)
        total = 0.0
        for _mpid, _nombre, cantidad, unidad, _mp in filas:
            total += convertir_a_litros(cantidad, unidad)
        return total if total > 0 else 1.0

    def descontar_stock(conn, ingredientes, cantidad_a_producir, cur, receta_id=None):
        ingredientes_escala = {}
        faltantes = []
        stock = obtener_stock()

        if receta_id is not None:
            batch_base = calcular_batch_base(receta_id)
        else:
            batch_base = 200.0

        for ingr_id, ingr_nombre, cantidad_base, unidad, materia_prima_id in ingredientes:
            factor = float(cantidad_a_producir) / float(batch_base)
            cantidad_escalada = float(cantidad_base) * factor
            ingredientes_escala[materia_prima_id] = ingredientes_escala.get(materia_prima_id, 0.0) + cantidad_escalada

        for materia_prima_id, cantidad_escalada in ingredientes_escala.items():
            cur.execute("""
                SELECT 1 FROM composicion_colorantes WHERE colorante_combinado_id = ?
            """, (materia_prima_id,))
            es_colorante_combinado = cur.fetchone() is not None

            if es_colorante_combinado:
                composicion = obtener_composicion_colorante(conn, materia_prima_id)
                if not composicion:
                    st.warning(f"No se encontró la composición del colorante combinado con ID: {materia_prima_id}.")
                    continue
                for componente_id, proporcion in composicion:
                    cantidad_componente = cantidad_escalada * float(proporcion)
                    stock_componente = stock.get(componente_id, {"stock": 0.0})["stock"]
                    if stock_componente < cantidad_componente - 1e-9:
                        cur.execute("SELECT nombre FROM materias_primas WHERE id = ?", (componente_id,))
                        row = cur.fetchone()
                        ingrediente_nombre = row[0] if row else f"ID {componente_id}"
                        faltantes.append((ingrediente_nombre, cantidad_componente, stock_componente))
                    else:
                        nuevo_stock = max(stock_componente - cantidad_componente, 0.0)
                        cur.execute("""
                            UPDATE stock_materias_primas SET cantidad_actual = ? WHERE materia_prima_id = ?
                        """, (nuevo_stock, componente_id))
                        stock[componente_id] = {"stock": nuevo_stock}
            else:
                stock_actual = stock.get(materia_prima_id, {"stock": 0.0})["stock"]
                if stock_actual < cantidad_escalada - 1e-9:
                    cur.execute("SELECT nombre FROM materias_primas WHERE id = ?", (materia_prima_id,))
                    row = cur.fetchone()
                    ingrediente_nombre = row[0] if row else f"ID {materia_prima_id}"
                    faltantes.append((ingrediente_nombre, cantidad_escalada, stock_actual))
                else:
                    nuevo_stock = max(stock_actual - cantidad_escalada, 0.0)
                    cur.execute("""
                        UPDATE stock_materias_primas SET cantidad_actual = ? WHERE materia_prima_id = ?
                    """, (nuevo_stock, materia_prima_id))
                    stock[materia_prima_id] = {"stock": nuevo_stock}

        if faltantes:
            return faltantes
        return None

    def ingredients_normalize_for_pdf(ingredientes):
        out = []
        for nombre, cant, unidad in ingredientes:
            u = (unidad or "").strip().lower()
            if u in ["l", "litros", "litro"] and abs(cant) < 1:
                out.append((nombre, cant * 1000.0, "cm³"))
            elif u in ["kg", "kilos", "kilo"] and abs(cant) < 1:
                out.append((nombre, cant * 1000.0, "g"))
            else:
                out.append((nombre, cant, unidad))
        return out

    def generar_pdf_receta(cliente, receta, cantidad, numero_pedido, fecha_pedido, lote, ingredientes, procedimientos):
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=35,
            rightMargin=35,
            topMargin=35,
            bottomMargin=45
        )
        elements = []
        styles = getSampleStyleSheet()

        # Estilos visuales optimizados
        style_title = ParagraphStyle(
            'DocTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=15,
            leading=18,
            textColor=colors.HexColor("#0072C6"),
            alignment=1,
            spaceAfter=12
        )

        style_section_heading = ParagraphStyle(
            'SectionHeading',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True
        )

        style_normal = ParagraphStyle(
            'NormalBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#334155"),
            spaceAfter=4
        )

        style_cell = ParagraphStyle(
            'CellText',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#334155")
        )

        style_cell_center = ParagraphStyle(
            'CellTextCenter',
            parent=style_cell,
            alignment=1
        )

        style_cell_header = ParagraphStyle(
            'CellTextHeader',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1E293B"),
            alignment=1
        )

        # 1. ENCABEZADO Y DATOS DE PEDIDO
        elements.append(Paragraph(f"Receta de Producción: {receta}", style_title))
        
        info_header = [
            [Paragraph(f"<b>Cliente:</b> {cliente}", style_cell), Paragraph(f"<b>Pedido N°:</b> {numero_pedido}", style_cell)],
            [Paragraph(f"<b>Fecha:</b> {fecha_pedido}", style_cell), Paragraph(f"<b>Lote:</b> {lote or 'PENDIENTE'}", style_cell)],
            [Paragraph(f"<b>Cantidad:</b> {cantidad:.2f} litros", style_cell), ""]
        ]
        t_info = Table(info_header, colWidths=[3.7*inch, 3.7*inch])
        t_info.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#F1F5F9")),
        ]))
        elements.append(t_info)
        elements.append(Spacer(1, 10))

        # 2. INGREDIENTES
        elements.append(Paragraph("1. LISTA DE INGREDIENTES", style_section_heading))
        tabla_ing = [[
            Paragraph("<b>Ingrediente</b>", style_cell_header), 
            Paragraph("<b>Cantidad</b>", style_cell_header), 
            Paragraph("<b>Unidad</b>", style_cell_header)
        ]]
        
        for nombre, cant, unidad in ingredients_normalize_for_pdf(ingredientes):
            tabla_ing.append([
                Paragraph(nombre, style_cell),
                Paragraph(f"{cant:.3f}", style_cell_center),
                Paragraph(unidad, style_cell_center)
            ])
        
        t_ing = Table(tabla_ing, colWidths=[4.2*inch, 1.6*inch, 1.6*inch])
        t_ing.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F1F5F9")),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 4),
        ]))
        
        for r_idx in range(1, len(tabla_ing)):
            if r_idx % 2 == 0:
                t_ing.setStyle(TableStyle([('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor("#F8FAFC"))]))
                
        elements.append(t_ing)
        elements.append(Spacer(1, 10))

        # 3. PROCEDIMIENTO Y CONTROL DE CALIDAD (PARSER PARSEADOR SEPARADO Y RESISTENTE)
        if procedimientos:
            raw_lines = procedimientos.split("\n")
            cleaned_lines = []
            for line in raw_lines:
                line_str = line.strip()
                if not line_str:
                    continue
                # Descartar renglones basura o repeticiones sin significado
                if re.match(r'^[1| ]+$', line_str):
                    continue
                cleaned_lines.append(line_str)

            active_table_rows = []

            def is_header_row(parts):
                """Determina si un conjunto de partes es un encabezado de tabla."""
                if not parts:
                    return False
                p0 = parts[0].lower()
                return any(k in p0 for k in ["orden", "parámetro", "parametro", "etapa", "paso", "aspecto"])

            def flush_table():
                """Construye y retorna el objeto Table garantizando alineación de columnas."""
                if not active_table_rows:
                    return None
                
                # Determinar la cantidad real de columnas observadas en las filas
                num_cols_counts = [len(r) for r in active_table_rows]
                target_cols = max(num_cols_counts)
                
                table_data = []
                for r_idx, row in enumerate(active_table_rows):
                    # Si estamos en una tabla de 5 columnas (Bitácora) pero la fila tiene 4 partes y la celda 0 no es número,
                    # ajustamos reinsertando una columna vacía para el "Orden" para evitar desplazar el texto a la Columna 0.
                    adjusted_row = list(row)
                    if target_cols >= 5 and len(adjusted_row) == 4:
                        first_cell = adjusted_row[0].strip()
                        # Si no es un número simple o código de paso corto, desplazamos a la derecha
                        if not re.match(r'^\d+$', first_cell) and len(first_cell) > 5:
                            adjusted_row = [""] + adjusted_row
                    
                    # Normalizar longitud
                    while len(adjusted_row) < target_cols:
                        adjusted_row.append("")
                    if len(adjusted_row) > target_cols:
                        adjusted_row = adjusted_row[:target_cols]

                    is_hdr = (r_idx == 0) or is_header_row(adjusted_row)
                    row_cells = []

                    for c_idx, cell_text in enumerate(adjusted_row):
                        cell_str = str(cell_text).strip()
                        if is_hdr:
                            c_style = style_cell_header
                        else:
                            # Centrar columnas de ID u orden, firmas y checks
                            if target_cols == 5 and (c_idx == 0 or c_idx == 3 or c_idx == 4):
                                c_style = style_cell_center
                            elif target_cols == 4 and c_idx == 2:
                                c_style = style_cell_center
                            else:
                                c_style = style_cell
                        row_cells.append(Paragraph(cell_str if cell_str else "-", c_style))
                    table_data.append(row_cells)

                # Definir anchos exactos de columna según la estructura detectada
                if target_cols == 5:
                    # Tabla de Bitácora: [Orden (0.6in), Descripción (3.1in), Control (2.0in), Registro (1.1in), Hora (0.6in)]
                    col_widths = [0.6 * inch, 3.1 * inch, 2.0 * inch, 1.1 * inch, 0.6 * inch]
                elif target_cols == 4:
                    # Tabla de Calidad: [Parámetro (1.8in), Ref (2.2in), Cumple (0.9in), Obs (2.5in)]
                    col_widths = [1.8 * inch, 2.2 * inch, 0.9 * inch, 2.5 * inch]
                else:
                    page_width = 7.4 * inch
                    col_widths = [page_width / target_cols] * target_cols

                t = Table(table_data, colWidths=col_widths, repeatRows=1)
                t_style = [
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                    ('TOPPADDING', (0,0), (-1,-1), 4),
                    ('LEFTPADDING', (0,0), (-1,-1), 4),
                    ('RIGHTPADDING', (0,0), (-1,-1), 4),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F1F5F9")),
                    ('LINEBELOW', (0,0), (-1,0), 1.0, colors.HexColor("#94A3B8")),
                ]

                for r in range(1, len(table_data)):
                    if r % 2 == 0:
                        t_style.append(('BACKGROUND', (0, r), (-1, r), colors.HexColor("#F8FAFC")))

                t.setStyle(TableStyle(t_style))
                return t

            # Procesamiento línea por línea del procedimiento
            for line in cleaned_lines:
                if '|' in line:
                    parts = [p.strip() for p in line.split('|')]
                    if parts and parts[0] == "":
                        parts.pop(0)
                    if parts and parts[-1] == "":
                        parts.pop()

                    # Omitir líneas separadoras de markdown como |---|---|
                    if parts and all(set(p).issubset({'-', '=', ' '}) for p in parts if p):
                        continue

                    # Si detectamos un nuevo encabezado dentro del flujo de la tabla, vaciamos la tabla anterior primero
                    if is_header_row(parts) and active_table_rows:
                        t_prev = flush_table()
                        if t_prev:
                            elements.append(t_prev)
                            elements.append(Spacer(1, 8))
                        active_table_rows = []

                    # Si el número de columnas cambia drásticamente respecto a la tabla actual, también vaciamos
                    if active_table_rows and len(parts) != len(active_table_rows[0]) and not is_header_row(parts):
                        # Si es un cambio de 5 a 4 columnas, claramente es otra tabla
                        if abs(len(parts) - len(active_table_rows[0])) >= 1:
                            t_prev = flush_table()
                            if t_prev:
                                elements.append(t_prev)
                                elements.append(Spacer(1, 8))
                            active_table_rows = []

                    active_table_rows.append(parts)
                else:
                    # Si veníamos acumulando una tabla y encontramos texto normal, imprimimos la tabla acumulada
                    t_flow = flush_table()
                    if t_flow:
                        elements.append(t_flow)
                        elements.append(Spacer(1, 8))
                        active_table_rows = []

                    if re.match(r'^\d+\.\s+.*', line):
                        elements.append(Spacer(1, 6))
                        elements.append(Paragraph(line, style_section_heading))
                        elements.append(Spacer(1, 4))
                    else:
                        elements.append(Paragraph(line, style_normal))

            # Imprimir última tabla si quedó pendiente
            t_flow = flush_table()
            if t_flow:
                elements.append(t_flow)
                elements.append(Spacer(1, 8))

        # 4. FIRMAS Y REGISTRO FINAL (BLOQUE PROTEGIDO CONTRA SALTO DE PÁGINA)
        firmas_block = []
        firmas_block.append(Spacer(1, 10))
        firmas_block.append(Paragraph("<b>4. CIERRE DE LOTE Y FIRMAS DE LIBERACIÓN</b>", style_section_heading))
        
        firmas_data = [
            [Paragraph("<b>Observaciones de Producción:</b>", style_cell), Paragraph("<b>Conformidad de Calidad:</b>", style_cell)],
            [Paragraph("<br/><br/>________________________________________", style_cell), Paragraph("<br/><br/>________________________________________", style_cell)],
            [Paragraph("<b>Firma Operario Responsable</b>", style_cell), Paragraph("<b>Firma Supervisor / Calidad</b>", style_cell)]
        ]
        t_firmas = Table(firmas_data, colWidths=[3.7*inch, 3.7*inch])
        t_firmas.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FAFAFA")),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        firmas_block.append(t_firmas)

        # Usar KeepTogether para evitar que el bloque de firmas se separe en dos páginas
        elements.append(KeepTogether(firmas_block))

        # Construir con NumberedCanvas para numeración correcta
        doc.build(elements, canvasmaker=NumberedCanvas)
        buffer.seek(0)
        return buffer

    def imprimir_rotulo(cliente, receta, lote, fecha_prod):
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        height = letter[1]
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 100, f"Producto: {receta}")
        c.drawString(50, height - 130, f"Número de Lote: {lote}")
        c.drawString(50, height - 160, f"Fecha producida: {fecha_prod}") 
        c.drawString(50, height - 190, f"Cliente: {cliente}")
        c.showPage()
        c.save()
        buf.seek(0)
        return buf        

    def handle_multiselect_change():
        st.session_state.current_selections = st.session_state.multiselect_key

    if 'current_selections' not in st.session_state:
        st.session_state.current_selections = []

    pedidos = obtener_pedidos()
    if not pedidos:
        st.info("ℹ️ No hay pedidos pendientes ni en proceso.")

    pedido_labels = [f"{p[1]} - {p[2]} - {p[4]} - Estado: {p[6].capitalize()}" for p in pedidos]

    st.multiselect("Seleccionar pedido",
                    pedido_labels,
                    default=st.session_state.current_selections,
                    key="multiselect_key",
                    on_change=handle_multiselect_change)

    pedidos_seleccionados = [pedidos[pedido_labels.index(seleccion)] for seleccion in st.session_state.current_selections if seleccion in pedido_labels]

    for i, pedido in enumerate(pedidos_seleccionados):
        pedido_label = None

        try:
            pedido_id = pedido[0]
            cliente = pedido[1]
            receta = pedido[2]
            cantidad = pedido[3]
            numero_pedido = pedido[4]
            fecha = pedido[5]
            estado = pedido[6]
            receta_id = pedido[7]
            lote = pedido[8]
            cliente_id = pedido[9]
            procedimientos = pedido[10] if len(pedido) > 10 else None

            pedido_label = pedido_labels[pedido_labels.index(st.session_state.current_selections[i])]

            with st.expander(f"Detalles del pedido: {numero_pedido}"):
                stock = obtener_stock()

                ingredientes_modificados = obtener_ingredientes_modificados_db(pedido_id)
                if ingredientes_modificados:
                    ingredientes_raw = ingredientes_modificados
                else:
                    ingredientes_raw = obtener_ingredientes(receta_id)

                batch_base = calcular_batch_base(receta_id)
                factor = float(cantidad) / float(batch_base)
                ingredientes = [(i[1], float(i[2]) * factor, i[3]) for i in ingredientes_raw]

                materias_primas = obtener_materias_primas()
                materias_primas_dict = {mp[0]: mp[1] for mp in materias_primas}
                materias_primas_labels = {mp[0]: f"{mp[1]} ({mp[2]})" for mp in materias_primas}

                col1, col2 = st.columns([1, 2])
                with col1:
                    st.markdown("### 🧾 Información del Pedido")
                    st.write(f"**Cliente:** {cliente}")
                    st.write(f"**Receta:** {receta}")
                    st.write(f"**Cantidad:** {cantidad} litros")
                    st.write(f"**N° Pedido:** {numero_pedido}")
                    st.write(f"**Fecha:** {fecha}")
                    st.write(f"**Estado:** `{estado}`")
                    
                    if lote:
                        st.write(f"**Lote asignado:** `{lote}`")
                        
                with col2:
                    st.markdown("### 🧪 Ingredientes Escalados")

                    with st.form(key=f"form_ingredientes_{pedido_id}"):
                        st.markdown("#### ✏️ Editar Ingredientes")
                        modificaciones = {}
                        for j, (ingr_id, ingr_nombre, cantidad_base, unidad, materia_prima_id) in enumerate(ingredientes_raw):
                            col_ingr1, col_ingr2, col_ingr3 = st.columns(3)

                            with col_ingr1:
                                nueva_materia_prima_id = st.selectbox(
                                    f"MP - {ingr_nombre}",
                                    options=list(materias_primas_labels.keys()),
                                    format_func=lambda x: materias_primas_labels[x],
                                    index=list(materias_primas_labels.keys()).index(materia_prima_id) if materia_prima_id in materias_primas_labels else 0,
                                    key=f"materia_prima_{pedido_id}_{ingr_id}_{j}"
                                )
                            with col_ingr2:
                                nueva_cantidad = st.number_input(
                                    "Cantidad",
                                    value=float(cantidad_base),
                                    format="%.3f",
                                    key=f"cantidad_{pedido_id}_{ingr_id}_{j}"
                                )
                            with col_ingr3:
                                nueva_unidad = st.text_input(
                                    "Unidad",
                                    value=unidad,
                                    key=f"unidad_{pedido_id}_{ingr_id}_{j}"
                                )

                            modificaciones[ingr_id] = {
                                'materia_prima_id': nueva_materia_prima_id,
                                'materia_prima_nombre': materias_primas_dict.get(nueva_materia_prima_id, "N/A"),
                                'cantidad': nueva_cantidad,
                                'unidad': nueva_unidad
                            }
                            
                        if st.form_submit_button("Guardar cambios en ingredientes"):
                            with sqlite3.connect(DB_PATH) as conn:
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

                    ingredientes_mostrar = [(materias_primas_dict.get(i[4], "N/A"), float(i[2]) * factor, i[3]) for i in ingredientes_raw]
                    st.dataframe(pd.DataFrame(ingredientes_mostrar, columns=["Ingrediente", "Cantidad", "Unidad"])
                                         .style.format({"Cantidad": "{:.3f}"}), use_container_width=True)

                colA, colB = st.columns(2)
                with colA:
                    pdf_bytes = generar_pdf_receta(
                        cliente,
                        receta,
                        cantidad,
                        numero_pedido,
                        fecha,
                        lote,
                        ingredientes,
                        procedimientos
                    )
                    st.download_button(
                        label=f"📄 Descargar receta PDF - {numero_pedido}",
                        data=pdf_bytes,
                        file_name=f"receta_{numero_pedido}_{lote or 'sin_lote'}.pdf",
                        mime="application/pdf"
                    )

                with colB:
                    if lote and lote != "PENDIENTE":
                        st.download_button(
                            label=f"🏷️ Imprimir rótulo - {numero_pedido}",
                            data=imprimir_rotulo(cliente, receta, lote, fecha),
                            file_name=f"rotulo_{numero_pedido}_{lote}.pdf",
                            mime="application/pdf"
                        )
                st.markdown("---")

                if estado == "pendiente":
                    st.subheader("⚙️ Opciones para estado Pendiente")
                    opcion = st.selectbox(f"Operación para {numero_pedido}:", ["Simular sin descontar stock", "Simular descontando y mostrar faltantes", "Confirmar producción"], key=f"opcion_{pedido_id}")
                    
                    if st.button(f"Ejecutar operación para {numero_pedido}", key=f"button_{pedido_id}"):
                        if opcion.startswith("Simular"):
                            ingredientes_simulacion = obtener_ingredientes_modificados_db(pedido_id)
                            if not ingredientes_simulacion:
                                ingredientes_simulacion = obtener_ingredientes(receta_id)
                            
                            with sqlite3.connect(DB_PATH) as conn:
                                cur = conn.cursor()
                                faltantes = descontar_stock(conn, ingredientes_simulacion, cantidad, cur, receta_id=receta_id)
                                if faltantes:
                                    st.warning("⚠️ Ingredientes faltantes:")
                                    for nombre, req, disp in faltantes:
                                        st.write(f"- {nombre}: requiere {req:.3f}, disponible {disp:.3f}")
                                    conn.rollback()
                                else:
                                    st.success("✅ Suficiente stock disponible.")
                        elif opcion == "Confirmar producción":
                            lote_nuevo = generar_numero_lote()
                            with sqlite3.connect(DB_PATH) as conn:
                                cur = conn.cursor()
                                try:
                                    conn.execute("BEGIN")
                                    conn.execute("""
                                        INSERT OR IGNORE INTO lotes (numero, fecha, cliente_id, receta_id)
                                        VALUES (?, ?, ?, ?)
                                    """, (lote_nuevo, datetime.now().strftime("%Y-%m-%d"), cliente_id, receta_id))
                                    conn.execute("UPDATE pedidos_produccion SET estado = 'en_proceso', lote = ? WHERE id = ?", (lote_nuevo, pedido_id))
                                    conn.commit()
                                    st.success(f"✅ Pedido en proceso. Lote: {lote_nuevo}")
                                    if pedido_label in st.session_state.current_selections:
                                        st.session_state.current_selections.remove(pedido_label)
                                    st.rerun()
                                except sqlite3.Error as e:
                                    conn.rollback()
                                    st.error(f"Ocurrió un error al confirmar la producción: {e}")

                elif estado == "en_proceso":
                    st.subheader("⚙️ Opciones para estado En Proceso")
                    
                    fecha_produccion = st.date_input(
                        "🗓️ **Fecha de Realización de la Producción**",
                        value=datetime.now().date(),
                        max_value=datetime.now().date(),
                        key=f"fecha_prod_{pedido_id}"
                    )
                    fecha_sql = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    cantidad_real = st.number_input("Cantidad real producida (litros):", min_value=0.0, value=float(cantidad), step=0.01, key=f"cantidad_real_{pedido_id}")
                    opcion = st.selectbox("Operación:", ["Simular descontando stock y mostrar faltantes", "Producir descontando stock"], key=f"opcion_en_proceso_{pedido_id}")
                    
                    if st.button(f"Ejecutar operación para {numero_pedido}", key=f"button_en_proceso_{pedido_id}"):
                        with sqlite3.connect(DB_PATH) as conn:
                            cur = conn.cursor()
                            try:
                                conn.execute("BEGIN")

                                ingredientes_finales = obtener_ingredientes_modificados_db(pedido_id)
                                if not ingredientes_finales:
                                    ingredientes_finales = obtener_ingredientes(receta_id)

                                if opcion == "Simular descontando stock y mostrar faltantes":
                                    faltantes = descontar_stock(conn, ingredientes_finales, cantidad, cur, receta_id=receta_id)
                                    if faltantes:
                                        st.warning("⚠️ Ingredientes faltantes:")
                                        for nombre, req, disp in faltantes:
                                            st.write(f"- {nombre}: requiere {req:.3f}, disponible {disp:.3f}")
                                    else:
                                        st.success("✅ Suficiente stock disponible para la producción.")
                                    conn.rollback()

                                elif opcion == "Producir descontando stock":
                                    faltantes = descontar_stock(conn, ingredientes_finales, cantidad_real, cur, receta_id=receta_id)
                                    if faltantes:
                                        st.warning("⚠️ No se puede completar la producción debido a ingredientes faltantes:")
                                        for nombre, req, disp in faltantes:
                                            st.write(f"- {nombre}: requiere {req:.3f}, disponible {disp:.3f}")
                                        conn.rollback()
                                        st.stop()

                                    ingr_dict = {}
                                    batch_base = calcular_batch_base(receta_id)
                                    factor_real = float(cantidad_real) / float(batch_base)
                                    for ingr_id, ingr_nombre, cantidad_base, unidad, materia_prima_id in ingredientes_finales:
                                        cantidad_escalada = float(cantidad_base) * factor_real
                                        
                                        cur.execute("SELECT 1 FROM composicion_colorantes WHERE colorante_combinado_id = ?", (materia_prima_id,))
                                        es_colorante_combinado = cur.fetchone() is not None

                                        if es_colorante_combinado:
                                            composicion = obtener_composicion_colorante(conn, materia_prima_id)
                                            for componente_id, proporcion in composicion:
                                                cantidad_componente = cantidad_escalada * float(proporcion)
                                                ingr_dict[componente_id] = ingr_dict.get(componente_id, 0.0) + cantidad_componente
                                        else:
                                            ingr_dict[materia_prima_id] = ingr_dict.get(materia_prima_id, 0.0) + cantidad_escalada

                                    for materia_prima_id, cantidad_ingrediente in ingr_dict.items():
                                        cur.execute("""
                                            INSERT INTO movimientos_materia_prima
                                            (materia_prima_id, fecha, cantidad, tipo_movimiento, destino, lote)
                                            VALUES (?, ?, ?, 'egreso', 'produccion', ?)
                                        """, (materia_prima_id, fecha_sql, -abs(cantidad_ingrediente), lote))

                                    cur.execute("""
                                        INSERT OR IGNORE INTO lotes (numero, fecha, cliente_id, receta_id)
                                        VALUES (?, ?, ?, ?)
                                    """, (lote, fecha_produccion.strftime("%Y-%m-%d"), cliente_id, receta_id))
                                    
                                    cur.execute("""
                                        INSERT INTO producciones (pedido_id, fecha, lote, estado, cantidad_litros, litros_envasados, cantidad_real_litros)
                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                    """, (pedido_id, fecha_sql, lote, 'producido', cantidad, 0, cantidad_real))
                                    
                                    cur.execute("UPDATE pedidos_produccion SET estado = 'producido' WHERE id = ?", (pedido_id,))
                                    cur.execute("DELETE FROM receta_modificada WHERE pedido_id = ?", (pedido_id,))
                                    
                                    conn.commit()
                                    st.success(f"✅ Producción registrada el **{fecha_produccion.strftime('%Y-%m-%d')}**. Lote: {lote} - Cantidad real: {cantidad_real} litros")
                                    if pedido_label in st.session_state.current_selections:
                                        st.session_state.current_selections.remove(pedido_label)
                                    st.rerun()

                            except sqlite3.Error as e:
                                conn.rollback()
                                st.error(f"Ocurrió un error al registrar la producción: {e}")

        except Exception as e:
            st.warning(f"Error al procesar el pedido seleccionado: {e}")

if __name__ == "__main__":
    gestionar_produccion()