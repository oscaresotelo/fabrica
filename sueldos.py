import streamlit as st
import sqlite3
import pandas as pd
import datetime
import locale
import calendar
import os
import io
import base64
import re # Necesario para el procesamiento de texto raw
from collections import defaultdict
from fpdf import FPDF # Asegúrate de que esta librería esté instalada: pip install fpdf2

# -------------------------------
# Configuración
# -------------------------------
DB_PATH = "minerva.db"
# Ajustar el locale para formatos de fecha y moneda si es necesario
try:
    # Intenta configurar el locale con .UTF-8 primero
    locale.setlocale(locale.LC_ALL, "es_ES.UTF-8")
except locale.Error:
    try:
        # Fallback a es_ES si el anterior falla
        locale.setlocale(locale.LC_ALL, "es_ES")
    except locale.Error:
        try:
            # Fallback a un locale genérico para Unix/Linux
            locale.setlocale(locale.LC_ALL, "es_ES.utf8")
        except locale.Error:
            pass # Si falla, continuará sin formato de moneda/fecha localizado

TOLERANCIA_PRESENTISMO_MIN = 10
LIMITE_TARDANZAS = 3
EMPLEADOS_PRESENTISMO_ESPECIAL = ["Gerardo", "Cristian", "Gabriel"] 

# -------------------------------
# Funciones auxiliares de DB
# -------------------------------
def get_connection():
    # Usar isolation_level=None para autocommit en Streamlit
    return sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)

def init_db():
    conn = get_connection()
    c = conn.cursor()

    # Empleados
    c.execute('''CREATE TABLE IF NOT EXISTS empleados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    sueldo_base REAL NOT NULL,
                    horas_jornada_diaria REAL NOT NULL,
                    horario_entrada TEXT NOT NULL,
                    horario_salida TEXT NOT NULL
                )''')

    # Asistencia
    c.execute('''CREATE TABLE IF NOT EXISTS asistencia (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    hora_entrada_real TEXT,
                    hora_salida_real TEXT,
                    es_feriado BOOLEAN DEFAULT 0,
                    ausente BOOLEAN DEFAULT 0,
                    justificado BOOLEAN DEFAULT 0,
                    justificacion_path TEXT,
                    observacion TEXT,
                    FOREIGN KEY(empleado_id) REFERENCES empleados(id)
                )''')

    # Liquidaciones
    c.execute('''CREATE TABLE IF NOT EXISTS liquidaciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    periodo TEXT NOT NULL,
                    dias_habiles_mes INTEGER NOT NULL,
                    dias_pagados INTEGER NOT NULL,
                    horas_extras REAL DEFAULT 0,
                    sueldo_bruto REAL NOT NULL,
                    bono_objetivo REAL DEFAULT 0,
                    bono_presentismo REAL DEFAULT 0,
                    descuento_falta REAL DEFAULT 0,
                    total_a_cobrar REAL NOT NULL,
                    FOREIGN KEY(empleado_id) REFERENCES empleados(id)
                )''')

    # Si la columna 'observacion' no existe, la añade (para compatibilidad)
    try:
        c.execute("SELECT observacion FROM asistencia LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE asistencia ADD COLUMN observacion TEXT")

    conn.close()

def get_empleados():
    conn = get_connection()
    df = pd.read_sql_query("SELECT id, nombre FROM empleados", conn)
    conn.close()
    return df

def get_empleado_info(empleado_id):
    conn = get_connection()
    query = "SELECT * FROM empleados WHERE id = ?"
    info = pd.read_sql_query(query, conn, params=(empleado_id,)).to_dict('records')
    conn.close()
    return info[0] if info else None

def insert_attendance_record(empleado_id, fecha_str, hora_entrada, hora_salida):
    """
    Inserta o actualiza un registro de asistencia con horas de entrada y salida reales.
    Si ya existe, lo actualiza a presente (ausente=0, justificado=0).
    """
    conn = get_connection()
    c = conn.cursor()
    
    # Asegurarse de que las horas sean None si están vacías, para evitar errores en la DB
    entrada = hora_entrada if hora_entrada else None
    salida = hora_salida if hora_salida else None
    
    # 1. Buscar si la fecha ya existe en la tabla de asistencia
    c.execute("SELECT id FROM asistencia WHERE empleado_id = ? AND fecha = ?", (empleado_id, fecha_str))
    record = c.fetchone()
    
    if record:
        # 2. Si existe, la actualiza con las horas, marcándola como presente
        c.execute("""
            UPDATE asistencia 
            SET hora_entrada_real = ?, 
                hora_salida_real = ?,
                ausente = 0, 
                justificado = 0,
                justificacion_path = NULL,
                observacion = ?
            WHERE id = ?
        """, (entrada, salida, "[Carga Manual/Bulk de Asistencia]", record[0]))
        
    else:
        # 3. Si no existe, la inserta como presente
        c.execute("""
            INSERT INTO asistencia (empleado_id, fecha, hora_entrada_real, hora_salida_real, ausente, justificado, observacion) 
            VALUES (?, ?, ?, ?, 0, 0, ?)
        """, (empleado_id, fecha_str, entrada, salida, "[Carga Manual/Bulk de Asistencia]"))
        
    conn.close()
    return True

