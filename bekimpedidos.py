import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "minerva.db"
CLIENTE_ID = 8
CLIENTE_NOMBRE = "BEKIM"

# ── Estado config ────────────────────────────────────────────────────────────
ESTADOS = {
    "producido":  {"color": "#00C896", "bg": "#00C89615", "label": "PRODUCIDO",  "icon": "✦"},
    "pendiente":  {"color": "#F59E0B", "bg": "#F59E0B15", "label": "PENDIENTE",  "icon": "◎"},
    "en_proceso": {"color": "#3B82F6", "bg": "#3B82F615", "label": "EN PROCESO", "icon": "◉"},
}

# ── DB ───────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

@st.cache_data(ttl=30)
def load_pedidos():
    query = """
        SELECT
            pp.id                  AS pedido_id,
            pp.numero_pedido,
            pp.fecha               AS fecha_pedido,
            pp.estado              AS estado_pedido,
            pp.lote,
            pp.cantidad            AS litros_solicitados,
            r.nombre               AS producto,
            pr.id                  AS produccion_id,
            pr.fecha               AS fecha_produccion,
            pr.estado              AS estado_produccion,
            pr.cantidad_litros     AS litros_producidos
        FROM pedidos_produccion pp
        LEFT JOIN recetas  r  ON pp.receta_id  = r.id
        LEFT JOIN producciones pr ON pr.pedido_id = pp.id
        WHERE pp.cliente_id = ?
          AND LOWER(pp.estado) != 'anulado'
        ORDER BY pp.fecha DESC
    """
    return pd.read_sql_query(query, get_conn(), params=(CLIENTE_ID,))

def fmt_fecha(valor):
    if not valor or pd.isna(valor):
        return "—"
    s = str(valor).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return s

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title=f"Producción · {CLIENTE_NOMBRE}",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body, [data-testid="stAppViewContainer"], .main {
    background: #0A0D14 !important;
    color: #E8EAF0;
    font-family: 'DM Sans', sans-serif;
}

