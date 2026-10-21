import streamlit as st
import sqlite3
import pandas as pd
from collections import defaultdict

DB_PATH = "minerva.db"  # Ajustar al path real

st.set_page_config(
    page_title="Planificador de Producción – Minerva",
    page_icon="🧴",
    layout="wide"
)

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    .titulo-principal {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1a3c5e;
        margin-bottom: 0.2rem;
    }
    .subtitulo {
        font-size: 0.95rem;
        color: #6b7280;
        margin-bottom: 1.5rem;
    }
    .card-receta {
        background: #f0f7ff;
        border: 1px solid #bfdbfe;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }
    .card-receta-nombre {
        font-weight: 600;
        color: #1e40af;
        font-size: 1rem;
    }
    .card-receta-detalle {
        font-size: 0.82rem;
        color: #4b5563;
    }
    .metric-box {
        background: #f9fafb;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 10px 14px;
        text-align: center;
    }
    .total-litros {
        background: linear-gradient(135deg, #1a3c5e, #2563eb);
        color: white;
        border-radius: 10px;
        padding: 14px 20px;
        font-size: 1.1rem;
        font-weight: 600;
        margin-bottom: 1rem;
    }
    .sin-stock {
        color: #dc2626;
        font-weight: 600;
    }
    .con-stock {
        color: #16a34a;
    }
    .badge-litros {
        display: inline-block;
        background: #dbeafe;
        color: #1d4ed8;
        border-radius: 20px;
        padding: 2px 10px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Funciones DB
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def cargar_recetas():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT id, nombre FROM recetas ORDER BY nombre", conn)
    conn.close()
    return df


@st.cache_data(show_spinner=False)
def cargar_ingredientes_receta(receta_id: int):
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT
            mp.id           AS mp_id,
            mp.nombre       AS materia_prima,
            mp.unidad       AS unidad_mp,
            ri.cantidad     AS cantidad_base,
            ri.unidad       AS unidad_receta
        FROM receta_ingredientes ri
        JOIN materias_primas mp ON mp.id = ri.materia_prima_id
        WHERE ri.receta_id = ?
        ORDER BY mp.nombre
    """
    df = pd.read_sql(query, conn, params=(receta_id,))
    conn.close()
    return df


@st.cache_data(show_spinner=False)
def cargar_stock():
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT materia_prima_id, cantidad_actual
        FROM stock_materias_primas
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df.set_index("materia_prima_id")["cantidad_actual"].to_dict()


def calcular_consolidado(carrito: list[dict]) -> pd.DataFrame:
    """Retorna DataFrame consolidado con totales de cada materia prima."""
    if not carrito:
        return pd.DataFrame()

    BASE_LITROS = 200.0
    acumulado = defaultdict(lambda: {"materia_prima": "", "unidad": "", "total": 0.0})

    for item in carrito:
        factor = item["litros"] / BASE_LITROS
        ing = cargar_ingredientes_receta(item["receta_id"])
        for _, row in ing.iterrows():
            mp_id = row["mp_id"]
            acumulado[mp_id]["materia_prima"] = row["materia_prima"]
            acumulado[mp_id]["unidad"] = row["unidad_receta"]
            acumulado[mp_id]["total"] += row["cantidad_base"] * factor

    stock = cargar_stock()
    filas = []
    for mp_id, datos in acumulado.items():
        stock_disp = stock.get(mp_id, 0.0)
        necesito = round(datos["total"], 3)
        diferencia = round(stock_disp - necesito, 3)
        filas.append({
            "Materia Prima": datos["materia_prima"],
            "Unidad": datos["unidad"],
            "Necesario": necesito,
            "Stock Actual": round(stock_disp, 3),
            "Diferencia": diferencia,
            "_mp_id": mp_id,
        })

    return pd.DataFrame(filas).sort_values("Materia Prima").reset_index(drop=True)


def detalle_por_receta(receta_id: int, litros: float) -> pd.DataFrame:
    """Retorna ingredientes de una receta escalados a los litros pedidos."""
    BASE_LITROS = 200.0
    factor = litros / BASE_LITROS
    ing = cargar_ingredientes_receta(receta_id).copy()  # .copy() evita mutar el cache
    if ing.empty:
        return pd.DataFrame()
    col_litros = f"Para {litros:.0f} L"
    ing[col_litros] = (ing["cantidad_base"] * factor).round(3)
    return ing[["materia_prima", "cantidad_base", col_litros, "unidad_receta"]].rename(columns={
        "materia_prima": "Ingrediente",
        "cantidad_base": "Base 200 L",
        "unidad_receta": "Unidad",
    }).sort_values("Ingrediente").reset_index(drop=True)


# ─────────────────────────────────────────────
# Estado de sesión
# ─────────────────────────────────────────────
if "carrito" not in st.session_state:
    st.session_state.carrito = []   # lista de dicts


# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────
st.markdown('<div class="titulo-principal">🧴 Planificador de Producción</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitulo">Armá tu plan de producción sumando recetas y litros. Ves el consolidado total de materias primas en tiempo real.</div>', unsafe_allow_html=True)

col_izq, col_der = st.columns([1, 1.6], gap="large")

# ─────────────────────────────────────────────
# COLUMNA IZQUIERDA – Agregar receta
# ─────────────────────────────────────────────
with col_izq:
    st.markdown("### ➕ Agregar receta al plan")

    recetas_df = cargar_recetas()
    opciones = {row["nombre"]: row["id"] for _, row in recetas_df.iterrows()}

    receta_sel = st.selectbox(
        "Seleccioná la receta",
        options=list(opciones.keys()),
        index=0,
        key="sel_receta"
    )

    litros_sel = st.number_input(
        "Litros a producir",
        min_value=1.0,
        max_value=50000.0,
        value=200.0,
        step=50.0,
        format="%.0f",
        key="inp_litros"
    )

    # Preview de ingredientes de la receta seleccionada
    with st.expander("👁️ Ver ingredientes de esta receta (base 200 L)", expanded=False):
        rid = opciones[receta_sel]
        ing_preview = cargar_ingredientes_receta(rid)
        if ing_preview.empty:
            st.info("Esta receta no tiene ingredientes cargados.")
        else:
            factor_prev = litros_sel / 200.0
            ing_preview = ing_preview.copy()
            ing_preview["Para tus litros"] = (ing_preview["cantidad_base"] * factor_prev).round(3)
            st.dataframe(
                ing_preview[["materia_prima", "cantidad_base", "Para tus litros", "unidad_receta"]].rename(columns={
                    "materia_prima": "Ingrediente",
                    "cantidad_base": "Base 200 L",
                    "unidad_receta": "Unidad"
                }),
                use_container_width=True,
                hide_index=True
            )

    if st.button("➕ Agregar al plan", use_container_width=True, type="primary"):
        st.session_state.carrito.append({
            "receta_id": opciones[receta_sel],
            "receta_nombre": receta_sel,
            "litros": litros_sel,
        })
        st.success(f"✔ {receta_sel} ({litros_sel:.0f} L) agregado al plan.")
        st.rerun()

    # ── Lista del plan actual ──
    st.markdown("---")
    st.markdown("### 📋 Plan de producción")

    if not st.session_state.carrito:
        st.info("Todavía no agregaste ninguna receta al plan.")
    else:
        total_litros = sum(i["litros"] for i in st.session_state.carrito)
        st.markdown(f'<div class="total-litros">🔵 Total planificado: {total_litros:,.0f} Litros en {len(st.session_state.carrito)} batch(es)</div>', unsafe_allow_html=True)

        indices_a_borrar = []
        for idx, item in enumerate(st.session_state.carrito):
            col_a, col_b = st.columns([5, 1])
            with col_a:
                st.markdown(
                    f'<div class="card-receta">'
                    f'<div class="card-receta-nombre">{item["receta_nombre"]}</div>'
                    f'<div class="card-receta-detalle">📦 <span class="badge-litros">{item["litros"]:.0f} L</span></div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            with col_b:
                if st.button("🗑️", key=f"del_{idx}", help="Quitar del plan"):
                    indices_a_borrar.append(idx)

        if indices_a_borrar:
            st.session_state.carrito = [
                item for i, item in enumerate(st.session_state.carrito)
                if i not in indices_a_borrar
            ]
            st.rerun()

        if st.button("🗑️ Limpiar todo el plan", use_container_width=True):
            st.session_state.carrito = []
            st.rerun()


# ─────────────────────────────────────────────
# COLUMNA DERECHA – Consolidado
# ─────────────────────────────────────────────
with col_der:
    st.markdown("### 📊 Consolidado de Materias Primas")

    if not st.session_state.carrito:
        st.info("Agregá recetas al plan para ver el consolidado de materias primas necesarias.")
    else:
        resultado = calcular_consolidado(st.session_state.carrito)

        if resultado.empty:
            st.warning("No se encontraron ingredientes para las recetas seleccionadas.")
        else:
            df_consol = resultado

            # Métricas rápidas
            faltantes = (df_consol["Diferencia"] < 0).sum()
            col1, col2, col3 = st.columns(3)
            col1.metric("Ingredientes totales", len(df_consol))
            col2.metric("Con stock suficiente", len(df_consol) - faltantes)
            col3.metric("⚠️ Requieren compra", faltantes)

            # Filtro
            filtro = st.radio(
                "Mostrar:",
                ["Todos", "Requieren compra", "Stock suficiente"],
                horizontal=True
            )

            df_view = df_consol.copy()
            if filtro == "Requieren compra":
                df_view = df_view[df_view["Diferencia"] < 0]
            elif filtro == "Stock suficiente":
                df_view = df_view[df_view["Diferencia"] >= 0]

            df_view = df_view.drop(columns=["_mp_id"])

            def colorear_fila(row):
                if row["Diferencia"] < 0:
                    return ["background-color: #fef2f2; color: #991b1b"] * len(row)
                elif row["Diferencia"] == 0:
                    return ["background-color: #fffbeb; color: #92400e"] * len(row)
                else:
                    return ["background-color: #f0fdf4; color: #166534"] * len(row)

            styled = (
                df_view.style
                .apply(colorear_fila, axis=1)
                .format({
                    "Necesario": "{:,.3f}",
                    "Stock Actual": "{:,.3f}",
                    "Diferencia": "{:+,.3f}",
                })
            )

            st.dataframe(styled, use_container_width=True, hide_index=True, height=480)
            st.markdown(
                "🟥 **Falta stock** &nbsp;|&nbsp; "
                "🟨 **Stock justo** &nbsp;|&nbsp; "
                "🟩 **Stock suficiente**"
            )

            # Exportar
            st.markdown("---")
            csv_data = df_view.to_csv(index=False).encode("utf-8")
            col_exp1, col_exp2 = st.columns(2)
            with col_exp1:
                st.download_button(
                    "⬇️ Exportar CSV consolidado",
                    data=csv_data,
                    file_name="plan_materias_primas.csv",
                    mime="text/csv",
                    use_container_width=True
                )


# ─────────────────────────────────────────────
# SECCIÓN INFERIOR – Detalle por receta
# ─────────────────────────────────────────────
if st.session_state.carrito:
    st.markdown("---")
    st.markdown("## 🔬 Detalle de ingredientes por receta")

    # Generar etiquetas únicas para duplicados
    conteo = defaultdict(int)
    for item in st.session_state.carrito:
        conteo[item["receta_nombre"]] += 1
    vistos = defaultdict(int)
    etiquetas_det = []
    for item in st.session_state.carrito:
        nombre = item["receta_nombre"]
        if conteo[nombre] > 1:
            vistos[nombre] += 1
            etiquetas_det.append(f"{nombre} — Batch #{vistos[nombre]}")
        else:
            etiquetas_det.append(nombre)

    for idx, item in enumerate(st.session_state.carrito):
        etiqueta = etiquetas_det[idx]
        litros = item["litros"]
        col_litros = f"Para {litros:.0f} L"

        with st.expander(f"🧴  {etiqueta}   ·   {litros:.0f} L", expanded=True):
            df_det = detalle_por_receta(item["receta_id"], litros)
            if df_det.empty:
                st.info("Sin ingredientes cargados.")
            else:
                # Separar en dos grupos: los que tienen cantidad > 0 para esos litros
                col_izq_det, col_der_det = st.columns([2, 1])

                with col_izq_det:
                    st.caption(f"📋 {len(df_det)} ingredientes · Base formulada para 200 L · Escala aplicada: ×{litros/200:.2f}")
                    styled_det = (
                        df_det.style
                        .format({"Base 200 L": "{:,.3f}", col_litros: "{:,.3f}"})
                        .apply(lambda row: [
                            "",
                            "",
                            "background-color: #dbeafe; font-weight: 600; color: #1e40af",
                            ""
                        ], axis=1)
                    )
                    st.dataframe(
                        styled_det,
                        use_container_width=True,
                        hide_index=True,
                        height=min(38 * len(df_det) + 40, 500)
                    )

                with col_der_det:
                    st.caption("📊 Resumen")
                    total_kg = df_det.loc[df_det["Unidad"] == "KG", col_litros].sum()
                    total_lt = df_det.loc[df_det["Unidad"].isin(["LITROS", "LITRO"]), col_litros].sum()
                    st.metric("Total KG", f"{total_kg:,.3f}")
                    st.metric("Total Litros (mat.)", f"{total_lt:,.3f}")
                    st.metric("Litros a producir", f"{litros:,.0f}")