def justificar_dia_ausente(empleado_id, fecha_str, justificacion_path, observacion):
    # (Misma función que antes)
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT id FROM asistencia WHERE empleado_id = ? AND fecha = ?", (empleado_id, fecha_str))
    record = c.fetchone()

    path_str = justificacion_path if justificacion_path else ''
    
    if record:
        c.execute("""
            UPDATE asistencia 
            SET ausente = 1, justificado = 1, hora_entrada_real = NULL, hora_salida_real = NULL, 
                justificacion_path = ?, observacion = ?
            WHERE id = ?
        """, (path_str, observacion, record[0]))
    else:
        c.execute("""
            INSERT INTO asistencia (empleado_id, fecha, ausente, justificado, justificacion_path, observacion) 
            VALUES (?, ?, 1, 1, ?, ?)
        """, (empleado_id, fecha_str, path_str, observacion))
        
    conn.close()
    return True

def force_unjustified_absence(empleado_id, fecha_str, observacion):
    # (Misma función que antes)
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT id FROM asistencia WHERE empleado_id = ? AND fecha = ?", (empleado_id, fecha_str))
    record = c.fetchone()
    
    if record:
        c.execute("""
            UPDATE asistencia 
            SET ausente = 1, justificado = 0, hora_entrada_real = NULL, hora_salida_real = NULL, 
                justificacion_path = NULL, observacion = ?
            WHERE id = ?
        """, (observacion, record[0]))
        
    else:
        c.execute("""
            INSERT INTO asistencia (empleado_id, fecha, ausente, justificado, observacion) 
            VALUES (?, ?, 1, 0, ?)
        """, (empleado_id, fecha_str, observacion))
        
    conn.close()
    return True

def get_asistencia_empleado(empleado_id, mes, anio):
    # (Misma función que antes)
    conn = get_connection()
    mes_str = f"{mes:02d}"
    anio_str = str(anio)

    query = """
        SELECT fecha,
               hora_entrada_real,
               hora_salida_real,
               ausente,
               justificado,
               es_feriado,
               justificacion_path,
               observacion
        FROM asistencia
        WHERE empleado_id = ?
          AND substr(fecha, 1, 4) = ?
          AND substr(fecha, 6, 2) = ?
        ORDER BY fecha
    """
    df_registros = pd.read_sql_query(query, conn, params=(empleado_id, anio_str, mes_str))
    conn.close()
    
    inicio_mes = datetime.date(anio, mes, 1)
    dias_del_mes = calendar.monthrange(anio, mes)[1]
    
    dias_habiles_laborables = []
    
    for i in range(dias_del_mes):
        fecha = inicio_mes + datetime.timedelta(days=i)
        if fecha.weekday() < 5: 
            dias_habiles_laborables.append(fecha.strftime("%Y-%m-%d"))
            
    df_dias_habiles = pd.DataFrame(dias_habiles_laborables, columns=['fecha'])
    
    df_completo = pd.merge(df_dias_habiles, df_registros, on='fecha', how='left')
    
    df_completo['ausente'] = df_completo['ausente'].astype(float).fillna(1).astype(int) 
    df_completo['justificado'] = df_completo['justificado'].astype(float).fillna(0).astype(int) 
    df_completo['es_feriado'] = df_completo['es_feriado'].astype(float).fillna(0).astype(int) 
    df_completo['justificacion_path'] = df_completo['justificacion_path'].fillna("")
    df_completo['observacion'] = df_completo['observacion'].fillna("")
    
    df_completo.loc[df_completo['hora_entrada_real'].notna(), 'ausente'] = 0

    return df_completo


def parse_raw_attendance_data(raw_text):
    """
    Procesa el texto sin formato del reloj checador para extraer las horas de entrada
    y salida por día. Asume que la entrada es la hora más temprana y la salida la más tardía.
    """
    # Regex para encontrar la marca de tiempo (Fecha y Hora), ignorando la zona horaria
    # Ejemplo: 2025-11-03 08:01:24-03:00 -> Busca '2025-11-03 08:01:24'
    timestamp_pattern = re.compile(r'(\d{4}-\d{2}-\d{2})\s(\d{2}:\d{2}:\d{2})')
    
    # { 'YYYY-MM-DD': ['HH:MM', 'HH:MM', ...] }
    daily_events = defaultdict(list)
    
    # Procesar línea por línea
    for line in raw_text.splitlines():
        match = timestamp_pattern.search(line)
        if match:
            date_str = match.group(1) # YYYY-MM-DD
            time_str_full = match.group(2) # HH:MM:SS
            time_str = time_str_full[:5] # Extraer HH:MM
            daily_events[date_str].append(time_str)

    # Procesar los eventos diarios para encontrar Entrada (min) y Salida (max)
    processed_data = []
    for date, times in daily_events.items():
        if times:
            # Ordenar las horas alfabéticamente/cronológicamente
            sorted_times = sorted(times)
            entrada = sorted_times[0]
            salida = sorted_times[-1]
            processed_data.append({
                'fecha': date,
                'hora_entrada': entrada,
                'hora_salida': salida
            })
            
    return processed_data


