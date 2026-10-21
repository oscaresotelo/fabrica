import streamlit as st
import pandas as pd
import sqlite3

DB_PATH = "minerva.db"

def get_lotes_sin_envasar():
    conn = sqlite3.connect(DB_PATH)
    query = """
    SELECT
        pr.id as produccion_id,
        pr.lote as nro_lote,
        pr.fecha,
        cl.nombre as cliente,
        re.nombre as receta,
        pr.cantidad_litros,
        IFNULL(pr.litros_envasados,0) as litros_envasados,
        (pr.cantidad_litros - IFNULL(pr.litros_envasados, 0)) AS litros_sin_envasar
    FROM producciones pr
    LEFT JOIN pedidos_produccion pp ON pr.pedido_id = pp.id
    LEFT JOIN clientes cl ON pp.cliente_id = cl.id
    LEFT JOIN recetas re ON pp.receta_id = re.id
    WHERE (pr.cantidad_litros - IFNULL(pr.litros_envasados,0)) > 0.009
    ORDER BY pr.fecha DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    # Elimina lotes con menos de 0.01 para máxima seguridad
    df = df[df['litros_sin_envasar'] >= 0.01]
    return df

def envasar_remanente_lote(lote_id, cantidad_a_envasar):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE producciones SET litros_envasados = IFNULL(litros_envasados,0) + ? WHERE id = ?",
        (cantidad_a_envasar, lote_id)
    )
    conn.commit()
    conn.close()

def modulo_saldos_sin_envasar():
    st.title("Saldos sin envasar por lote")

    df_lotes = get_lotes_sin_envasar()
    if df_lotes.empty:
        st.info("No hay lotes con saldo sin envasar mayor a 0.01 litros.")
        return

    with st.expander("🔎 Ver lotes y saldos sin envasar", expanded=True):
        st.dataframe(
            df_lotes,
            use_container_width=True,
            hide_index=True,
            height=350
        )
        st.caption("Puedes ordenar y buscar por cualquier columna.")

    st.markdown("### Envasar remanente de lote")
    selec_idx = st.selectbox(
        "Selecciona un lote para envasar su saldo:",
        df_lotes.index,
        format_func=lambda i: (
            f"Lote: {df_lotes.loc[i,'nro_lote']} | Fecha: {df_lotes.loc[i,'fecha']} | "
            f"Cliente: {df_lotes.loc[i,'cliente']} | Receta: {df_lotes.loc[i,'receta']} | "
            f"Litros sin envasar: {df_lotes.loc[i,'litros_sin_envasar']:.2f}"
        )
    )
    lote_row = df_lotes.loc[selec_idx]
    cantidad_max = float(lote_row["litros_sin_envasar"])

    # Si el saldo es menor al mínimo, muestra aviso y bloquea input
    if cantidad_max < 0.01:
        st.warning("Este lote tiene un saldo demasiado pequeño para ser envasado.")
        return

    col1, col2 = st.columns(2)
    with col1:
        cantidad_a_envasar = st.number_input(
            "Cantidad de litros a envasar (máximo posible):",
            min_value=0.01,
            max_value=cantidad_max,
            value=round(cantidad_max, 2),
            step=0.01
        )
    with col2:
        st.markdown(f"**Cliente:** {lote_row['cliente']}")
        st.markdown(f"**Receta:** {lote_row['receta']}")
        st.markdown(f"**Lote producción:** {lote_row['nro_lote']}")
        st.markdown(f"**Fecha producción:** {lote_row['fecha']}")

    if st.button("Envasar saldo seleccionado"):
        envasar_remanente_lote(lote_row["produccion_id"], cantidad_a_envasar)
        st.success(
            f"Lote {lote_row['nro_lote']}: {cantidad_a_envasar:.2f} litros marcados como envasados. "
            "Ahora puedes generar una nueva orden de envasado desde el módulo habitual."
        )
        st.experimental_rerun()
    st.info(
        "⚠️ Esta acción solo descuenta litros del saldo sin envasar. Si deseas registrar unidades, "
        "realiza también la orden de envasado correspondiente para trazabilidad."
    )
