import streamlit as st
import sqlite3
import pandas as pd
from collections import defaultdict
import io
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# ── Config ────────────────────────────────#####################################
DB_PATH = "minerva.db"   # ajustá la ruta si es necesario

ESTADOS_VALIDOS = ["pendiente", "en proceso", "producido", "entregado", "anulado"]

ESTADOS_CONFIG = {
    "pendiente":   ("🟡", "#FFF9E6", "#856404"),
    "en proceso":  ("🔵", "#EAF3FF", "#004085"),
    "producido":   ("🟢", "#EAFAF1", "#155724"),
    "entregado":   ("✅", "#E8F8FB", "#0C5460"),
    "anulado":     ("🔴", "#FDF2F2", "#721C24"),
    "sin estado":  ("⚪", "#F0F0F0", "#555555"),
}

# ── DB helpers ─────────────────────────────────────────────────────────────────
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

@st.cache_data
def cargar_clientes():
    with get_conn() as conn:
        return pd.read_sql("SELECT id, nombre FROM clientes ORDER BY nombre", conn)

def cargar_pedidos_cliente(cliente_id: int):
    query = """
        SELECT
            p.id,
            p.numero_pedido,
            p.receta_id,
            r.nombre        AS producto,
            p.cantidad,
            p.fecha,
            COALESCE(NULLIF(TRIM(p.estado), ''), 'sin estado') AS estado,
            p.lote
        FROM pedidos_produccion p
        LEFT JOIN recetas r ON r.id = p.receta_id
        WHERE p.cliente_id = ?
        ORDER BY p.fecha DESC, CAST(p.numero_pedido AS INTEGER) DESC
    """
    with get_conn() as conn:
        return pd.read_sql(query, conn, params=[cliente_id])

def actualizar_estado(pedido_id: int, nuevo_estado: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE pedidos_produccion SET estado = ? WHERE id = ?",
            (nuevo_estado, pedido_id)
        )
        conn.commit()

def actualizar_estados_bulk(ids: list[int], nuevo_estado: str):
    with get_conn() as conn:
        conn.executemany(
            "UPDATE pedidos_produccion SET estado = ? WHERE id = ?",
            [(nuevo_estado, pid) for pid in ids]
        )
        conn.commit()

def render_badge(estado: str) -> str:
    key = estado.strip().lower()
    icono, bg, color = ESTADOS_CONFIG.get(key, ("⚪", "#E2E3E5", "#383D41"))
    return (
        f'<span style="background:{bg};color:{color};padding:2px 10px;'
        f'border-radius:12px;font-weight:600;font-size:0.82rem;">'
        f'{icono} {estado.upper()}</span>'
    )

def label_pedido(row) -> str:
    """Etiqueta única para un pedido: N°PEDIDO – PRODUCTO (id interno)."""
    return f"{row['numero_pedido']} – {row['producto']}  (id {row['id']})"

# ── Layout ─────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Pedidos – Minerva",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Pedidos de Producción")

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔎 Filtros")

    clientes_df = cargar_clientes()
    cliente_sel = st.selectbox("Cliente", clientes_df["nombre"].tolist())
    cliente_id = int(
        clientes_df.loc[clientes_df["nombre"] == cliente_sel, "id"].iloc[0]
    )

    st.divider()
    nro_filtro = st.text_input("N° de pedido (opcional)", placeholder="ej: 221")

    st.divider()
    estado_filtro = st.radio(
        "Filtrar por estado",
        ["Todos"] + [e.capitalize() for e in ESTADOS_VALIDOS],
    )

# ── Carga ──────────────────────────────────────────────────────────────────────
if "refresh" not in st.session_state:
    st.session_state.refresh = 0

@st.cache_data(show_spinner=False)
def _cargar(cliente_id, _refresh):
    return cargar_pedidos_cliente(cliente_id)

df = _cargar(cliente_id, st.session_state.refresh)

if df.empty:
    st.info(f"El cliente **{cliente_sel}** no tiene pedidos registrados.")
    st.stop()

if nro_filtro.strip():
    df = df[df["numero_pedido"].astype(str).str.contains(nro_filtro.strip(), case=False)]
    if df.empty:
        st.warning("No se encontraron pedidos con ese número.")
        st.stop()

if estado_filtro != "Todos":
    df_vista = df[df["estado"].str.lower() == estado_filtro.lower()].copy()
else:
    df_vista = df.copy()

# ── Métricas ───────────────────────────────────────────────────────────────────
st.subheader(f"Cliente: {cliente_sel}")

estados_presentes = df["estado"].str.lower().unique().tolist()
all_states_ordered = [e for e in ESTADOS_VALIDOS if e in estados_presentes] + \
                     [e for e in estados_presentes if e not in ESTADOS_VALIDOS]

cols_met = st.columns(len(all_states_ordered) + 1)
cols_met[0].metric("Total pedidos", len(df))
for i, estado in enumerate(all_states_ordered):
    count = len(df[df["estado"].str.lower() == estado])
    icono = ESTADOS_CONFIG.get(estado, ("⚪",))[0]
    cols_met[i + 1].metric(f"{icono} {estado.capitalize()}", count)

st.divider()

if df_vista.empty:
    st.info("No hay pedidos con ese estado para este cliente.")
    st.stop()

def color_fila(row):
    estado = row["Estado"].strip().lower()
    bg = ESTADOS_CONFIG.get(estado, ("", "#FFFFFF", ""))[1]
    return [f"background-color: {bg}" for _ in row]

tab_tabla, tab_editar, tab_mp_pedido, tab_mp, tab_remito = st.tabs([
    "📋 Ver pedidos", 
    "✏️ Cambiar estado", 
    "🔍 MP por Pedido", 
    "🧪 Materias primas pendientes", 
    "🖨️ Remito"
])

# ── Tab 1: tabla ───────────────────────────────────────────────────────────────
with tab_tabla:
    df_display = df_vista.rename(columns={
        "numero_pedido": "N° Pedido",
        "producto":      "Producto",
        "cantidad":      "Cantidad (L)",
        "fecha":         "Fecha",
        "estado":        "Estado",
        "lote":          "Lote",
    })
    cols_tabla = ["N° Pedido", "Producto", "Cantidad (L)", "Fecha", "Estado", "Lote"]
    styled = (
        df_display[cols_tabla]
        .style
        .apply(color_fila, axis=1)
        .format({"Cantidad (L)": "{:,.0f}"})
    )
    st.dataframe(styled, use_container_width=True, hide_index=True, height=500)

# ── Tab 2: editar estado ───────────────────────────────────────────────────────
with tab_editar:
    st.markdown("Seleccioná un pedido y cambiá su estado, o actualizá varios a la vez.")
    col_single, col_bulk = st.columns(2)

    with col_single:
        st.markdown("##### 🔄 Un pedido")
        df_vista_reset = df_vista.reset_index(drop=True)
        opciones_labels = [label_pedido(r) for _, r in df_vista_reset.iterrows()]
        id_por_label = {label_pedido(r): int(r["id"]) for _, r in df_vista_reset.iterrows()}

        label_sel = st.selectbox("Pedido", opciones_labels, key="sel_individual")
        pedido_id_sel = id_por_label[label_sel]
        row_sel = df_vista_reset[df_vista_reset["id"] == pedido_id_sel].iloc[0]

        st.markdown(f"Estado actual: {render_badge(row_sel['estado'])}", unsafe_allow_html=True)
        st.caption(f"Producto: {row_sel['producto']} | Cantidad: {row_sel['cantidad']:,.0f} L | Fecha: {row_sel['fecha']} | Lote: {row_sel['lote']}")

        idx_actual = ESTADOS_VALIDOS.index(row_sel["estado"]) if row_sel["estado"] in ESTADOS_VALIDOS else 0
        nuevo_estado = st.selectbox(
            "Nuevo estado",
            ESTADOS_VALIDOS,
            index=idx_actual,
            key="nuevo_individual",
            format_func=lambda x: f"{ESTADOS_CONFIG[x][0]} {x.capitalize()}",
        )

        if st.button("💾 Guardar cambio", key="btn_individual", type="primary"):
            if nuevo_estado == row_sel["estado"]:
                st.warning("El estado no cambió.")
            else:
                actualizar_estado(pedido_id_sel, nuevo_estado)
                st.success(f"Pedido actualizado a **{nuevo_estado.upper()}**")
                st.session_state.refresh += 1
                st.cache_data.clear()
                st.rerun()

    with col_bulk:
        st.markdown("##### 🔀 Varios pedidos")
        labels_bulk = st.multiselect("Seleccioná pedidos", options=opciones_labels, key="sel_bulk")
        estado_bulk = st.selectbox(
            "Nuevo estado para todos",
            ESTADOS_VALIDOS,
            key="nuevo_bulk",
            format_func=lambda x: f"{ESTADOS_CONFIG[x][0]} {x.capitalize()}",
        )

        if st.button("💾 Aplicar a seleccionados", key="btn_bulk", type="primary"):
            if not labels_bulk:
                st.warning("Seleccioná al menos un pedido.")
            else:
                ids_bulk = [id_por_label[lbl] for lbl in labels_bulk]
                actualizar_estados_bulk(ids_bulk, estado_bulk)
                st.success(f"{len(ids_bulk)} pedido(s) actualizados a **{estado_bulk.upper()}**")
                st.session_state.refresh += 1
                st.cache_data.clear()
                st.rerun()

# ── Tab 3: Materias Primas por Búsqueda de N° de Pedido (Agrupado por prefijo) ──
with tab_mp_pedido:
    st.markdown("#### 🔍 Materias Primas por Número o Prefijo de Pedido")
    st.caption("Ingresá el número de pedido (ej: **1268**) para agrupar automáticamente **todos** los subpedidos o líneas que comiencen o coincidan con ese número (ej. 1268-1, 1268-2) y calcular los insumos totales.")

    busqueda_nro = st.text_input("Ingresá el N° de pedido a consultar:", placeholder="ej: 1268", key="input_busqueda_nro_mp")

    if not busqueda_nro.strip():
        st.info("Ingresá un número de pedido arriba para ver el desglose y las materias primas.")
    else:
        # Filtrar todos los registros del cliente cuyo número de pedido contenga o comience con el texto ingresado
        df_pedido_grupo = df[df["numero_pedido"].astype(str).str.contains(busqueda_nro.strip(), case=False)].copy()

        if df_pedido_grupo.empty:
            st.warning(f"No se encontraron pedidos que coincidan con **'{busqueda_nro}'** para este cliente.")
        else:
            st.success(f"Se encontraron **{len(df_pedido_grupo)}** registro(s) asociados al pedido/prefijo **'{busqueda_nro}'**.")

            # Mostrar detalle de los subpedidos incluidos en este grupo
            with st.expander("📄 Ver detalle de todos los ítems incluidos", expanded=True):
                st.dataframe(
                    df_pedido_grupo[["id", "numero_pedido", "producto", "cantidad", "estado", "lote"]]
                    .rename(columns={
                        "id": "ID Interno",
                        "numero_pedido": "N° Pedido",
                        "producto": "Producto",
                        "cantidad": "Litros",
                        "estado": "Estado",
                        "lote": "Lote",
                    })
                    .style.format({"Litros": "{:,.1f}"}),
                    use_container_width=True,
                    hide_index=True,
                )

            @st.cache_data(show_spinner=False)
            def cargar_ingredientes_receta_simple(receta_id: int):
                query = """
                    SELECT
                        mp.id           AS mp_id,
                        mp.nombre       AS materia_prima,
                        ri.cantidad     AS cantidad_base,
                        ri.unidad       AS unidad
                    FROM receta_ingredientes ri
                    JOIN materias_primas mp ON mp.id = ri.materia_prima_id
                    WHERE ri.receta_id = ?
                """
                with get_conn() as conn:
                    return pd.read_sql(query, conn, params=(receta_id,))

            @st.cache_data(show_spinner=False)
            def cargar_stock_mp_dict():
                with get_conn() as conn:
                    df_s = pd.read_sql("SELECT materia_prima_id, cantidad_actual FROM stock_materias_primas", conn)
                return df_s.set_index("materia_prima_id")["cantidad_actual"].to_dict()

            # Consolidar materias primas sumando las cantidades de todas las recetas de este grupo
            BASE_CALC = 200.0  # Factor estándar base de formulación
            acumulado_mp = defaultdict(lambda: {"nombre": "", "unidad": "", "total": 0.0})

            for _, row in df_pedido_grupo.iterrows():
                receta_id = row["receta_id"]
                cantidad_l = row["cantidad"]

                if pd.isna(receta_id) or not receta_id or pd.isna(cantidad_l):
                    continue

                factor = cantidad_l / BASE_CALC
                df_ing = cargar_ingredientes_receta_simple(int(receta_id))

                for _, ing_row in df_ing.iterrows():
                    acumulado_mp[ing_row["mp_id"]]["nombre"] = ing_row["materia_prima"]
                    acumulado_mp[ing_row["mp_id"]]["unidad"] = ing_row["unidad"]
                    acumulado_mp[ing_row["mp_id"]]["total"] += ing_row["cantidad_base"] * factor

            stock_dict = cargar_stock_mp_dict()
            filas_mp_grupo = []

            for mp_id, d in acumulado_mp.items():
                necesario = round(d["total"], 3)
                disponible = round(stock_dict.get(mp_id, 0.0), 3)
                diferencia = round(disponible - necesario, 3)
                filas_mp_grupo.append({
                    "Materia Prima": d["nombre"],
                    "Unidad":        d["unidad"],
                    "Necesario":     necesario,
                    "Stock Actual":  disponible,
                    "Diferencia":    diferencia,
                    "_falta":        diferencia < 0,
                })

            if not filas_mp_grupo:
                st.warning("No se pudieron calcular materias primas (las recetas de estos pedidos no tienen ingredientes cargados).")
            else:
                df_mp_pedido_res = pd.DataFrame(filas_mp_grupo).sort_values("Materia Prima").reset_index(drop=True)
                
                faltantes_ped = df_mp_pedido_res["_falta"].sum()
                col_mp1, col_mp2 = st.columns(2)
                col_mp1.metric("Insumos totales necesarios", len(df_mp_pedido_res))
                col_mp2.metric("⚠️ Con stock insuficiente", int(faltantes_ped))

                def color_mp_ped(row):
                    d = row["Diferencia"]
                    if d < 0:
                        return ["background-color:#fef2f2;color:#991b1b"] * len(row)
                    elif d == 0:
                        return ["background-color:#fffbeb;color:#92400e"] * len(row)
                    else:
                        return ["background-color:#f0fdf4;color:#166534"] * len(row)

                df_mp_pedido_display = df_mp_pedido_res.drop(columns=["_falta"])
                styled_mp_ped = (
                    df_mp_pedido_display.style
                    .apply(color_mp_ped, axis=1)
                    .format({
                        "Necesario":    "{:,.3f}",
                        "Stock Actual": "{:,.3f}",
                        "Diferencia":   "{:+,.3f}",
                    })
                )

                st.dataframe(styled_mp_ped, use_container_width=True, hide_index=True)
                st.caption("🟥 Falta stock   |   🟨 Stock justo   |   🟩 Stock suficiente")

# ── Tab 4: Materias primas pendientes ─────────────────────────────────────────
with tab_mp:
    @st.cache_data(show_spinner=False)
    def cargar_pendientes_global(_refresh):
        query = """
            SELECT
                p.id,
                p.numero_pedido,
                p.receta_id,
                r.nombre        AS receta,
                p.cantidad,
                p.estado,
                c.nombre        AS cliente
            FROM pedidos_produccion p
            LEFT JOIN recetas r ON r.id = p.receta_id
            LEFT JOIN clientes c ON c.id = p.cliente_id
            WHERE LOWER(TRIM(p.estado)) IN ('pendiente', 'en proceso')
            ORDER BY c.nombre, p.numero_pedido
        """
        with get_conn() as conn:
            return pd.read_sql(query, conn)

    @st.cache_data(show_spinner=False)
    def cargar_ingredientes_receta_mp(receta_id: int):
        query = """
            SELECT
                mp.id           AS mp_id,
                mp.nombre       AS materia_prima,
                ri.cantidad     AS cantidad_base,
                ri.unidad       AS unidad
            FROM receta_ingredientes ri
            JOIN materias_primas mp ON mp.id = ri.materia_prima_id
            WHERE ri.receta_id = ?
        """
        with get_conn() as conn:
            return pd.read_sql(query, conn, params=(receta_id,))

    @st.cache_data(show_spinner=False)
    def cargar_stock_mp():
        with get_conn() as conn:
            df_s = pd.read_sql("SELECT materia_prima_id, cantidad_actual FROM stock_materias_primas", conn)
        return df_s.set_index("materia_prima_id")["cantidad_actual"].to_dict()

    def consolidar_mp(df_pedidos: pd.DataFrame):
        BASE = 200.0
        acum = defaultdict(lambda: {"nombre": "", "unidad": "", "total": 0.0})
        for _, row in df_pedidos.iterrows():
            if pd.isna(row["receta_id"]) or not row["receta_id"]:
                continue
            factor = row["cantidad"] / BASE
            ing = cargar_ingredientes_receta_mp(int(row["receta_id"])).copy()
            for _, i in ing.iterrows():
                acum[i["mp_id"]]["nombre"] = i["materia_prima"]
                acum[i["mp_id"]]["unidad"] = i["unidad"]
                acum[i["mp_id"]]["total"] += i["cantidad_base"] * factor

        stock = cargar_stock_mp()
        filas = []
        for mp_id, d in acum.items():
            necesario = round(d["total"], 3)
            disponible = round(stock.get(mp_id, 0.0), 3)
            diferencia = round(disponible - necesario, 3)
            filas.append({
                "Materia Prima":  d["nombre"],
                "Unidad":         d["unidad"],
                "Necesario":      necesario,
                "Stock Actual":   disponible,
                "Diferencia":     diferencia,
                "_falta":         diferencia < 0,
            })
        return pd.DataFrame(filas).sort_values("Materia Prima").reset_index(drop=True)

    df_pend = cargar_pendientes_global(st.session_state.refresh)

    if df_pend.empty:
        st.success("✅ No hay pedidos pendientes ni en proceso. ¡Todo producido!")
        st.stop()

    st.markdown("#### 🔍 ¿Para qué pedidos querés ver las materias primas?")
    scope = st.radio("Alcance", ["Todos los clientes", f"Solo {cliente_sel}"], horizontal=True, key="mp_scope")

    if scope == f"Solo {cliente_sel}":
        df_pend_filtrado = df_pend[df_pend["cliente"] == cliente_sel].copy()
    else:
        df_pend_filtrado = df_pend.copy()

    estado_mp = st.radio("Estado de pedidos a incluir", ["Pendiente + En proceso", "Solo pendiente", "Solo en proceso"], horizontal=True, key="mp_estado")
    if estado_mp == "Solo pendiente":
        df_pend_filtrado = df_pend_filtrado[df_pend_filtrado["estado"].str.lower() == "pendiente"]
    elif estado_mp == "Solo en proceso":
        df_pend_filtrado = df_pend_filtrado[df_pend_filtrado["estado"].str.lower() == "en proceso"]

    if df_pend_filtrado.empty:
        st.info("No hay pedidos con ese criterio.")
        st.stop()

    st.divider()
    total_litros_pend = df_pend_filtrado["cantidad"].sum()
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Pedidos incluidos", len(df_pend_filtrado))
    col_b.metric("Litros a producir", f"{total_litros_pend:,.0f}")
    col_c.metric("Clientes involucrados", df_pend_filtrado["cliente"].nunique())

    with st.expander("📄 Ver detalle de pedidos incluidos", expanded=False):
        df_detalle = df_pend_filtrado[["id", "numero_pedido", "cliente", "receta", "cantidad", "estado"]].copy()
        df_detalle["N° Pedido"] = df_detalle["numero_pedido"].astype(str) + "  (id " + df_detalle["id"].astype(str) + ")"
        st.dataframe(
            df_detalle[["N° Pedido", "cliente", "receta", "cantidad", "estado"]]
            .rename(columns={"cliente": "Cliente", "receta": "Producto", "cantidad": "Litros", "estado": "Estado"})
            .style.format({"Litros": "{:,.1f}"}),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.markdown("#### 🧮 Materias primas consolidadas")

    df_mp = consolidar_mp(df_pend_filtrado)

    if df_mp.empty:
        st.warning("No se pudieron calcular materias primas (recetas sin ingredientes).")
        st.stop()

    faltantes = df_mp["_falta"].sum()
    col_x, col_y = st.columns(2)
    col_x.metric("Ingredientes distintos", len(df_mp))
    col_y.metric("⚠️ Con stock insuficiente", int(faltantes))

    ver = st.radio("Mostrar", ["Todos", "Solo faltantes", "Solo con stock suficiente"], horizontal=True, key="mp_ver")
    df_mp_view = df_mp.drop(columns=["_falta"])
    if ver == "Solo faltantes":
        df_mp_view = df_mp_view[df_mp["_falta"]]
    elif ver == "Solo con stock suficiente":
        df_mp_view = df_mp_view[~df_mp["_falta"]]

    def color_mp(row):
        d = row["Diferencia"]
        if d < 0:
            return ["background-color:#fef2f2;color:#991b1b"] * len(row)
        elif d == 0:
            return ["background-color:#fffbeb;color:#92400e"] * len(row)
        else:
            return ["background-color:#f0fdf4;color:#166534"] * len(row)

    styled_mp = df_mp_view.style.apply(color_mp, axis=1).format({
        "Necesario": "{:,.3f}",
        "Stock Actual": "{:,.3f}",
        "Diferencia": "{:+,.3f}",
    })

    st.dataframe(styled_mp, use_container_width=True, hide_index=True, height=500)
    st.caption("🟥 Falta stock   |   🟨 Stock justo   |   🟩 Stock suficiente")

    export_data = (
        df_mp_view[df_mp["_falta"]].to_csv(index=False).encode("utf-8")
        if faltantes > 0
        else df_mp_view.to_csv(index=False).encode("utf-8")
    )
    st.download_button(
        "⬇️ Exportar faltantes CSV",
        data=export_data,
        file_name="faltantes_produccion.csv",
        mime="text/csv",
    )

# ── Remito PDF ─────────────────────────────────────────────────────────────────
def generar_remito_pdf(
    cliente_nombre: str,
    numero_pedido: str,
    numero_envio: int,
    fecha: str,
    filas: list[dict],
    observaciones: str = "",
) -> bytes:
    buffer = io.BytesIO()
    PAGE_W, PAGE_H = A4
    MARGIN = 1.8 * cm

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN)

    VERDE_OSCURO  = colors.HexColor("#1B4332")
    VERDE_MEDIO   = colors.HexColor("#2D6A4F")
    VERDE_CLARO   = colors.HexColor("#D8F3DC")
    GRIS_CLARO    = colors.HexColor("#F8F9FA")
    GRIS_BORDE    = colors.HexColor("#DEE2E6")
    BLANCO        = colors.white

    base = getSampleStyleSheet()

    s_fábrica = ParagraphStyle("fabrica", fontName="Helvetica-Bold", fontSize=13, textColor=BLANCO, alignment=TA_CENTER, leading=16)
    s_titulo_doc = ParagraphStyle("titulo_doc", fontName="Helvetica-Bold", fontSize=15, textColor=BLANCO, alignment=TA_CENTER, leading=18)
    s_label = ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=8, textColor=VERDE_MEDIO, alignment=TA_LEFT, leading=10)
    s_valor = ParagraphStyle("valor", fontName="Helvetica-Bold", fontSize=11, textColor=VERDE_OSCURO, alignment=TA_LEFT, leading=14)
    s_col_header = ParagraphStyle("col_header", fontName="Helvetica-Bold", fontSize=9, textColor=BLANCO, alignment=TA_CENTER, leading=11)
    s_celda = ParagraphStyle("celda", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#212529"), alignment=TA_LEFT, leading=11)
    s_celda_c = ParagraphStyle("celda_c", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#212529"), alignment=TA_CENTER, leading=11)
    s_firma_label = ParagraphStyle("firma_label", fontName="Helvetica-Bold", fontSize=8, textColor=VERDE_OSCURO, alignment=TA_CENTER, leading=10)
    s_total_label = ParagraphStyle("total_label", fontName="Helvetica-Bold", fontSize=10, textColor=VERDE_OSCURO, alignment=TA_RIGHT, leading=12)
    s_total_valor = ParagraphStyle("total_valor", fontName="Helvetica-Bold", fontSize=12, textColor=BLANCO, alignment=TA_CENTER, leading=14)
    s_obs_contenido = ParagraphStyle("obs_contenido", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#212529"), alignment=TA_LEFT, leading=12)

    story = []
    col_w = PAGE_W - 2 * MARGIN

    header_data = [[
        Paragraph("FÁBRICA DE PRODUCTOS CAPILARES<br/><font size='7'>Elaboración de productos de higiene y cosmética</font>", s_fábrica),
        Paragraph("REMITO INTERNO<br/>DE DESPACHO", s_titulo_doc),
    ]]
    header_tbl = Table(header_data, colWidths=[col_w * 0.62, col_w * 0.38])
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), VERDE_MEDIO),
        ("BACKGROUND", (1, 0), (1, 0), VERDE_OSCURO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 0.35 * cm))

    info_data = [[
        Paragraph("NUMERO DE PEDIDO", s_label),
        Paragraph("NUMERO DE ENVÍO", s_label),
        Paragraph("FECHA", s_label),
    ], [
        Paragraph(numero_pedido, s_valor),
        Paragraph(str(numero_envio), s_valor),
        Paragraph(fecha, s_valor),
    ]]
    info_tbl = Table(info_data, colWidths=[col_w * 0.38, col_w * 0.28, col_w * 0.34])
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_CLARO),
        ("BOX", (0, 0), (-1, -1), 1, GRIS_BORDE),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, GRIS_BORDE),
        ("LINEAFTER", (1, 0), (1, -1), 0.5, GRIS_BORDE),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 0.25 * cm))

    dest_data = [[
        Paragraph("CLIENTE / DESTINATARIO", s_label),
    ], [
        Paragraph(cliente_nombre.upper(), ParagraphStyle("dest", fontName="Helvetica-Bold", fontSize=13, textColor=VERDE_OSCURO, alignment=TA_LEFT, leading=16)),
    ]]
    dest_tbl = Table(dest_data, colWidths=[col_w])
    dest_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), VERDE_CLARO),
        ("BOX", (0, 0), (-1, -1), 1.5, VERDE_MEDIO),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(dest_tbl)
    story.append(Spacer(1, 0.3 * cm))

    encabezado = [
        Paragraph("CLIENTE", s_col_header),
        Paragraph("PRODUCTO", s_col_header),
        Paragraph("ENVASE", s_col_header),
        Paragraph("CANTIDAD", s_col_header),
    ]

    tabla_data = [encabezado]
    for f in filas:
        tabla_data.append([
            Paragraph(str(f.get("cliente", cliente_nombre)), s_celda),
            Paragraph(str(f.get("receta_nombre", "")), s_celda),
            Paragraph(str(f.get("envase", "")), s_celda),
            Paragraph(str(f.get("cantidad", "")), s_celda_c),
        ])

    col_widths = [col_w * 0.14, col_w * 0.38, col_w * 0.34, col_w * 0.14]
    prod_tbl = Table(tabla_data, colWidths=col_widths, repeatRows=1)

    ts = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VERDE_OSCURO),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRIS_BORDE),
        ("BOX", (0, 0), (-1, -1), 1, VERDE_MEDIO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ])
    for i in range(1, len(tabla_data)):
        bg = BLANCO if i % 2 == 1 else GRIS_CLARO
        ts.add("BACKGROUND", (0, i), (-1, i), bg)

    prod_tbl.setStyle(ts)
    story.append(prod_tbl)
    story.append(Spacer(1, 0.25 * cm))

    total_items = sum(float(f.get("cantidad", 0)) for f in filas)
    total_data = [[
        Paragraph("TOTAL", s_total_label),
        Paragraph(str(total_items), s_total_valor),
    ]]
    total_tbl = Table(total_data, colWidths=[col_w - 2 * cm, 2 * cm])
    total_tbl.setStyle(TableStyle([
        ("BACKGROUND", (1, 0), (1, 0), VERDE_OSCURO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 6),
        ("BOX", (1, 0), (1, 0), 1, VERDE_MEDIO),
    ]))
    story.append(total_tbl)
    story.append(Spacer(1, 0.35 * cm))

    if observaciones.strip():
        obs_html = observaciones.replace("\n", "<br/>")
        obs_data = [[Paragraph("OBSERVACIONES", s_label)], [Paragraph(obs_html, s_obs_contenido)]]
        obs_tbl = Table(obs_data, colWidths=[col_w])
        obs_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), GRIS_CLARO),
            ("BOX", (0, 0), (-1, -1), 1, GRIS_BORDE),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(obs_tbl)
        story.append(Spacer(1, 0.45 * cm))
    else:
        story.append(Spacer(1, 0.45 * cm))

    line = "_" * 32
    firmas_data = [[
        Paragraph(f"{line}<br/>RESPONSABLE DE DESPACHO", s_firma_label),
        Paragraph(f"{line}<br/>TRANSPORTISTA", s_firma_label),
        Paragraph(f"{line}<br/>RECIBIDO CONFORME", s_firma_label),
    ]]
    firmas_tbl = Table(firmas_data, colWidths=[col_w / 3] * 3)
    firmas_tbl.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ]))
    story.append(firmas_tbl)

    doc.build(story)
    buffer.seek(0)
    return buffer.read()

# ── Tab 5: Remito ───────────────────────────────────────────────────────────────
with tab_remito:
    st.markdown("#### 🖨️ Generar Remito Interno de Despacho")
    st.caption("Seleccioná los productos producidos que querés incluir en el remito.")

    df_producidos = df[df["estado"].str.lower() == "producido"].copy()

    if df_producidos.empty:
        st.info(f"No hay pedidos en estado **producido** para **{cliente_sel}**.")
        st.stop()

    @st.cache_data(show_spinner=False)
    def cargar_envases_todos_producidos(cliente_id: int, _refresh):
        query = """
            SELECT
                p.numero_pedido,
                p.id            AS pedido_id,
                c.nombre        AS cliente,
                r.nombre        AS receta_nombre,
                COALESCE(e.descripcion, '—') AS envase,
                SUM(COALESCE(oe.cantidad_unidades, 0)) AS cantidad_envasada,
                p.cantidad      AS cantidad_pedido
            FROM pedidos_produccion p
            LEFT JOIN recetas r           ON r.id = p.receta_id
            LEFT JOIN clientes c          ON c.id = p.cliente_id
            LEFT JOIN producciones pr     ON pr.pedido_id = p.id
            LEFT JOIN ordenes_envasado oe ON oe.produccion_id = pr.id
            LEFT JOIN envases e           ON e.id = oe.envase_id
            WHERE p.cliente_id = ?
              AND LOWER(TRIM(p.estado)) = 'producido'
            GROUP BY
                p.numero_pedido,
                p.id,
                c.nombre,
                r.nombre,
                e.descripcion
            ORDER BY CAST(p.numero_pedido AS INTEGER) DESC, r.nombre
        """
        with get_conn() as conn:
            return pd.read_sql(query, conn, params=(cliente_id,))

    df_todos_envases = cargar_envases_todos_producidos(cliente_id, st.session_state.refresh)

    if df_todos_envases.empty:
        df_todos_envases = df_producidos.rename(columns={"producto": "receta_nombre"}).copy()
        df_todos_envases["cliente"]          = cliente_sel
        df_todos_envases["envase"]           = "—"
        df_todos_envases["cantidad_envasada"] = df_todos_envases["cantidad"]
        df_todos_envases["cantidad_pedido"]   = df_todos_envases["cantidad"]
        df_todos_envases["pedido_id"]         = df_todos_envases["id"]

    def _label_fila(row) -> str:
        cant = row["cantidad_envasada"] if row["cantidad_envasada"] > 0 else row["cantidad_pedido"]
        return f"N°{row['numero_pedido']} | {row['receta_nombre']} | {row['envase']} | {cant:,.0f} uds"

    df_todos_envases["_label"] = df_todos_envases.apply(_label_fila, axis=1)

    st.markdown("##### 1. Filtrá por número de pedido (opcional)")
    numeros_disp = ["Todos"] + sorted(
        df_todos_envases["numero_pedido"].unique().tolist(),
        key=lambda x: (0, int(x)) if str(x).isdigit() else (1, str(x)),
        reverse=True,
    )
    col_filt1, col_filt2, col_filt3 = st.columns([2, 1, 1])
    with col_filt1:
        nro_filtro_rem = st.selectbox("Ver productos de pedido N°", numeros_disp, key="remito_filtro_nro")
    with col_filt2:
        nro_envio = st.number_input("N° de envío", min_value=1, value=1, step=1, key="remito_nro_envio")
    with col_filt3:
        fecha_remito = st.date_input("Fecha del remito", value=datetime.date.today(), key="remito_fecha")
        fecha_remito_str = fecha_remito.strftime("%d/%m/%Y")

    if nro_filtro_rem != "Todos":
        df_filtrado_rem = df_todos_envases[df_todos_envases["numero_pedido"] == nro_filtro_rem].copy()
    else:
        df_filtrado_rem = df_todos_envases.copy()

    st.markdown("##### 2. Elegí los productos que irán en el remito")
    todas_labels = df_filtrado_rem["_label"].tolist()

    col_sel_a, col_sel_b, _ = st.columns([1, 1, 3])
    with col_sel_a:
        if st.button("✅ Seleccionar todos", key="rem_sel_all"):
            st.session_state["rem_productos_sel"] = todas_labels
    with col_sel_b:
        if st.button("❌ Limpiar selección", key="rem_sel_none"):
            st.session_state["rem_productos_sel"] = []

    if "rem_productos_sel" not in st.session_state:
        st.session_state["rem_productos_sel"] = todas_labels

    labels_validas = [l for l in st.session_state["rem_productos_sel"] if l in todas_labels]

    productos_sel = st.multiselect(
        "Productos a incluir en el remito",
        options=todas_labels,
        default=labels_validas,
        key="rem_multiselect",
    )
    st.session_state["rem_productos_sel"] = productos_sel

    if not productos_sel:
        st.warning("Seleccioná al menos un producto para generar el remito.")
        st.stop()

    df_seleccion = df_filtrado_rem[df_filtrado_rem["_label"].isin(productos_sel)].copy()

    st.markdown("##### 3. Ingresá la cantidad de tambores por producto")
    df_editor = pd.DataFrame({
        "N° Pedido": df_seleccion["numero_pedido"].tolist(),
        "Producto":  df_seleccion["receta_nombre"].tolist(),
        "Envase":    df_seleccion["envase"].tolist(),
        "Tambores":  [0] * len(df_seleccion),
    })

    df_editado = st.data_editor(
        df_editor,
        use_container_width=True,
        hide_index=True,
        disabled=["N° Pedido", "Producto", "Envase"],
        column_config={
            "Tambores": st.column_config.NumberColumn("Tambores", min_value=0, step=1),
        },
        key="rem_data_editor",
    )

    total_sel = int(df_editado["Tambores"].sum())
    st.caption(f"**{len(df_editado)} línea(s)** | Total tambores: **{total_sel:,}**")

    numeros_en_sel = df_seleccion["numero_pedido"].unique().tolist()
    if len(numeros_en_sel) == 1:
        nro_ped_pdf = numeros_en_sel[0]
        nro_predeterminado = f"000-{int(nro_ped_pdf):05d}" if str(nro_ped_pdf).isdigit() else str(nro_ped_pdf)
    else:
        nro_predeterminado = " / ".join(
            f"000-{int(n):05d}" if str(n).isdigit() else str(n)
            for n in sorted(numeros_en_sel, key=lambda x: (0, int(x)) if str(x).isdigit() else (1, str(x)))
        )

    st.markdown("##### 4. Configuración final y generación del PDF")
    col_pdf_opt1, col_pdf_opt2 = st.columns([2, 2])
    with col_pdf_opt1:
        nro_pedido_manual = st.text_input("Número de Pedido en PDF (Editable)", value=nro_predeterminado, key="remito_nro_pedido_manual")
    with col_pdf_opt2:
        observaciones_remito = st.text_area("Observaciones del Remito (Opcional)", value="", height=100, key="remito_observaciones")

    if st.button("📄 Generar PDF del Remito", type="primary"):
        filas_remito = [
            {
                "cliente":       cliente_sel,
                "receta_nombre": row["Producto"],
                "envase":        row["Envase"],
                "cantidad":      int(row["Tambores"]),
            }
            for _, row in df_editado.iterrows()
        ]
        pdf_bytes = generar_remito_pdf(
            cliente_nombre=cliente_sel,
            numero_pedido=nro_pedido_manual,
            numero_envio=int(nro_envio),
            fecha=fecha_remito_str,
            filas=filas_remito,
            observaciones=observaciones_remito,
        )
        
        nro_archivo = "".join(x for x in nro_pedido_manual if x.isalnum() or x in "-_").strip()[:30]
        nombre_archivo = f"remito_{cliente_sel}_{nro_archivo}_envio{nro_envio}.pdf"
        
        st.download_button(
            label="⬇️ Descargar Remito PDF",
            data=pdf_bytes,
            file_name=nombre_archivo,
            mime="application/pdf",
        )
        st.success("✅ PDF generado con éxito.")