# -------------------------------
# Funciones de LÓGICA DE LIQUIDACIÓN
# -------------------------------
def get_feriados_nacionales(mes, anio):
    # (Misma función que antes)
    feriados = []
    if mes == 9: 
        try:
            fecha_feriado = datetime.date(anio, 9, 24)
            if fecha_feriado.weekday() < 5:
                feriados.append(fecha_feriado)
        except ValueError:
            pass 
    return feriados

def get_dias_habiles_y_feriados(mes, anio):
    # (Misma función que antes)
    inicio_mes = datetime.date(anio, mes, 1)
    num_days = calendar.monthrange(anio, mes)[1]
    dias_base_divisor = 0 
    feriados = get_feriados_nacionales(mes, anio)
    dias_feriados_habiles = 0
    fecha_actual = inicio_mes
    while fecha_actual.month == mes:
        if fecha_actual.weekday() < 5:
            dias_base_divisor += 1
            if fecha_actual in feriados:
                dias_feriados_habiles += 1
        fecha_actual += datetime.timedelta(days=1)
    return {
        "dias_calendario": num_days,
        "dias_base_divisor": dias_base_divisor, 
        "dias_feriados_habiles": dias_feriados_habiles
    }

def calcular_valor_hora(sueldo_base, dias_base_divisor, horas_jornada):
    # (Misma función que antes)
    if dias_base_divisor == 0 or horas_jornada == 0:
        return 0
    divisor = dias_base_divisor * horas_jornada 
    return sueldo_base / divisor

def preparar_df_asistencia(df_asistencia, empleado_info):
    HORA_FORMATO = "%H:%M" 
    horario_entrada = datetime.datetime.strptime(empleado_info["horario_entrada"], HORA_FORMATO)
    horario_salida = datetime.datetime.strptime(empleado_info["horario_salida"], HORA_FORMATO)
    
    df_asistencia['es_tardanza'] = 0
    df_asistencia['horas_extras_calculadas'] = 0.0
    
    for index, row in df_asistencia.iterrows():
        try:
            # 1. Calcular Tardanza (misma lógica)
            if row['ausente'] == 0 and row['hora_entrada_real'] is not None:
                entrada_real = datetime.datetime.strptime(row['hora_entrada_real'], HORA_FORMATO)
                tolerancia_limite = horario_entrada + datetime.timedelta(minutes=TOLERANCIA_PRESENTISMO_MIN)
                if entrada_real > tolerancia_limite:
                    if row['justificado'] == 0: 
                        df_asistencia.loc[index, 'es_tardanza'] = 1
            
            # 2. Calcular Horas Extras (CORRECCIÓN DE PRECISIÓN APLICADA)
            if row['ausente'] == 0 and row['hora_salida_real'] is not None:
                salida_real = datetime.datetime.strptime(row['hora_salida_real'], HORA_FORMATO)
                
                if salida_real < horario_salida:
                    pass
                else:
                    diferencia = salida_real - horario_salida
                    horas_extra = diferencia.total_seconds() / 3600
                    
                    # 💥 CORRECCIÓN: Se remueve el redondeo diario para mantener la precisión
                    # El redondeo se aplica solo al total en la función de liquidación.
                    df_asistencia.loc[index, 'horas_extras_calculadas'] = horas_extra
                    
        except (ValueError, TypeError):
            pass 

    return df_asistencia

def evaluar_presentismo(empleado_id, registros_asistencia_df, LIMITE_TARDANZAS, EMPLEADOS_PRESENTISMO_ESPECIAL, empleado_nombre):
    # (Misma función que antes)
    perdida_bono = False
    motivo = "Asistencia perfecta."
    
    inasistencias_no_justificadas = registros_asistencia_df[
        (registros_asistencia_df["ausente"] == 1) & 
        (registros_asistencia_df["justificado"] == 0)
    ].shape[0]
    
    tardanzas_no_justificadas = registros_asistencia_df["es_tardanza"].sum()

    if inasistencias_no_justificadas >= 1:
        perdida_bono = True
        motivo = f"Una o más inasistencias sin justificar ({inasistencias_no_justificadas} total)."
    
    elif tardanzas_no_justificadas > LIMITE_TARDANZAS:
        perdida_bono = True
        motivo = f"Más de {LIMITE_TARDANZAS} tardanzas no justificadas ({tardanzas_no_justificadas} total)."
    
    return perdida_bono, motivo

def calcular_liquidacion(empleado_info, registros_asistencia_df, dias_info, pagar_horas_extras=True, override_presentismo=False):
    # --- CONFIGURACIÓN DE DIVISOR FIJO ---
    # Se utiliza 22 días para que el valor de la hora sea constante todos los meses
    DIVISOR_FIJO_DIAS = 22.0
    
    sueldo_base = empleado_info["sueldo_base"]
    horas_jornada = empleado_info["horas_jornada_diaria"]
    
    # 1. Cálculo del Valor de la Hora (Base para todo el sistema)
    valor_dia_preciso = sueldo_base / DIVISOR_FIJO_DIAS
    valor_hora_normal_preciso = valor_dia_preciso / horas_jornada
    
    valor_hora_calculo_he = round(valor_hora_normal_preciso, 2)
    valor_dia_descuento_preciso = valor_hora_normal_preciso * horas_jornada
    
    # 2. Cálculo de Horas Extras
    MULTIPLICADOR_HE = 1.0
    valor_hora_extra_redondeado_muestra = round(valor_hora_calculo_he * MULTIPLICADOR_HE, 2)
    
    horas_extras_totales = registros_asistencia_df["horas_extras_calculadas"].sum()
    monto_horas_extras = round(horas_extras_totales * valor_hora_extra_redondeado_muestra, 2) if pagar_horas_extras else 0.0
    
    # 3. Análisis de Faltas y Presentismo
    tardanzas = registros_asistencia_df["es_tardanza"].sum()
    ausencias_no_justificadas = registros_asistencia_df[(registros_asistencia_df["ausente"] == 1) & (registros_asistencia_df["justificado"] == 0)].shape[0]
    
    perdida_bono = (ausencias_no_justificadas >= 1 or tardanzas > 3) # LIMITE_TARDANZAS = 3
    
    monto_presentismo_base = (110000.0 if empleado_info["nombre"] in ["Gerardo", "Cristian", "Gabriel"] else 60500.0)
    bono_presentismo = monto_presentismo_base if (not perdida_bono or override_presentismo) else 0.0
    
    # Determinar motivo para mostrar en la interfaz
    motivo_perdida = "N/A"
    if ausencias_no_justificadas >= 1:
        motivo_perdida = "Ausencias No Justificadas"
    elif tardanzas > 3:
        motivo_perdida = "Exceso de Tardanzas"
    
    # 4. Cálculo Final
    descuento_faltas = round(ausencias_no_justificadas * valor_dia_descuento_preciso, 2)
    bono_objetivo = sueldo_base * 0.10
    
    sueldo_neto = round(sueldo_base + bono_objetivo + bono_presentismo + monto_horas_extras - descuento_faltas, 2)
    
    # 5. Diccionarios de Salida
    detalle_liquid = {
        "Sueldo Fijo Mensual": sueldo_base,
        "Bono Objetivo (10%)": bono_objetivo,
        "Bono Presentismo": bono_presentismo,
        "Pago Horas Extras (1x)": monto_horas_extras,
        "Descuento Ausencias No Justificadas": -descuento_faltas,
        "Sueldo Neto": sueldo_neto
    }
    
    info_adicional = {
        "Días Base (Fijo)": DIVISOR_FIJO_DIAS,
        "Valor Hora Normal (Base Precisa)": valor_hora_normal_preciso,
        "Valor Hora Extra (1x Redondeado)": valor_hora_extra_redondeado_muestra,
        "Valor Día de Descuento (Preciso)": round(valor_dia_descuento_preciso, 2),
        "Días Ausentes No Justificados": ausencias_no_justificadas,
        "Horas Extras Totales": horas_extras_totales,
        "Tardanzas No Justificadas": tardanzas,
        "Bono Presentismo Aplica": not perdida_bono,
        "Override Presentismo": override_presentismo,
        "Motivo Pérdida Presentismo": motivo_perdida,
        "Pagar Horas Extras": pagar_horas_extras  # <--- ESTA LÍNEA SOLUCIONA EL ERROR
    }
    
    return detalle_liquid, info_adicional