[data-testid="stAppViewContainer"] { background: #0A0D14 !important; }
[data-testid="stHeader"] { background: transparent !important; }
section[data-testid="stSidebar"] { background: #0D1017 !important; }

.block-container {
    padding: 2rem 2.5rem 4rem !important;
    max-width: 1400px;
}

/* ── Header ── */
.hero {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    padding: 2rem 0 1.5rem;
    border-bottom: 1px solid #1E2230;
    margin-bottom: 2rem;
}
.hero-badge {
    width: 52px; height: 52px;
    background: linear-gradient(135deg, #00C896, #007A5E);
    border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem;
    box-shadow: 0 8px 24px #00C89640;
    flex-shrink: 0;
}
.hero-text h1 {
    font-family: 'Syne', sans-serif;
    font-size: 1.9rem;
    font-weight: 800;
    color: #FFFFFF;
    letter-spacing: -.03em;
    line-height: 1;
}
.hero-text p {
    font-size: .85rem;
    color: #8A93AA;
    margin-top: .3rem;
    font-weight: 300;
}
.hero-client {
    margin-left: auto;
    background: #131720;
    border: 1px solid #1E2230;
    border-radius: 10px;
    padding: .5rem 1.2rem;
    text-align: right;
}
.hero-client span { display: block; }
.hero-client .lbl { font-size: .7rem; color: #8A93AA; text-transform: uppercase; letter-spacing: .1em; }
.hero-client .val { font-family: 'Syne', sans-serif; font-size: 1.1rem; font-weight: 700; color: #00C896; }

/* ── KPI strip ── */
.kpi-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 2rem; }
.kpi-card {
    background: #0F1319;
    border: 1px solid #1E2230;
    border-radius: 16px;
    padding: 1.2rem 1.5rem;
    position: relative;
    overflow: hidden;
    transition: border-color .2s;
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
}
.kpi-card.green::before { background: linear-gradient(90deg, #00C896, transparent); }
.kpi-card.amber::before { background: linear-gradient(90deg, #F59E0B, transparent); }
.kpi-card.blue::before  { background: linear-gradient(90deg, #3B82F6, transparent); }
.kpi-card:hover { border-color: #2E3448; }

.kpi-num {
    font-family: 'Syne', sans-serif;
    font-size: 2.6rem;
    font-weight: 800;
    line-height: 1;
    margin-bottom: .3rem;
}
.kpi-card.green .kpi-num { color: #00C896; }
.kpi-card.amber .kpi-num { color: #F59E0B; }
.kpi-card.blue  .kpi-num { color: #3B82F6; }
.kpi-lbl { font-size: .78rem; color: #9AA3BA; text-transform: uppercase; letter-spacing: .08em; }
.kpi-icon {
    position: absolute;
    right: 1.2rem; top: 50%; transform: translateY(-50%);
    font-size: 2rem; opacity: .12;
}

/* ── Filters ── */
.filter-bar {
    background: #0F1319;
    border: 1px solid #1E2230;
    border-radius: 16px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 1.5rem;
    display: flex;
    gap: 1rem;
    align-items: center;
    flex-wrap: wrap;
}
.filter-label {
    font-size: .7rem;
    color: #5A6075;
    text-transform: uppercase;
    letter-spacing: .1em;
    margin-bottom: .3rem;
}

/* ── Streamlit widget overrides ── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stTextInput"] > div > div > input {
    background: #131720 !important;
    border: 1px solid #1E2230 !important;
    border-radius: 10px !important;
    color: #E8EAF0 !important;
    font-family: 'DM Sans', sans-serif !important;
}
[data-testid="stSelectbox"] > div > div:hover,
[data-testid="stTextInput"] > div > div > input:focus {
    border-color: #00C896 !important;
    box-shadow: 0 0 0 2px #00C89625 !important;
}
label[data-testid="stWidgetLabel"] p {
    font-family: 'DM Sans', sans-serif !important;
    font-size: .75rem !important;
    color: #9AA3BA !important;
    text-transform: uppercase;
    letter-spacing: .08em;
}
[data-testid="stButton"] button {
    background: #00C896 !important;
    color: #000 !important;
    border: none !important;
    border-radius: 10px !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    font-size: .8rem !important;
    letter-spacing: .05em;
}
[data-testid="stButton"] button:hover {
    background: #00D9A6 !important;
    box-shadow: 0 4px 16px #00C89650 !important;
}
[data-testid="stDownloadButton"] button {
    background: #131720 !important;
    color: #00C896 !important;
    border: 1px solid #00C89640 !important;
    border-radius: 10px !important;
    font-family: 'DM Sans', sans-serif !important;
}

/* ── Detail card ── */
.det-card {
    background: #0F1319;
    border: 1px solid #1E2230;
    border-radius: 18px;
    padding: 1.6rem 1.8rem;
    margin-bottom: 1rem;
    position: relative;
    overflow: hidden;
    transition: border-color .25s, transform .15s;
}
.det-card:hover { border-color: #2E3448; transform: translateY(-2px); }
.det-card .accent-line {
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 4px;
    border-radius: 18px 0 0 18px;
}
.det-card-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 1rem;
}
.det-num {
    font-family: 'Syne', sans-serif;
    font-size: 1.3rem;
    font-weight: 800;
    color: #FFFFFF;
    letter-spacing: -.02em;
}
.det-producto {
    font-size: .88rem;
    color: #A8AEBE;
    margin-top: .15rem;
    font-weight: 400;
}
.estado-pill {
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    padding: .3rem .9rem;
    border-radius: 999px;
    font-size: .72rem;
    font-weight: 700;
    letter-spacing: .1em;
    text-transform: uppercase;
    border: 1px solid;
    white-space: nowrap;
}
.det-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: .8rem;
}
.det-field {}
.det-field-lbl {
    font-size: .67rem;
    color: #7A839A;
    text-transform: uppercase;
    letter-spacing: .1em;
    margin-bottom: .25rem;
}
.det-field-val {
    font-size: .95rem;
    font-weight: 500;
    color: #D8DCE8;
}
.det-field-val.mono {
    font-family: 'Courier New', monospace;
    font-size: .8rem;
    color: #9AA3BA;
}
.lote-tag {
    display: inline-block;
    background: #131720;
    border: 1px solid #2A3048;
    border-radius: 6px;
    padding: .15rem .5rem;
    font-family: monospace;
    font-size: .75rem;
    color: #9AA3BA;
}

/* ── Results count ── */
.results-count {
    font-size: .78rem;
    color: #7A839A;
    margin-bottom: 1rem;
    text-transform: uppercase;
    letter-spacing: .08em;
}
.results-count strong { color: #00C896; }

/* ── Table ── */
[data-testid="stDataFrame"] {
    border-radius: 14px !important;
    overflow: hidden;
    border: 1px solid #1E2230 !important;
}

/* ── Section title ── */
.sec-title {
    font-family: 'Syne', sans-serif;
    font-size: 1rem;
    font-weight: 700;
    color: #E8EAF0;
    letter-spacing: -.01em;
    margin: 1.5rem 0 1rem;
    display: flex;
    align-items: center;
    gap: .5rem;
}
.sec-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: #1E2230;
}

/* ── Divider ── */
hr { border: none; border-top: 1px solid #1E2230 !important; margin: 1.5rem 0 !important; }

/* ── No results ── */
.no-results {
    text-align: center;
    padding: 3rem;
    color: #3D4460;
    font-size: .9rem;
}
.no-results span { font-size: 2.5rem; display: block; margin-bottom: .5rem; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0A0D14; }
::-webkit-scrollbar-thumb { background: #1E2230; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ── Hero header ──────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="hero">
  <div class="hero-badge">⬡</div>
  <div class="hero-text">
    <h1>Control de Producción</h1>
    <p>Trazabilidad de pedidos · Estado en tiempo real</p>
  </div>
  <div class="hero-client">
    <span class="lbl">Cliente</span>
    <span class="val">{CLIENTE_NOMBRE}</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Carga de datos ────────────────────────────────────────────────────────────
df = load_pedidos()

if df.empty:
    st.markdown('<div class="no-results"><span>○</span>Sin pedidos para este cliente.</div>', unsafe_allow_html=True)
    st.stop()

# ── KPIs ──────────────────────────────────────────────────────────────────────
total      = len(df)
producidos = (df["estado_pedido"] == "producido").sum()
pendientes = total - producidos

st.markdown(f"""
<div class="kpi-strip">
  <div class="kpi-card green">
    <div class="kpi-icon">✦</div>
    <div class="kpi-num">{producidos}</div>
    <div class="kpi-lbl">Producidos</div>
  </div>
  <div class="kpi-card amber">
    <div class="kpi-icon">◎</div>
    <div class="kpi-num">{pendientes}</div>
    <div class="kpi-lbl">Pendientes</div>
  </div>
  <div class="kpi-card blue">
    <div class="kpi-icon">⬡</div>
    <div class="kpi-num">{total}</div>
    <div class="kpi-lbl">Total activos</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Filtros ────────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([1, 2, 1])

estados_opts = ["Todos"] + sorted(df["estado_pedido"].dropna().unique().tolist())
filtro_estado = col1.selectbox("Estado", estados_opts)

productos_opts = ["Todos"] + sorted(df["producto"].dropna().unique().tolist())
filtro_producto = col2.selectbox("Producto / Receta", productos_opts)

busqueda = col3.text_input("N° de pedido", placeholder="ej: 1113-1")

# Aplicar filtros
dff = df.copy()
if filtro_estado != "Todos":
    dff = dff[dff["estado_pedido"] == filtro_estado]
if filtro_producto != "Todos":
    dff = dff[dff["producto"] == filtro_producto]
if busqueda.strip():
    dff = dff[dff["numero_pedido"].astype(str).str.contains(busqueda.strip(), case=False)]

# ── Selector principal ────────────────────────────────────────────────────────
numeros = dff["numero_pedido"].astype(str).tolist()
pedido_sel = st.selectbox(
    "Pedido seleccionado",
    ["— Mostrar todos —"] + numeros,
)

if pedido_sel != "— Mostrar todos —":
    df_vista = dff[dff["numero_pedido"].astype(str) == pedido_sel]
else:
    df_vista = dff

st.markdown(f'<p class="results-count"><strong>{len(df_vista)}</strong> registros encontrados</p>', unsafe_allow_html=True)

# ── Tarjetas ──────────────────────────────────────────────────────────────────
if df_vista.empty:
    st.markdown('<div class="no-results"><span>○</span>No hay pedidos con esos filtros.</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="sec-title">Detalle de pedidos</div>', unsafe_allow_html=True)

    # Limitar a 50 en vista "todos" para performance
    mostrar = df_vista.head(50) if pedido_sel == "— Mostrar todos —" else df_vista

    for _, row in mostrar.iterrows():
        ep = str(row["estado_pedido"]).lower() if row["estado_pedido"] else "pendiente"
        cfg = ESTADOS.get(ep, {"color": "#6B7394", "bg": "#6B739415", "label": ep.upper(), "icon": "○"})

        fecha_prod = fmt_fecha(row["fecha_produccion"]) if row["produccion_id"] else "—"
        lote_html  = f'<span class="lote-tag">{row["lote"]}</span>' if row["lote"] else '<span style="color:#3D4460">—</span>'

        litros_prod = f'{row["litros_producidos"]:.1f} L' if row["produccion_id"] and pd.notna(row["litros_producidos"]) else "—"

        st.markdown(f"""
        <div class="det-card">
          <div class="accent-line" style="background:{cfg['color']};"></div>
          <div class="det-card-head">
            <div>
              <div class="det-num">Pedido {row['numero_pedido']}</div>
              <div class="det-producto">{row['producto'] or '—'}</div>
            </div>
            <div class="estado-pill" style="color:{cfg['color']};border-color:{cfg['color']}40;background:{cfg['bg']};">
              {cfg['icon']} {cfg['label']}
            </div>
          </div>
          <div class="det-grid">
            <div class="det-field">
              <div class="det-field-lbl">📅 Fecha pedido</div>
              <div class="det-field-val">{fmt_fecha(row['fecha_pedido'])}</div>
            </div>
            <div class="det-field">
              <div class="det-field-lbl">🏭 Fecha producción</div>
              <div class="det-field-val">{fecha_prod}</div>
            </div>
            <div class="det-field">
              <div class="det-field-lbl">💧 Litros pedido</div>
              <div class="det-field-val">{row['litros_solicitados']:.1f} L</div>
            </div>
            <div class="det-field">
              <div class="det-field-lbl">⚗️ Litros producidos</div>
              <div class="det-field-val">{litros_prod}</div>
            </div>
            <div class="det-field" style="grid-column: span 2;">
              <div class="det-field-lbl">🏷️ Lote</div>
              <div class="det-field-val">{lote_html}</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    if pedido_sel == "— Mostrar todos —" and len(df_vista) > 50:
        st.markdown(f'<p style="text-align:center;color:#3D4460;font-size:.8rem;">Mostrando 50 de {len(df_vista)} registros. Usá los filtros para acotar la búsqueda.</p>', unsafe_allow_html=True)

    # ── Tabla resumen ─────────────────────────────────────────────────────────
    st.markdown('<div class="sec-title">Tabla resumen</div>', unsafe_allow_html=True)

    df_tabla = df_vista[[
        "numero_pedido", "fecha_pedido", "fecha_produccion",
        "estado_pedido", "producto", "litros_solicitados", "litros_producidos", "lote"
    ]].copy()

    df_tabla["fecha_pedido"]     = df_tabla["fecha_pedido"].apply(fmt_fecha)
    df_tabla["fecha_produccion"] = df_tabla["fecha_produccion"].apply(fmt_fecha)
    df_tabla["litros_solicitados"] = df_tabla["litros_solicitados"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
    df_tabla["litros_producidos"]  = df_tabla["litros_producidos"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
    df_tabla["lote"] = df_tabla["lote"].fillna("—")
    df_tabla.columns = ["N° Pedido", "Fecha Pedido", "Fecha Producción", "Estado", "Producto", "L. Pedido", "L. Producido", "Lote"]

    st.dataframe(df_tabla, use_container_width=True, hide_index=True)

    csv = df_tabla.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇ Exportar CSV",
        data=csv,
        file_name=f"producciones_{CLIENTE_NOMBRE}_{datetime.today().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )