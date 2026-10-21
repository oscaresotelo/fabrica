import streamlit as st
import sqlite3
import pandas as pd
import json
from pathlib import Path

# ─── CONFIG ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Minerva · Análisis de Costos",
    page_icon="⚗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── ESTILOS ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&display=swap');

:root {
    --bg: #0d0f14;
    --surface: #151820;
    --surface2: #1c2030;
    --border: #252a3a;
    --accent: #c8ff4e;
    --accent2: #4ef0ff;
    --danger: #ff5a5a;
    --text: #f0f2fa;
    --muted: #a0a8bc;
    --green: #4ade80;
    --yellow: #fbbf24;
}

html, body, [data-testid="stAppViewContainer"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 16px !important;
}

[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}

[data-testid="stSidebar"] * {
    color: var(--text) !important;
}

h1, h2, h3 {
    font-family: 'Syne', sans-serif !important;
    color: var(--text) !important;
}

.titulo-principal {
    font-family: 'Syne', sans-serif;
    font-size: 2.4rem;
    font-weight: 800;
    letter-spacing: -1px;
    line-height: 1.1;
    color: var(--text);
    margin-bottom: 0.2rem;
}

.titulo-principal span {
    color: var(--accent);
}

.subtitulo {
    font-family: 'DM Mono', monospace;
    font-size: 1rem;
    color: var(--muted);
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 2rem;
}

.metric-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.6rem;
}

.metric-label {
    font-size: 0.88rem;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 0.3rem;
    font-family: 'DM Mono', monospace;
}

.metric-value {
    font-family: 'Syne', sans-serif;
    font-size: 2rem;
    font-weight: 700;
    color: var(--text);
}

.metric-value.accent { color: var(--accent); }
.metric-value.green  { color: var(--green); }
.metric-value.danger { color: var(--danger); }
.metric-value.yellow { color: var(--yellow); }
.metric-value.blue   { color: var(--accent2); }

.section-header {
    font-family: 'Syne', sans-serif;
    font-size: 0.9rem;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--muted);
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border);
    margin: 1.2rem 0 0.8rem 0;
}

.costo-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border);
    font-size: 1rem;
}

.costo-row:last-child { border-bottom: none; }
.costo-nombre { color: var(--text); }
.costo-monto  { font-family: 'DM Mono', monospace; color: var(--accent); font-weight: 500; }
.costo-porce  { font-size: 0.88rem; color: var(--muted); margin-left: 0.6rem; }

.pill {
    display: inline-block;
    padding: 0.2rem 0.7rem;
    border-radius: 20px;
    font-size: 0.82rem;
    font-family: 'DM Mono', monospace;
    letter-spacing: 1px;
    text-transform: uppercase;
}
.pill-green  { background: rgba(74,222,128,0.15); color: var(--green); border: 1px solid rgba(74,222,128,0.3); }
.pill-red    { background: rgba(255,90,90,0.15);  color: var(--danger); border: 1px solid rgba(255,90,90,0.3); }
.pill-yellow { background: rgba(251,191,36,0.15); color: var(--yellow); border: 1px solid rgba(251,191,36,0.3); }

.ganancia-bar-container {
    height: 8px;
    background: var(--border);
    border-radius: 4px;
    overflow: hidden;
    margin-top: 0.4rem;
}

.ganancia-bar {
    height: 100%;
    border-radius: 4px;
    transition: width 0.5s ease;
}

.block-box {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.5rem;
}

.ingrediente-row {
    display: flex;
    justify-content: space-between;
    font-size: 0.96rem;
    padding: 0.3rem 0;
    border-bottom: 1px solid var(--border);
    color: var(--text);
}
.ingrediente-row:last-child { border-bottom: none; }

.tag-sin-precio {
    font-size: 0.78rem;
    color: var(--danger);
    background: rgba(255,90,90,0.1);
    padding: 0.1rem 0.5rem;
    border-radius: 4px;
    border: 1px solid rgba(255,90,90,0.2);
}

/* Streamlit overrides - inputs con fondo blanco y texto negro para legibilidad */

/* Number inputs */
.stNumberInput input {
    background: #ffffff !important;
    color: #111111 !important;
    border: 1px solid #cccccc !important;
    border-radius: 8px !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 1rem !important;
    font-weight: 600 !important;
}
.stNumberInput input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px rgba(200,255,78,0.25) !important;
}

/* Text inputs */
.stTextInput input {
    background: #ffffff !important;
    color: #111111 !important;
    border: 1px solid #cccccc !important;
    border-radius: 8px !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 1rem !important;
}
.stTextInput input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px rgba(200,255,78,0.25) !important;
}

/* Selectbox - fondo blanco texto negro en todos los estados */
.stSelectbox > div > div,
.stSelectbox [data-baseweb="select"],
.stSelectbox [data-baseweb="select"] > div,
.stSelectbox [data-baseweb="select"] > div > div {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: #111111 !important;
    border-color: #cccccc !important;
    border-radius: 8px !important;
    font-family: 'DM Mono', monospace !important;
}
/* Texto del valor seleccionado */
.stSelectbox [data-baseweb="select"] span,
.stSelectbox [data-baseweb="select"] div[class*="ValueContainer"] *,
.stSelectbox [data-baseweb="select"] div[class*="singleValue"],
.stSelectbox [data-baseweb="select"] input,
.stSelectbox [data-baseweb="select"] [data-testid="stSelectbox"] {
    color: #111111 !important;
    font-weight: 600 !important;
    font-family: 'DM Mono', monospace !important;
}
/* Icono flecha del selectbox */
.stSelectbox [data-baseweb="select"] svg {
    fill: #111111 !important;
}
/* Dropdown abierto */
[data-baseweb="popover"],
[data-baseweb="popover"] ul,
[data-baseweb="menu"] {
    background: #ffffff !important;
    background-color: #ffffff !important;
}
[data-baseweb="popover"] [role="option"],
[data-baseweb="menu"] [role="option"] {
    background: #ffffff !important;
    color: #111111 !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.95rem !important;
}
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="menu"] [role="option"]:hover,
[data-baseweb="popover"] [aria-selected="true"],
[data-baseweb="menu"] [aria-selected="true"] {
    background: #e8f5e9 !important;
    color: #111111 !important;
}

/* Labels de inputs y selectbox */
.stNumberInput label,
.stTextInput label,
.stSelectbox label,
.stSlider label,
.stCheckbox label {
    color: var(--text) !important;
    font-size: 0.92rem !important;
    font-family: 'DM Mono', monospace !important;
}

.stSlider > div { color: var(--text) !important; }
[data-testid="stMetric"] { display: none; }

div[data-testid="column"] { gap: 0 !important; }

.stButton > button {
    background: var(--accent) !important;
    color: #0d0f14 !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 8px !important;
    letter-spacing: 1px !important;
}

.stButton > button:hover {
    background: #d4ff66 !important;
}

.aviso {
    background: rgba(255,90,90,0.08);
    border: 1px solid rgba(255,90,90,0.25);
    border-radius: 8px;
    padding: 0.8rem 1.1rem;
    font-size: 0.96rem;
    color: var(--danger);
    margin-bottom: 0.8rem;
}

.info-box {
    background: rgba(78,240,255,0.05);
    border: 1px solid rgba(78,240,255,0.2);
    border-radius: 8px;
    padding: 0.8rem 1.1rem;
    font-size: 0.96rem;
    color: var(--accent2);
    margin-bottom: 0.8rem;
}

/* tabs */
button[data-baseweb="tab"] {
    font-family: 'DM Mono', monospace !important;
    font-size: 0.75rem !important;
    letter-spacing: 1px !important;
    color: var(--muted) !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
}

[data-testid="stDataFrameResizable"] {
    background: var(--surface) !important;
}

</style>
""", unsafe_allow_html=True)


# ─── DB CONNECTION ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_conn():
    """Retorna conexión a la base de datos. Ajustar la ruta si es necesario."""
    db_path = Path("minerva.db")
    if not db_path.exists():
        # buscar en directorio del script
        db_path = Path(__file__).parent / "minerva.db"
    return sqlite3.connect(str(db_path), check_same_thread=False)


def query(sql, params=()):
    conn = get_conn()
    return pd.read_sql_query(sql, conn, params=params)


# ─── FUNCIONES DE DATOS ────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_clientes():
    return query("SELECT id, nombre FROM clientes ORDER BY nombre")


@st.cache_data(ttl=60)
def get_productos_por_cliente(cliente_id):
    return query("""
        SELECT p.id, p.nombre, p.id_receta, p.envase_id, p.tipo_caja_id,
               e.descripcion as envase_desc, e.capacidad_litros
        FROM productos p
        LEFT JOIN envases e ON p.envase_id = e.id
        WHERE p.cliente_id = ?
        ORDER BY p.nombre
    """, (cliente_id,))


@st.cache_data(ttl=60)
def get_ultimo_precio_venta(cliente_id, producto_id, envase_id):
    df = query("""
        SELECT precio_unitario, fecha_desde
        FROM precios_productos_envasados
        WHERE cliente_id = ? AND producto_id = ? AND envase_id = ?
          AND fecha_hasta IS NULL
        ORDER BY fecha_desde DESC
        LIMIT 1
    """, (cliente_id, producto_id, envase_id))
    if df.empty:
        # intento sin envase_id (más permisivo)
        df = query("""
            SELECT precio_unitario, fecha_desde
            FROM precios_productos_envasados
            WHERE cliente_id = ? AND producto_id = ?
              AND fecha_hasta IS NULL
            ORDER BY fecha_desde DESC
            LIMIT 1
        """, (cliente_id, producto_id))
    return (df.iloc[0]["precio_unitario"], df.iloc[0]["fecha_desde"]) if not df.empty else (None, None)


@st.cache_data(ttl=60)
def get_ingredientes_con_precio(receta_id):
    """Devuelve ingredientes de la receta con su último precio unitario."""
    df = query("""
        SELECT ri.materia_prima_id, mp.nombre, ri.cantidad, ri.unidad,
               (SELECT pmp.precio_unitario
                FROM precios_materias_primas pmp
                WHERE pmp.materia_prima_id = ri.materia_prima_id
                ORDER BY pmp.fecha DESC
                LIMIT 1) as precio_unitario,
               (SELECT pmp.fecha
                FROM precios_materias_primas pmp
                WHERE pmp.materia_prima_id = ri.materia_prima_id
                ORDER BY pmp.fecha DESC
                LIMIT 1) as precio_fecha
        FROM receta_ingredientes ri
        JOIN materias_primas mp ON ri.materia_prima_id = mp.id
        WHERE ri.receta_id = ?
        ORDER BY ri.cantidad DESC
    """, (receta_id,))
    df["costo_linea"] = df["cantidad"] * df["precio_unitario"].fillna(0)
    return df


@st.cache_data(ttl=60)
def get_ultimo_precio_envase(envase_id):
    df = query("""
        SELECT precio_unitario, fecha_ingreso
        FROM entradas_envases
        WHERE envase_id = ?
        ORDER BY fecha_ingreso DESC
        LIMIT 1
    """, (envase_id,))
    return (df.iloc[0]["precio_unitario"], df.iloc[0]["fecha_ingreso"]) if not df.empty else (None, None)


@st.cache_data(ttl=60)
def get_info_caja(tipo_caja_id):
    df = query("SELECT descripcion, unidades_por_caja FROM tipo_cajas WHERE id = ?", (tipo_caja_id,))
    return df.iloc[0] if not df.empty else None


@st.cache_data(ttl=60)
def get_overhead():
    """Calcula overhead total: gastos + sueldos de empleados."""
    df_gastos = query("SELECT importe_total, moneda FROM gastos")
    df_emp = query("SELECT sueldo_base FROM empleados")
    total_gastos = df_gastos["importe_total"].sum() if not df_gastos.empty else 0
    total_sueldos = df_emp["sueldo_base"].sum() if not df_emp.empty else 0
    return total_gastos, total_sueldos, total_gastos + total_sueldos


@st.cache_data(ttl=60)
def get_flete_receta(receta_id):
    df = query("""
        SELECT monto FROM costos_flete_recetas
        WHERE receta_id = ?
        ORDER BY fecha_desde DESC
        LIMIT 1
    """, (receta_id,))
    return df.iloc[0]["monto"] if not df.empty else 0.0


@st.cache_data(ttl=60)
def get_all_gastos():
    return query("""
        SELECT g.fecha_factura, g.beneficiario_nombre, ci.nombre as categoria,
               g.importe_total, g.moneda, g.observaciones
        FROM gastos g
        LEFT JOIN categorias_imputacion ci ON g.categoria_id = ci.id
        ORDER BY g.fecha_factura DESC
    """)


@st.cache_data(ttl=60)
def get_all_empleados():
    return query("SELECT nombre, sueldo_base FROM empleados ORDER BY nombre")



@st.cache_data(ttl=60)
def get_cotizacion_dolar():
    """Retorna (compra, venta, fecha_hora) de cotizacion_dolar."""
    df = query("SELECT compra, venta, fecha_hora FROM cotizacion_dolar ORDER BY fecha_hora DESC LIMIT 1")
    if df.empty:
        return None, None, None
    return float(df.iloc[0]["compra"]), float(df.iloc[0]["venta"]), str(df.iloc[0]["fecha_hora"])

# ─── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="titulo-principal">⚗️ Minerva · <span>Costos</span></div>
<div class="subtitulo">análisis de rentabilidad por producto</div>
""", unsafe_allow_html=True)

# ─── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="section-header">Filtros</div>', unsafe_allow_html=True)

    clientes_df = get_clientes()
    cliente_opciones = {row["nombre"]: row["id"] for _, row in clientes_df.iterrows()}
    cliente_sel = st.selectbox("Cliente", list(cliente_opciones.keys()))
    cliente_id = cliente_opciones[cliente_sel]

    productos_df = get_productos_por_cliente(cliente_id)
    if productos_df.empty:
        st.warning("Sin productos para este cliente.")
        st.stop()

    prod_opciones = {row["nombre"]: row for _, row in productos_df.iterrows()}
    prod_sel = st.selectbox("Producto", list(prod_opciones.keys()))
    prod_row = prod_opciones[prod_sel]

    st.markdown('<div class="section-header">Parámetros</div>', unsafe_allow_html=True)

    capacidad_planta = st.number_input(
        "Capacidad planta (litros/mes)", min_value=1000, max_value=200000,
        value=32000, step=1000,
        help="Se usa para distribuir el overhead por litro producido."
    )

    margen_objetivo = st.slider(
        "Margen ganancia deseado (%)", min_value=0, max_value=200, value=30
    )

    precio_venta_manual = st.number_input(
        "Precio venta manual (ARS, 0 = usar BD)",
        min_value=0.0, value=0.0, step=100.0,
        help="Si es > 0 sobreescribe el precio de la base de datos."
    )

    st.markdown('<div class="section-header">Cotizacion Dolar</div>', unsafe_allow_html=True)
    dolar_compra_bd, dolar_venta_bd, dolar_fecha_bd = get_cotizacion_dolar()
    dolar_default = float(dolar_venta_bd or 1400.0)
    cotizacion_dolar = st.number_input(
        "Cotizacion USD → ARS",
        min_value=1.0, value=dolar_default, step=10.0,
        help="Se aplica al precio de envases (que estan en USD). Se precarga desde la BD."
    )
    if dolar_fecha_bd:
        st.markdown(
            f'<div style="font-size:0.8rem; color:var(--muted); margin-top:-0.4rem; margin-bottom:0.5rem;">' +
            f'BD: compra ${dolar_compra_bd:,.0f} / venta ${dolar_venta_bd:,.0f}<br>' +
            f'Actualizado: {dolar_fecha_bd[:10]}</div>',
            unsafe_allow_html=True
        )

    st.markdown('<div class="section-header">Opciones</div>', unsafe_allow_html=True)
    mostrar_ingredientes = st.checkbox("Ver detalle ingredientes", value=True)
    mostrar_overhead_detalle = st.checkbox("Ver detalle overhead", value=False)


# ─── DATOS DEL PRODUCTO SELECCIONADO ──────────────────────────────────────────
receta_id   = prod_row.get("id_receta")
envase_id   = prod_row.get("envase_id")
tipo_caja_id = prod_row.get("tipo_caja_id")
prod_id     = int(prod_row["id"])
cap_litros  = float(prod_row.get("capacidad_litros") or 1.0)
envase_desc = prod_row.get("envase_desc") or "—"

# ── Costo de insumos (receta) ──────────────────────────────────────────────────
costo_insumos = 0.0
ingred_df = pd.DataFrame()
avisos_sin_precio = []

if receta_id and str(receta_id).strip() not in ("", "None"):
    ingred_df = get_ingredientes_con_precio(int(receta_id))
    sin_precio = ingred_df[ingred_df["precio_unitario"].isna() | (ingred_df["precio_unitario"] == 0)]
    avisos_sin_precio = sin_precio["nombre"].tolist()
    # Costo por 200 litros de receta → escalar a capacidad_litros del envase
    costo_receta_200L = ingred_df["costo_linea"].sum()
    costo_insumos = costo_receta_200L * cap_litros / 200.0
else:
    avisos_sin_precio = ["⚠ Producto sin receta asignada"]

# ── Costo envase (precio en USD → convertir a ARS) ──────────────────────────────
precio_envase_usd = 0.0
fecha_envase = None
if envase_id:
    _pe, fecha_envase = get_ultimo_precio_envase(int(envase_id))
    precio_envase_usd = float(_pe or 0)
costo_envase = precio_envase_usd * cotizacion_dolar

# ── Costo caja (por unidad) ────────────────────────────────────────────────────
costo_caja_por_unidad = 0.0
caja_info = None
if tipo_caja_id:
    caja_info = get_info_caja(int(tipo_caja_id))

# ── Overhead por unidad ────────────────────────────────────────────────────────
total_gastos, total_sueldos, total_overhead = get_overhead()
overhead_por_litro = total_overhead / capacidad_planta if capacidad_planta > 0 else 0
overhead_por_unidad = overhead_por_litro * 1.0  # siempre 1 litro fijo

# ── Flete de receta (por litro) → por unidad ──────────────────────────────────
flete_receta_por_unidad = 0.0
if receta_id and str(receta_id).strip() not in ("", "None"):
    flete_total = get_flete_receta(int(receta_id))
    # flete_total es por lote de 200L; escalar a litros del envase
    flete_receta_por_unidad = flete_total * cap_litros / 200.0

# ── Costo total por unidad ─────────────────────────────────────────────────────
costo_total = costo_insumos + costo_envase + costo_caja_por_unidad + overhead_por_unidad + flete_receta_por_unidad

# ── Precio de venta ────────────────────────────────────────────────────────────
precio_bd, fecha_precio_bd = get_ultimo_precio_venta(cliente_id, prod_id, int(envase_id) if envase_id else 0)
precio_venta = precio_venta_manual if precio_venta_manual > 0 else (float(precio_bd or 0))

# ── Precio sugerido (con margen objetivo) ─────────────────────────────────────
precio_sugerido = costo_total * (1 + margen_objetivo / 100) if costo_total > 0 else 0

# ── Ganancia ──────────────────────────────────────────────────────────────────
ganancia_abs   = precio_venta - costo_total if precio_venta > 0 else 0
ganancia_pct   = (ganancia_abs / precio_venta * 100) if precio_venta > 0 else 0
markup_pct     = (ganancia_abs / costo_total * 100) if costo_total > 0 else 0


# ─── AVISOS ───────────────────────────────────────────────────────────────────
if avisos_sin_precio:
    for av in avisos_sin_precio[:3]:
        st.markdown(f'<div class="aviso">⚠ Sin precio: <b>{av}</b></div>', unsafe_allow_html=True)

if precio_venta == 0:
    st.markdown('<div class="info-box">ℹ No hay precio de venta registrado. Usá el precio manual en el panel lateral o cargá uno en la base de datos.</div>', unsafe_allow_html=True)


# ─── LAYOUT PRINCIPAL ─────────────────────────────────────────────────────────
tabs = st.tabs(["📊 Resumen", "🧪 Ingredientes", "🏭 Overhead", "📋 Comparativa"])

# ══════════════════════════════════════════════════════════════
# TAB 1 — RESUMEN
# ══════════════════════════════════════════════════════════════
with tabs[0]:
    col1, col2 = st.columns([1.1, 0.9], gap="medium")

    with col1:
        st.markdown('<div class="section-header">Desglose de costo por unidad</div>', unsafe_allow_html=True)

        def fila_costo(nombre, valor, total, icono=""):
            pct = (valor / total * 100) if total > 0 else 0
            st.markdown(f"""
            <div class="costo-row">
                <span class="costo-nombre">{icono} {nombre}</span>
                <span>
                    <span class="costo-monto">$ {valor:,.2f}</span>
                    <span class="costo-porce">{pct:.1f}%</span>
                </span>
            </div>
            """, unsafe_allow_html=True)

        fila_costo("Insumos (receta)", costo_insumos, costo_total, "🧬")
        fila_costo("Envase", costo_envase, costo_total, "🫙")
        fila_costo("Caja / Embalaje", costo_caja_por_unidad, costo_total, "📦")
        fila_costo("Overhead (indirectos)", overhead_por_unidad, costo_total, "🏭")
        fila_costo("Flete receta", flete_receta_por_unidad, costo_total, "🚛")

        st.markdown(f"""
        <div style="margin-top:0.8rem; padding:0.8rem 0; border-top: 2px solid var(--accent);">
            <div class="costo-row" style="border:none; padding:0;">
                <span style="font-family:'Syne',sans-serif; font-weight:700; font-size:1rem;">COSTO TOTAL UNITARIO</span>
                <span style="font-family:'Syne',sans-serif; font-weight:800; font-size:1.2rem; color:var(--accent);">$ {costo_total:,.2f}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # envase info
        st.markdown(f"""
        <div class="block-box" style="margin-top:1rem;">
            <div style="font-size:0.85rem; letter-spacing:2px; color:var(--muted); text-transform:uppercase; margin-bottom:0.5rem;">Envase / Presentación</div>
            <div style="font-size:1.05rem;">{envase_desc} &nbsp;·&nbsp; <span style="color:var(--muted);">{cap_litros} L/unidad</span></div>
            {"<div style='font-size:0.88rem; color:var(--muted); margin-top:0.4rem;'>Último precio: <b>USD " + f"{precio_envase_usd:,.3f}</b> = <b>ARS $ {costo_envase:,.2f}</b> ({fecha_envase})</div>" if fecha_envase else ""}
        </div>
        """, unsafe_allow_html=True)

        if caja_info is not None:
            st.markdown(f"""
            <div class="block-box">
                <div style="font-size:0.85rem; letter-spacing:2px; color:var(--muted); text-transform:uppercase; margin-bottom:0.5rem;">Caja</div>
                <div style="font-size:1.05rem;">{caja_info['descripcion']}</div>
                <div style="font-size:0.88rem; color:var(--muted); margin-top:0.3rem;">{caja_info['unidades_por_caja']} unidades por caja</div>
            </div>
            """, unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="section-header">Precio de venta y ganancia</div>', unsafe_allow_html=True)

        # Precio de venta
        fuente_precio = "manual" if precio_venta_manual > 0 else ("base de datos" if precio_bd else "—")
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Precio de venta ({fuente_precio})</div>
            <div class="metric-value blue">$ {precio_venta:,.2f}</div>
            {"<div style='font-size:0.7rem; color:var(--muted); margin-top:0.2rem;'>vigente desde " + str(fecha_precio_bd) + "</div>" if fecha_precio_bd and precio_venta_manual == 0 else ""}
        </div>
        """, unsafe_allow_html=True)

        # Ganancia absoluta
        color_gan = "green" if ganancia_abs > 0 else "danger"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Ganancia por unidad</div>
            <div class="metric-value {color_gan}">$ {ganancia_abs:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)

        # Margen %
        pill_class = "pill-green" if ganancia_pct >= 20 else ("pill-yellow" if ganancia_pct >= 10 else "pill-red")
        bar_color = "var(--green)" if ganancia_pct >= 20 else ("var(--yellow)" if ganancia_pct >= 10 else "var(--danger)")
        bar_width = min(abs(ganancia_pct), 100)

        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Margen neto &nbsp;<span class="pill {pill_class}">{ganancia_pct:.1f}%</span></div>
            <div class="metric-value {color_gan}">{ganancia_pct:.1f}%</div>
            <div class="ganancia-bar-container">
                <div class="ganancia-bar" style="width:{bar_width}%; background:{bar_color};"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Markup
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Markup sobre costo</div>
            <div class="metric-value yellow">{markup_pct:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-header" style="margin-top:1.4rem;">Precio sugerido</div>', unsafe_allow_html=True)

        diferencia = precio_sugerido - precio_venta
        dif_pct = (diferencia / precio_venta * 100) if precio_venta > 0 else 0
        dif_color = "var(--green)" if diferencia <= 0 else "var(--danger)"
        dif_signo = "+" if diferencia > 0 else ""

        st.markdown(f"""
        <div class="block-box">
            <div style="font-size:0.85rem; letter-spacing:2px; color:var(--muted); text-transform:uppercase; margin-bottom:0.6rem;">
                Con {margen_objetivo}% de margen objetivo
            </div>
            <div style="font-family:'Syne',sans-serif; font-size:1.8rem; font-weight:800; color:var(--accent2);">
                $ {precio_sugerido:,.2f}
            </div>
            <div style="font-size:0.9rem; margin-top:0.5rem; color:{dif_color};">
                {dif_signo}$ {diferencia:,.2f} &nbsp;({dif_signo}{dif_pct:.1f}%) vs. precio actual
            </div>
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# TAB 2 — INGREDIENTES
# ══════════════════════════════════════════════════════════════
with tabs[1]:
    if ingred_df.empty:
        st.markdown('<div class="aviso">Sin receta asignada a este producto.</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="info-box">Receta ID: <b>{receta_id}</b> · Escala: 200 L base → {cap_litros} L/unidad ({cap_litros/200*100:.1f}%)</div>', unsafe_allow_html=True)

        col_h1, col_h2, col_h3, col_h4 = st.columns([3, 1, 1, 1])
        with col_h1: st.markdown('<div style="font-size:0.85rem; letter-spacing:2px; color:var(--muted); text-transform:uppercase;">Ingrediente</div>', unsafe_allow_html=True)
        with col_h2: st.markdown('<div style="font-size:0.85rem; letter-spacing:2px; color:var(--muted); text-transform:uppercase;">Cantidad</div>', unsafe_allow_html=True)
        with col_h3: st.markdown('<div style="font-size:0.85rem; letter-spacing:2px; color:var(--muted); text-transform:uppercase;">$ / unidad</div>', unsafe_allow_html=True)
        with col_h4: st.markdown('<div style="font-size:0.85rem; letter-spacing:2px; color:var(--muted); text-transform:uppercase;">Costo línea</div>', unsafe_allow_html=True)

        st.markdown('<hr style="border-color:var(--border); margin:0.4rem 0;">', unsafe_allow_html=True)

        for _, row in ingred_df.iterrows():
            sin_p = pd.isna(row["precio_unitario"]) or row["precio_unitario"] == 0
            costo_escalado = row["costo_linea"] * cap_litros / 200.0
            col1i, col2i, col3i, col4i = st.columns([3, 1, 1, 1])
            with col1i:
                tag = '<span class="tag-sin-precio">sin precio</span>' if sin_p else ""
                st.markdown(f'<div style="font-size:0.96rem; padding:0.4rem 0;">{row["nombre"]} {tag}</div>', unsafe_allow_html=True)
            with col2i:
                st.markdown(f'<div style="font-size:0.96rem; padding:0.4rem 0; color:var(--muted);">{row["cantidad"]} {row["unidad"]}</div>', unsafe_allow_html=True)
            with col3i:
                pu = row["precio_unitario"] if not sin_p else 0
                st.markdown(f'<div style="font-size:0.96rem; padding:0.4rem 0; color:var(--accent2);">$ {pu:,.2f}</div>', unsafe_allow_html=True)
            with col4i:
                color = "var(--muted)" if sin_p else "var(--accent)"
                st.markdown(f'<div style="font-size:0.96rem; padding:0.4rem 0; color:{color};">$ {costo_escalado:,.2f}</div>', unsafe_allow_html=True)

        st.markdown('<hr style="border-color:var(--border); margin:0.6rem 0;">', unsafe_allow_html=True)
        col_t1, _, _, col_t4 = st.columns([3, 1, 1, 1])
        with col_t1: st.markdown('<div style="font-family:\'Syne\',sans-serif; font-weight:700; font-size:1.05rem;">TOTAL INSUMOS</div>', unsafe_allow_html=True)
        with col_t4: st.markdown(f'<div style="font-family:\'Syne\',sans-serif; font-weight:800; font-size:1.05rem; color:var(--accent);">$ {costo_insumos:,.2f}</div>', unsafe_allow_html=True)

        if mostrar_ingredientes:
            st.markdown('<div class="section-header" style="margin-top:1.5rem;">Participación por ingrediente</div>', unsafe_allow_html=True)
            df_chart = ingred_df.copy()
            df_chart["costo_escalado"] = df_chart["costo_linea"] * cap_litros / 200.0
            df_chart = df_chart[df_chart["costo_escalado"] > 0].sort_values("costo_escalado", ascending=False)
            if not df_chart.empty:
                df_chart["% del costo"] = (df_chart["costo_escalado"] / df_chart["costo_escalado"].sum() * 100).round(1)
                st.bar_chart(df_chart.set_index("nombre")["costo_escalado"], color="#c8ff4e")


# ══════════════════════════════════════════════════════════════
# TAB 3 — OVERHEAD
# ══════════════════════════════════════════════════════════════
with tabs[2]:
    col_ov1, col_ov2 = st.columns(2, gap="medium")

    with col_ov1:
        st.markdown('<div class="section-header">Estructura de overhead</div>', unsafe_allow_html=True)

        def mini_card(label, valor, color="var(--text)"):
            st.markdown(f"""
            <div class="metric-card" style="padding:0.9rem 1.1rem;">
                <div class="metric-label">{label}</div>
                <div style="font-family:'Syne',sans-serif; font-weight:700; font-size:1.3rem; color:{color};">$ {valor:,.0f}</div>
            </div>
            """, unsafe_allow_html=True)

        mini_card("Total gastos operativos", total_gastos, "var(--accent2)")
        mini_card("Total sueldos empleados", total_sueldos, "var(--yellow)")
        mini_card("OVERHEAD TOTAL", total_overhead, "var(--accent)")

        st.markdown(f"""
        <div class="block-box" style="margin-top:1rem;">
            <div class="metric-label">Capacidad de planta</div>
            <div style="font-size:1.2rem; font-weight:700;">{capacidad_planta:,.0f} L / mes</div>
            <div style="font-size:0.92rem; color:var(--muted); margin-top:0.5rem;">
                Overhead por litro: <b style="color:var(--accent);">$ {overhead_por_litro:,.2f}</b>
            </div>
            <div style="font-size:0.92rem; color:var(--muted);">
                Overhead por unidad (1L fijo): <b style="color:var(--accent);">$ {overhead_por_unidad:,.2f}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_ov2:
        st.markdown('<div class="section-header">Empleados</div>', unsafe_allow_html=True)
        emp_df = get_all_empleados()
        for _, e in emp_df.iterrows():
            st.markdown(f"""
            <div class="costo-row">
                <span class="costo-nombre">{e['nombre']}</span>
                <span class="costo-monto">$ {e['sueldo_base']:,.0f}</span>
            </div>
            """, unsafe_allow_html=True)

    if mostrar_overhead_detalle:
        st.markdown('<div class="section-header" style="margin-top:1.5rem;">Detalle de gastos</div>', unsafe_allow_html=True)
        gastos_df = get_all_gastos()
        if not gastos_df.empty:
            st.dataframe(
                gastos_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "importe_total": st.column_config.NumberColumn("Importe", format="$ %.0f"),
                    "fecha_factura": "Fecha",
                    "beneficiario_nombre": "Beneficiario",
                    "categoria": "Categoría",
                    "moneda": "Moneda",
                    "observaciones": "Obs.",
                }
            )


# ══════════════════════════════════════════════════════════════
# TAB 4 — COMPARATIVA DE PRODUCTOS
# ══════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown('<div class="section-header">Todos los productos del cliente</div>', unsafe_allow_html=True)
    st.markdown('<div class="info-box">Se usa el overhead calculado con los parámetros del panel lateral. Solo se muestran productos con precio de venta registrado.</div>', unsafe_allow_html=True)

    rows_comp = []
    for _, prod in productos_df.iterrows():
        p_id = int(prod["id"])
        p_receta = prod.get("id_receta")
        p_envase = prod.get("envase_id")
        p_caja   = prod.get("tipo_caja_id")
        p_cap    = float(prod.get("capacidad_litros") or 1.0)

        # insumos
        ci = 0.0
        if p_receta and str(p_receta).strip() not in ("", "None"):
            try:
                idf = get_ingredientes_con_precio(int(p_receta))
                ci = idf["costo_linea"].sum() * p_cap / 200.0
            except Exception:
                ci = 0.0

        # envase (USD -> ARS)
        ce = 0.0
        if p_envase:
            try:
                pe, _ = get_ultimo_precio_envase(int(p_envase))
                ce = float(pe or 0) * cotizacion_dolar
            except Exception:
                ce = 0.0

        # overhead
        oh = overhead_por_litro * 1.0  # siempre 1 litro fijo

        # flete
        fl = 0.0
        if p_receta and str(p_receta).strip() not in ("", "None"):
            try:
                fl = get_flete_receta(int(p_receta)) * p_cap / 200.0
            except Exception:
                fl = 0.0

        costo_u = ci + ce + oh + fl

        # precio venta
        p_env_id = int(p_envase) if p_envase else 0
        pv, _ = get_ultimo_precio_venta(cliente_id, p_id, p_env_id)
        pv = float(pv or 0)

        if pv == 0:
            continue  # saltar si no hay precio

        gan = pv - costo_u
        margen = (gan / pv * 100) if pv > 0 else 0

        rows_comp.append({
            "Producto": prod["nombre"],
            "Envase": prod.get("envase_desc") or "—",
            "Cap (L)": p_cap,
            "Costo insumos": round(ci, 2),
            "Costo envase": round(ce, 2),
            "Overhead": round(oh, 2),
            "Flete": round(fl, 2),
            "COSTO TOTAL": round(costo_u, 2),
            "Precio venta": round(pv, 2),
            "Ganancia": round(gan, 2),
            "Margen %": round(margen, 1),
        })

    if rows_comp:
        df_comp = pd.DataFrame(rows_comp).sort_values("Margen %", ascending=False)

        st.dataframe(
            df_comp,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Costo insumos":  st.column_config.NumberColumn(format="$ %.2f"),
                "Costo envase":   st.column_config.NumberColumn(format="$ %.2f"),
                "Overhead":       st.column_config.NumberColumn(format="$ %.2f"),
                "Flete":          st.column_config.NumberColumn(format="$ %.2f"),
                "COSTO TOTAL":    st.column_config.NumberColumn(format="$ %.2f"),
                "Precio venta":   st.column_config.NumberColumn(format="$ %.2f"),
                "Ganancia":       st.column_config.NumberColumn(format="$ %.2f"),
                "Margen %":       st.column_config.ProgressColumn(
                    "Margen %", min_value=0, max_value=100, format="%.1f%%"
                ),
            }
        )

        st.markdown('<div class="section-header" style="margin-top:1.5rem;">Margen por producto</div>', unsafe_allow_html=True)
        df_chart2 = df_comp.set_index("Producto")["Margen %"]
        st.bar_chart(df_chart2, color="#4ef0ff")
    else:
        st.markdown('<div class="aviso">No hay productos con precio de venta registrado para este cliente.</div>', unsafe_allow_html=True)