# -------------------------------
# Función de Generación de PDF
# -------------------------------
class PDF(FPDF):
    # (Misma clase que antes)
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Boleta de Liquidación de Sueldos', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 11)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 7, title, 0, 1, 'L', 1)
        self.ln(2)

    def chapter_body(self, data, col_width=60):
        self.set_font('Arial', '', 10)
        
        self.set_fill_color(230, 230, 230)
        self.cell(col_width * 3, 6, 'Concepto', 1, 0, 'L', 1)
        self.cell(col_width, 6, 'Monto', 1, 1, 'R', 1)

        self.set_font('Arial', '', 10)
        for concepto, monto in data.items():
            self.cell(col_width * 3, 6, concepto, 1, 0, 'L')
            self.cell(col_width, 6, f'$ {monto:,.2f}', 1, 1, 'R')
        self.ln(5)

    def summary(self, total_neto):
        self.set_font('Arial', 'B', 14)
        self.set_fill_color(180, 255, 180)
        self.cell(0, 10, f'TOTAL NETO A COBRAR: $ {total_neto:,.2f}', 1, 1, 'C', 1)

def create_liquid_pdf(empleado_info, mes, anio, detalle_liquid, info_adicional):
    # (Misma función que antes)
    pdf = PDF('P', 'mm', 'A4')
    pdf.alias_nb_pages()
    pdf.add_page()
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 5, f"Colaborador: {empleado_info['nombre']}", 0, 1, 'L')
    periodo_str = datetime.date(anio, mes, 1).strftime("%B").capitalize()
    pdf.cell(0, 5, f"Período: {periodo_str} {anio}", 0, 1, 'L')
    pdf.ln(5)

    pdf.chapter_title("Detalle de Haberes y Descuentos")
    
    pdf_data = {}
    
    pdf_data["Sueldo Fijo Mensual"] = detalle_liquid["Sueldo Fijo Mensual"]
    pdf_data["Bono Objetivo (10%)"] = detalle_liquid["Bono Objetivo (10%)"]
    pdf_data["Bono Presentismo"] = detalle_liquid["Bono Presentismo"]
    pdf_data["Pago Horas Extras (1x)"] = detalle_liquid["Pago Horas Extras (1x)"]
    
    desc_val = abs(detalle_liquid["Descuento Ausencias No Justificadas"])
    pdf_data["(-) Descuento Ausencias No Justificadas"] = -desc_val 

    pdf.chapter_body(pdf_data, col_width=45)

    pdf.summary(detalle_liquid["Sueldo Neto"])
    pdf.ln(5)
    
    pdf.chapter_title("Información de Asistencia y Cálculo")
    pdf.set_font('Arial', '', 9)
    
    info_items = [
    f"Días Base (Fijo): {info_adicional['Días Base (Fijo)']}", # <--- CAMBIO AQUÍ
    f"Horas Extras Totales: {info_adicional['Horas Extras Totales']}",
    f"Tardanzas No Just.: {info_adicional['Tardanzas No Justificadas']}",
    f"Días Ausentes No Just.: {info_adicional['Días Ausentes No Justificados']}",
    f"Bono Presentismo Aplica (Lógica): {'Sí' if info_adicional['Bono Presentismo Aplica'] else 'No'}",
    f"Override Presentismo: {'Sí' if info_adicional['Override Presentismo'] else 'No'}",
]
    
    col_width = 65
    for i, item in enumerate(info_items):
        pdf.cell(col_width, 5, item, 0, 0, 'L')
        if (i + 1) % 3 == 0:
            pdf.ln(5)
    
    #pdf_output = pdf.output(dest='S')
    return pdf.output(dest='S').encode('latin-1')

