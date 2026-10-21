import streamlit as st
import sqlite3
import pandas as pd
import datetime
import locale
import calendar
import os
import io
import base64
import re 
from collections import defaultdict
from fpdf import FPDF 

# -------------------------------
# Configuración
# -------------------------------
DB_PATH = "minerva.db"
try:
    locale.setlocale(locale.LC_ALL, "es_ES.UTF-8")
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, "es_ES")
    except locale.Error:
        pass 

TOLERANCIA_PRESENTISMO_MIN = 10
LIMITE_TARDANZAS = 3
EMPLEADOS_PRESENTISMO_ESPECIAL = ["Gerardo", "Cristian", "Gabriel"] 

# -------------------------------
# Funciones auxiliares de DB
# -------------------------------
def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS empleados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    sueldo_base REAL NOT NULL,
                    horas_jornada_diaria REAL NOT NULL,
                    horario_entrada TEXT NOT NULL,
                    horario_salida TEXT NOT NULL
                )''')
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
    conn = get_connection()
    c = conn.cursor()
    entrada = hora_entrada if hora_entrada else None
    salida = hora_salida if hora_salida else None
    c.execute("SELECT id FROM asistencia WHERE empleado_id = ? AND fecha = ?", (empleado_id, fecha_str))
    record = c.fetchone()
    if record:
        c.execute("""
            UPDATE asistencia 
            SET hora_entrada_real = ?, hora_salida_real = ?, ausente = 0, justificado = 0,
                justificacion_path = NULL, observacion = ?
            WHERE id = ?
        """, (entrada, salida, "[Carga Manual/Bulk]", record[0]))
    else:
        c.execute("""
            INSERT INTO asistencia (empleado_id, fecha, hora_entrada_real, hora_salida_real, ausente, justificado, observacion) 
            VALUES (?, ?, ?, ?, 0, 0, ?)
        """, (empleado_id, fecha_str, entrada, salida, "[Carga Manual/Bulk]"))
    conn.close()

def justificar_dia_ausente(empleado_id, fecha_str, justificacion_path, observacion):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM asistencia WHERE empleado_id = ? AND fecha = ?", (empleado_id, fecha_str))
    record = c.fetchone()
    path_str = justificacion_path if justificacion_path else ''
    if record:
        c.execute("UPDATE asistencia SET ausente = 1, justificado = 1, justificacion_path = ?, observacion = ? WHERE id = ?", (path_str, observacion, record[0]))
    else:
        c.execute("INSERT INTO asistencia (empleado_id, fecha, ausente, justificado, justificacion_path, observacion) VALUES (?, ?, 1, 1, ?, ?)", (empleado_id, fecha_str, path_str, observacion))
    conn.close()

def force_unjustified_absence(empleado_id, fecha_str, observacion):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM asistencia WHERE empleado_id = ? AND fecha = ?", (empleado_id, fecha_str))
    record = c.fetchone()
    if record:
        c.execute("UPDATE asistencia SET ausente = 1, justificado = 0, observacion = ? WHERE id = ?", (observacion, record[0]))
    else:
        c.execute("INSERT INTO asistencia (empleado_id, fecha, ausente, justificado, observacion) VALUES (?, ?, 1, 0, ?)", (empleado_id, fecha_str, observacion))
    conn.close()

def get_asistencia_empleado(empleado_id, mes, anio):
    conn = get_connection()
    mes_str = f"{mes:02d}"
    query = "SELECT * FROM asistencia WHERE empleado_id = ? AND substr(fecha, 1, 4) = ? AND substr(fecha, 6, 2) = ? ORDER BY fecha"
    df_registros = pd.read_sql_query(query, conn, params=(empleado_id, str(anio), mes_str))
    conn.close()
    
    inicio_mes = datetime.date(anio, mes, 1)
    dias_del_mes = calendar.monthrange(anio, mes)[1]
    dias_habiles_laborables = [(inicio_mes + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(dias_del_mes) if (inicio_mes + datetime.timedelta(days=i)).weekday() < 5]
    df_completo = pd.merge(pd.DataFrame(dias_habiles_laborables, columns=['fecha']), df_registros, on='fecha', how='left')
    df_completo[['ausente', 'justificado', 'es_feriado']] = df_completo[['ausente', 'justificado', 'es_feriado']].fillna(0).astype(int)
    df_completo.loc[df_completo['hora_entrada_real'].isna() & (df_completo['justificado'] == 0), 'ausente'] = 1
    return df_completo

def parse_raw_attendance_data(raw_text):
    timestamp_pattern = re.compile(r'(\d{4}-\d{2}-\d{2})\s(\d{2}:\d{2}:\d{2})')
    daily_events = defaultdict(list)
    for line in raw_text.splitlines():
        match = timestamp_pattern.search(line)
        if match:
            daily_events[match.group(1)].append(match.group(2)[:5])
    return [{'fecha': d, 'hora_entrada': min(t), 'hora_salida': max(t)} for d, t in daily_events.items()]

# -------------------------------
# Lógica de Liquidación
# -------------------------------
def get_feriados_nacionales(mes, anio):
    feriados = []
    if mes == 9: 
        try:
            fecha_feriado = datetime.date(anio, 9, 24)
            if fecha_feriado.weekday() < 5: feriados.append(fecha_feriado)
        except ValueError: pass
    return feriados

def get_dias_habiles_y_feriados(mes, anio):
    inicio_mes = datetime.date(anio, mes, 1)
    dias_base_divisor = 0
    feriados = get_feriados_nacionales(mes, anio)
    dias_feriados_habiles = 0
    fecha_actual = inicio_mes
    while fecha_actual.month == mes:
        if fecha_actual.weekday() < 5:
            dias_base_divisor += 1
            if fecha_actual in feriados: dias_feriados_habiles += 1
        fecha_actual += datetime.timedelta(days=1)
    return {"dias_base_divisor": dias_base_divisor, "dias_feriados_habiles": dias_feriados_habiles}

def preparar_df_asistencia(df_asistencia, empleado_info):
    fmt = "%H:%M"
    horario_entrada = datetime.datetime.strptime(empleado_info["horario_entrada"], fmt)
    horario_salida = datetime.datetime.strptime(empleado_info["horario_salida"], fmt)
    df_asistencia['es_tardanza'] = 0
    df_asistencia['horas_extras_calculadas'] = 0.0
    for idx, row in df_asistencia.iterrows():
        try:
            if row['ausente'] == 0 and row['hora_entrada_real']:
                if datetime.datetime.strptime(row['hora_entrada_real'], fmt) > (horario_entrada + datetime.timedelta(minutes=TOLERANCIA_PRESENTISMO_MIN)):
                    if row['justificado'] == 0: df_asistencia.loc[idx, 'es_tardanza'] = 1
            if row['ausente'] == 0 and row['hora_salida_real']:
                salida_real = datetime.datetime.strptime(row['hora_salida_real'], fmt)
                if salida_real > horario_salida:
                    df_asistencia.loc[idx, 'horas_extras_calculadas'] = (salida_real - horario_salida).total_seconds() / 3600
        except: pass
    return df_asistencia

def calcular_liquidacion(empleado_info, registros_asistencia_df, dias_info, pagar_extras=True, override_pres=False, override_horas_extras=None):
    # --- CONFIGURACIÓN DE DIVISOR FIJO ---
    DIVISOR_FIJO_DIAS = 22.0  # Se usa 22 para estandarizar el valor de la hora
    
    sueldo_base = empleado_info["sueldo_base"]
    horas_j = empleado_info["horas_jornada_diaria"]
    
    # El valor de la hora ahora es constante, sin importar los días del mes
    val_hora_norm = (sueldo_base / DIVISOR_FIJO_DIAS / horas_j)
    val_hora_extra = round(val_hora_norm, 2)
    
    # Lógica de Horas Extras (Manual o Auto)
    total_hs_extras = override_horas_extras if override_horas_extras is not None else registros_asistencia_df["horas_extras_calculadas"].sum()
    monto_extras = round(total_hs_extras * val_hora_extra, 2) if pagar_extras else 0.0
    
    # Presentismo
    tardanzas = registros_asistencia_df["es_tardanza"].sum()
    faltas_ij = registros_asistencia_df[(registros_asistencia_df["ausente"] == 1) & (registros_asistencia_df["justificado"] == 0)].shape[0]
    
    pierde_pres = (faltas_ij >= 1 or tardanzas > LIMITE_TARDANZAS)
    bono_pres_monto = (110000.0 if empleado_info["nombre"] in EMPLEADOS_PRESENTISMO_ESPECIAL else 60500.0)
    bono_pres = bono_pres_monto if (not pierde_pres or override_pres) else 0.0
    
    # El descuento por faltas también se basa en el valor hora fijo
    descuento_faltas = round(faltas_ij * (val_hora_norm * horas_j), 2)
    
    bono_obj = sueldo_base * 0.10
    neto = round(sueldo_base + bono_obj + bono_pres + monto_extras - descuento_faltas, 2)
    
    detalle = {
        "Sueldo Fijo Mensual": sueldo_base, 
        "Bono Objetivo (10%)": bono_obj,
        "Bono Presentismo": bono_pres, 
        "Pago Horas Extras (1x)": monto_extras,
        "Descuento Ausencias No Justificadas": -descuento_faltas, 
        "Sueldo Neto": neto
    }
    
    info = {
        "Días Base (Fijo)": DIVISOR_FIJO_DIAS, 
        "Horas Extras Totales": f"{total_hs_extras:,.2f} hs",
        "Tardanzas No Just.": tardanzas, 
        "Días Ausentes No Just.": faltas_ij,
        "Bono Presentismo Aplica": not pierde_pres, 
        "Override Presentismo": override_pres
    }
    return detalle, info
# -------------------------------
# PDF
# -------------------------------
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Boleta de Liquidación de Sueldos', 0, 1, 'C')
    def footer(self):
        self.set_y(-15); self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', 0, 0, 'C')

def create_liquid_pdf(empleado_info, mes, anio, detalle, info_ad):
    pdf = PDF(); pdf.alias_nb_pages(); pdf.add_page()
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 5, f"Colaborador: {empleado_info['nombre']}", 0, 1)
    pdf.cell(0, 5, f"Período: {calendar.month_name[mes].capitalize()} {anio}", 0, 1)
    pdf.ln(5)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(140, 7, "Concepto", 1, 0, 'L', 1); pdf.cell(40, 7, "Monto", 1, 1, 'R', 1)
    for k, v in detalle.items():
        if k != "Sueldo Neto":
            pdf.cell(140, 6, k, 1); pdf.cell(40, 6, f"$ {v:,.2f}", 1, 1, 'R')
    pdf.set_font('Arial', 'B', 12); pdf.cell(140, 10, "TOTAL NETO", 1); pdf.cell(40, 10, f"$ {detalle['Sueldo Neto']:,.2f}", 1, 1, 'R')
    return bytes(pdf.output(dest='S'))

# -------------------------------
# Interfaz
# -------------------------------
def main():
    st.set_page_config(page_title="Gestión de Sueldos", layout="wide")
    init_db()
    emps = get_empleados()
    if emps.empty: st.error("No hay empleados."); return
    emps_dict = dict(zip(emps["nombre"], emps["id"]))

    st.sidebar.title("Configuración")
    emp_nom = st.sidebar.selectbox("Empleado", list(emps_dict.keys()))
    emp_id = emps_dict[emp_nom]
    mes = st.sidebar.selectbox("Mes", list(range(1, 13)), index=datetime.date.today().month-1)
    anio = st.sidebar.number_input("Año", 2000, 2100, 2025)

    tab0, tab1, tab2 = st.tabs(["➕ Carga Asistencia", "📋 Gestión Asistencia", "💰 Liquidación"])

    with tab0:
        st.subheader("Carga de Registros")
        raw = st.text_area("Pegar datos del reloj checador", height=200)
        if st.button("Procesar Carga Masiva"):
            res = parse_raw_attendance_data(raw)
            for r in res: insert_attendance_record(emp_id, r['fecha'], r['hora_entrada'], r['hora_salida'])
            st.success(f"Cargados {len(res)} registros."); st.rerun()

    with tab1:
        info_e = get_empleado_info(emp_id)
        df_as = preparar_df_asistencia(get_asistencia_empleado(emp_id, mes, anio), info_e)
        st.dataframe(df_as, use_container_width=True)

    with tab2:
        st.subheader("Liquidación y Ajustes")
        col1, col2, col3 = st.columns(3)
        with col1: pagar_ex = st.checkbox("Pagar Horas Extras", True)
        with col2: over_pres = st.checkbox("Forzar Pago Presentismo", False)
        
        # --- AJUSTE MANUAL DE HORAS EXTRAS ---
        info_e = get_empleado_info(emp_id)
        df_as = preparar_df_asistencia(get_asistencia_empleado(emp_id, mes, anio), info_e)
        hs_auto = df_as["horas_extras_calculadas"].sum()
        
        with col3:
            hs_manual = st.number_input("⏱️ Ajustar Total Horas Extras", 0.0, 500.0, float(hs_auto), 0.5)
        
        det, inf_a = calcular_liquidacion(info_e, df_as, get_dias_habiles_y_feriados(mes, anio), pagar_ex, over_pres, hs_manual)
        
        st.metric("TOTAL NETO A COBRAR", f"$ {det['Sueldo Neto']:,.2f}")
        st.table(pd.DataFrame([det]).T.rename(columns={0: "Monto"}))
        
        pdf = create_liquid_pdf(info_e, mes, anio, det, inf_a)
        st.download_button("⬇️ Descargar PDF", pdf, f"Liquidacion_{emp_nom}_{mes}_{anio}.pdf", "application/pdf")

if __name__ == "__main__":
    main()