# -------------------------------
# Interfaz principal
# -------------------------------
def main():
    st.set_page_config(page_title="💼 Gestión de Sueldos", layout="wide")
    st.title("💼 Gestión de Sueldos y Asistencia")

    init_db()

    empleados_df = get_empleados()
    empleados_dict = dict(zip(empleados_df["nombre"], empleados_df["id"]))

    if empleados_df.empty:
        st.error("No hay empleados registrados en la base de datos. Por favor, agregue empleados para continuar.")
        return

    # Tabs (Se añade una nueva pestaña al inicio)
    tab0, tab1, tab2 = st.tabs(["➕ Cargar Asistencia Pura", "📋 Gestión de Asistencia", "💰 Liquidación"])

    # -------------------------------
    # TAB 0: CARGA DE ASISTENCIA PURA
    # -------------------------------
    with tab0:
        st.subheader("➕ Carga de Registros de Asistencia")
        
        # Selección de empleado para la carga
        empleado_nombre_carga = st.selectbox(
            "👤 Seleccionar Empleado para la Carga", 
            list(empleados_dict.keys()),
            key="empleado_carga_select_tab0"
        )
        empleado_id_carga = empleados_dict[empleado_nombre_carga]

        st.markdown("---")
        
        col_manual, col_bulk = st.columns(2)
        
        with col_manual:
            st.markdown("#### 📝 Carga Manual (Día Único)")
            with st.form("form_cargar_asistencia_manual"):
                
                fecha_registro = st.date_input(
                    "📅 Fecha del Registro", 
                    datetime.datetime.now().date(),
                    key="fecha_registro_input_manual"
                )
                fecha_str_manual = fecha_registro.strftime("%Y-%m-%d")

                hora_entrada = st.text_input(
                    "Hora de Entrada (HH:MM)", 
                    placeholder="Ej: 07:55",
                    key="hora_entrada_input_manual"
                )
                hora_salida = st.text_input(
                    "Hora de Salida (HH:MM)", 
                    placeholder="Ej: 17:30",
                    key="hora_salida_input_manual"
                )

                submit_button_manual = st.form_submit_button("💾 Cargar/Actualizar Registro Manual")

            if submit_button_manual:
                valid_time = True
                
                def is_valid_time(t):
                    if not t: return True
                    try:
                        datetime.datetime.strptime(t, "%H:%M")
                        return True
                    except ValueError:
                        return False
                        
                if not is_valid_time(hora_entrada):
                    st.error("Formato de Hora de Entrada inválido. Use HH:MM.")
                    valid_time = False
                if not is_valid_time(hora_salida):
                    st.error("Formato de Hora de Salida inválido. Use HH:MM.")
                    valid_time = False

                if valid_time and (hora_entrada or hora_salida):
                    insert_attendance_record(empleado_id_carga, fecha_str_manual, hora_entrada, hora_salida)
                    st.success(f"Registro de asistencia manual para **{empleado_nombre_carga}** el **{fecha_str_manual}** cargado/actualizado correctamente.")
                    st.rerun()
                elif not hora_entrada and not hora_salida:
                    st.error("Debe ingresar al menos la Hora de Entrada o la Hora de Salida.")

        with col_bulk:
            st.markdown("#### 📄 Carga Masiva (Texto Raw del Checador)")
            with st.form("form_cargar_asistencia_bulk"):
                raw_data = st.text_area(
                    "Pega aquí el texto raw del reloj checador:", 
                    height=300,
                    placeholder="Ejemplo:\n1\n45862245\njoaquin\n--\n...\n2025-11-03 08:01:24-03:00\n-",
                    key="raw_data_input"
                )
                submit_button_bulk = st.form_submit_button("🚀 Procesar y Cargar Datos Masivos")

            if submit_button_bulk:
                if raw_data:
                    # 1. Parsear los datos
                    registros_procesados = parse_raw_attendance_data(raw_data)
                    
                    if not registros_procesados:
                        st.warning("No se encontraron registros válidos de fecha y hora en el texto proporcionado.")
                    else:
                        # 2. Insertar/Actualizar en la DB
                        conteo = 0
                        for record in registros_procesados:
                            insert_attendance_record(
                                empleado_id_carga, 
                                record['fecha'], 
                                record['hora_entrada'], 
                                record['hora_salida']
                            )
                            conteo += 1
                        
                        st.success(f"Se procesaron y cargaron/actualizaron **{conteo}** registros diarios para **{empleado_nombre_carga}**.")
                        st.dataframe(pd.DataFrame(registros_procesados), use_container_width=True)
                        st.rerun()
                else:
                    st.error("El campo de texto raw no puede estar vacío.")

    # -------------------------------
    # El resto del código principal (Pestañas 1 y 2)
    # -------------------------------
    
    # El empleado y período se configuran una vez aquí para las pestañas 1 y 2
    st.sidebar.title("Configuración de Período")
    empleado_nombre = st.sidebar.selectbox("👤 Empleado (Asistencia y Liquidación)", list(empleados_dict.keys()), key="empleado_select")
    empleado_id = empleados_dict[empleado_nombre]

    col1, col2 = st.sidebar.columns(2)
    with col1:
        mes_num = st.selectbox("📅 Mes", list(range(1, 13)), format_func=lambda x: datetime.date(1900, x, 1).strftime("%B"), key="mes_select")
    with col2:
        anio = st.number_input("📅 Año", min_value=2000, max_value=2100, value=datetime.datetime.now().year, key="anio_input")
    
    mes_str = datetime.date(anio, mes_num, 1).strftime("%B").capitalize()


    # -------------------------------
    # TAB 1: GESTIÓN DE ASISTENCIA
    # -------------------------------
    with tab1:
        st.subheader(f"📋 Asistencia de {empleado_nombre} - {mes_str} {anio}")
        # El contenido de esta pestaña debe ir dentro de un 'if' que verifica la selección
        if empleado_id and mes_num and anio:
            empleado_info = get_empleado_info(empleado_id)
            registros_df = get_asistencia_empleado(empleado_id, mes_num, anio) 
            registros_df_calculado = preparar_df_asistencia(registros_df.copy(), empleado_info)
            dias_info = get_dias_habiles_y_feriados(mes_num, anio)
            
            dias_presente = registros_df_calculado[registros_df_calculado['ausente'] == 0].shape[0]
            dias_ausente_no_justificado = registros_df_calculado[(registros_df_calculado['ausente'] == 1) & (registros_df_calculado['justificado'] == 0)].shape[0]
            
            st.info(f"Total Días Hábiles de Pago: **{dias_info['dias_base_divisor']}** | Días Presente: **{dias_presente}** | Faltas **NO Justificadas**: **{dias_ausente_no_justificado}**")
            
            # --- SECCIÓN DE ACCIONES MANUALES ---
            st.markdown("---")
            st.markdown("### 🛠️ Acciones Manuales sobre Días")

            col_justificar, col_descontar = st.columns(2)
            
            with col_justificar:
                st.markdown("#### 📝 Justificación de Ausencias")
                dias_a_justificar_df = registros_df_calculado[
                    (registros_df_calculado['ausente'] == 1) & 
                    (registros_df_calculado['justificado'] == 0)
                ]
                
                if not dias_a_justificar_df.empty:
                    fechas_ausentes = sorted(dias_a_justificar_df['fecha'].tolist())
                    
                    with st.form("form_justificar_ausencia"):
                        fecha_justificar = st.selectbox(
                            "Fecha a Justificar:", 
                            fechas_ausentes,
                            key="just_date"
                        )
                        archivo_justificacion = st.file_uploader(
                            "Sube Certificado/Documento (Opcional)",
                            type=['pdf', 'jpg', 'png']
                        )
                        observacion_just = st.text_area(
                            "Observación/Motivo de la justificación", 
                            height=80,
                            key="just_obs"
                        )
                        justificar_btn = st.form_submit_button("✅ Justificar Ausencia Seleccionada")

                    if justificar_btn:
                        path_guardado = ""
                        if archivo_justificacion is not None:
                            path_guardado = f"uploaded/{archivo_justificacion.name}"

                        justificar_dia_ausente(empleado_id, fecha_justificar, path_guardado, observacion_just)
                        st.success(f"Día **{fecha_justificar}** justificado correctamente.")
                        st.rerun()
                else:
                    st.info("No hay ausencias no justificadas pendientes de acción.")
            
            with col_descontar:
                st.markdown("#### ✂️ Descuento Manual (Falta Injustificada)")
                
                dias_habiles_mes = registros_df_calculado['fecha'].tolist()

                with st.form("form_descontar_dia"):
                    fecha_descontar = st.selectbox(
                        "Fecha para Descontar:", 
                        dias_habiles_mes,
                        key="desc_date"
                    )
                    
                    observacion_desc = st.text_area(
                        "Motivo del Descuento Manual", 
                        placeholder="Ej: Descuento por inasistencia sin aviso.",
                        height=80,
                        key="desc_obs"
                    )
                    
                    descontar_btn = st.form_submit_button("❌ Forzar Descuento (Falta Injustificada)")
                
                if descontar_btn:
                    if observacion_desc:
                        force_unjustified_absence(empleado_id, fecha_descontar, f"[DESCUENTO MANUAL] {observacion_desc}")
                        st.warning(f"Día **{fecha_descontar}** forzado a Falta Injustificada (Descuento aplicado).")
                        st.rerun()
                    else:
                        st.error("Debe ingresar un motivo para el Descuento Manual.")

            st.markdown("---")

            # --- TABLA DE REGISTROS (DETALLE) ---
            st.subheader("Detalle de Registros de Asistencia")
            
            registros_df_display = registros_df_calculado.copy()
            registros_df_display["ausente"] = registros_df_display["ausente"].map({0: "No", 1: "Sí"})
            registros_df_display["justificado"] = registros_df_display["justificado"].map({0: "No", 1: "Sí"})
            registros_df_display["es_feriado"] = registros_df_display["es_feriado"].map({0: "No", 1: "Sí"})
            registros_df_display["es_tardanza"] = registros_df_display["es_tardanza"].map({0: "No", 1: "Sí"})
            registros_df_display["horas_extras_calculadas"] = registros_df_display["horas_extras_calculadas"].apply(lambda x: f"{x:,.2f}" if x > 0 else "")


            st.dataframe(registros_df_display.rename(columns={
                "es_tardanza": "Tardanza (No Just.)",
                "horas_extras_calculadas": "Horas Extra (hs)",
                "justificacion_path": "Doc. Justificación",
                "observacion": "Observación"
            }), use_container_width=True)


    # -------------------------------
    # TAB 2: LIQUIDACIÓN
    # -------------------------------
    with tab2:
        st.subheader(f"💰 Liquidación de Sueldos de {empleado_nombre}")

        if empleado_id and mes_num and anio:
            
            col_options_1, col_options_2 = st.columns(2)
            
            with col_options_1:
                pagar_horas_extras = st.checkbox(
                    "✅ Pagar Horas Extras Calculadas", 
                    value=True,
                    help="Desmarca esta opción para anular el pago de todas las horas extras para este período."
                )
            
            with col_options_2:
                override_presentismo = st.checkbox(
                    "💵 Pagar Bono Presentismo (Override)", 
                    value=False,
                    help="Marca esta opción para pagar el bono de presentismo incluso si no se cumplieron los requisitos (tardanzas o ausencias)."
                )


            st.markdown("---") 
            
            empleado_info = get_empleado_info(empleado_id)
            registros_df = get_asistencia_empleado(empleado_id, mes_num, anio) 
            registros_df_calculado = preparar_df_asistencia(registros_df.copy(), empleado_info)
            dias_info = get_dias_habiles_y_feriados(mes_num, anio)

            detalle_liquid, info_adicional = calcular_liquidacion(
                empleado_info, 
                registros_df_calculado, 
                dias_info,
                pagar_horas_extras,
                override_presentismo
            )
            
            st.header(f"Boleta de Sueldo de {empleado_info['nombre']}")
            st.subheader(f"Período: {mes_str} {anio}")
            
            pdf_bytes = create_liquid_pdf(empleado_info, mes_num, anio, detalle_liquid, info_adicional)
            pdf_filename = f"Liquidacion_{empleado_info['nombre'].replace(' ', '_')}_{anio}_{mes_num:02d}.pdf"
            
            st.download_button(
                label="⬇️ Descargar Liquidación (PDF)",
                data=pdf_bytes,
                file_name=pdf_filename,
                mime="application/pdf"
            )

            st.markdown("---")
            
            colA, colB = st.columns(2)
            with colA:
                st.metric("Sueldo Fijo Mensual", f"${detalle_liquid['Sueldo Fijo Mensual']:,.2f}")
                st.metric("Bono Objetivo (10%)", f"${detalle_liquid['Bono Objetivo (10%)']:,.2f}")
            with colB:
                presentismo_status = "✅ Aplica" if info_adicional['Bono Presentismo Aplica'] else "❌ No Aplica"
                if info_adicional['Override Presentismo']:
                    presentismo_status = f"✅ Pagado (Override)"

                st.metric("Bono Presentismo", f"${detalle_liquid['Bono Presentismo']:,.2f}", delta=presentismo_status)
                if not info_adicional['Bono Presentismo Aplica'] and not info_adicional['Override Presentismo']:
                    st.error(f"Motivo No Pago (Lógica): {info_adicional['Motivo Pérdida Presentismo']}")
                
                pago_he_label = f"{info_adicional['Horas Extras Totales']} ({'Pagadas' if info_adicional['Pagar Horas Extras'] else 'NO Pagadas'})"
                st.metric("Horas Extras a Pagar (1x)", pago_he_label)
            
            st.markdown("---")
            
            st.subheader("Detalle de Haberes y Descuentos")
            
            data = {
                "Concepto": [
                    "Sueldo Fijo Mensual", 
                    "Bono Objetivo (10%)", 
                    "Bono Presentismo", 
                    "Pago Horas Extras (1x)", 
                    "Descuento Ausencias No Justificadas"
                ],
                "Monto": [
                    detalle_liquid["Sueldo Fijo Mensual"],
                    detalle_liquid["Bono Objetivo (10%)"],
                    detalle_liquid["Bono Presentismo"],
                    detalle_liquid["Pago Horas Extras (1x)"], 
                    detalle_liquid["Descuento Ausencias No Justificadas"]
                ]
            }
            df_detalle = pd.DataFrame(data)
            
            def color_descuento(val):
                color = 'red' if val < 0 else 'green'
                return f'color: {color}'
            
            df_detalle_styled = df_detalle.style \
                .format({"Monto": "U$S {:,.2f}"}) \
                .map(color_descuento, subset=['Monto']) 

            st.dataframe(df_detalle_styled, use_container_width=True, hide_index=True)

            st.markdown("---")
            
            st.markdown(f"## 💵 Total Neto a Pagar: **${detalle_liquid['Sueldo Neto']:,.2f}**")
            
            st.markdown("---")
            
            with st.expander("Información Técnica del Período"):
                info_df = pd.DataFrame(list(info_adicional.items()), columns=['Concepto', 'Valor'])
                
                conceptos_monetarios = ['Valor Hora Extra (1x Redondeado)', 'Valor Día de Descuento (Preciso)']
                conceptos_precisos = ['Valor Hora Normal (Base Precisa)']

                info_df['Valor'] = info_df.apply(
                    lambda row: f"${row['Valor']:,.2f}" if row['Concepto'] in conceptos_monetarios else \
                                 f"{row['Valor']:.6f}" if row['Concepto'] in conceptos_precisos else \
                                 row['Valor'], 
                    axis=1
                )
                
                info_df['Valor'] = info_df['Valor'].astype(str)
                
                st.table(info_df.style.hide(axis="index"))

if __name__ == "__main__":
    main()