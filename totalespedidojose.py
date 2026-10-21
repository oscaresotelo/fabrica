import streamlit as st
import sqlite3
import pandas as pd

DB_PATH = "minerva.db"

st.set_page_config(page_title="Costos de Recetas", layout="wide")

st.title("Costos de Recetas")

conn = sqlite3.connect(DB_PATH)

query = """
WITH ultimo_precio AS (
    SELECT
        cmp.materia_prima_id,
        cmp.precio_unitario,
        cmp.fecha,
        ROW_NUMBER() OVER (
            PARTITION BY cmp.materia_prima_id
            ORDER BY date(cmp.fecha) DESC, cmp.id DESC
        ) AS rn
    FROM compras_materia_prima cmp
),

costos AS (
    SELECT
        r.id AS receta_id,
        r.nombre AS receta,
        c.nombre AS cliente,
        mp.nombre AS materia_prima,
        ri.cantidad,
        ri.unidad,
        COALESCE(up.precio_unitario, 0) AS precio_unitario,
        ROUND(
            ri.cantidad * COALESCE(up.precio_unitario, 0),
            2
        ) AS costo_ingrediente

    FROM receta_ingredientes ri

    INNER JOIN recetas r
        ON r.id = ri.receta_id

    LEFT JOIN clientes c
        ON c.id = r.cliente_id

    INNER JOIN materias_primas mp
        ON mp.id = ri.materia_prima_id

    LEFT JOIN ultimo_precio up
        ON up.materia_prima_id = ri.materia_prima_id
        AND up.rn = 1
)

SELECT *
FROM costos
ORDER BY cliente, receta, materia_prima
"""

df = pd.read_sql_query(query, conn)

# RESUMEN DE COSTOS
resumen = (
    df.groupby(
        ["receta_id", "receta", "cliente"],
        as_index=False
    )["costo_ingrediente"]
    .sum()
    .rename(
        columns={
            "costo_ingrediente": "costo_total_receta"
        }
    )
)

# LITROS TOTALES
volumen_query = """
SELECT
    r.id AS receta_id,
    SUM(ri.cantidad) AS litros_totales

FROM receta_ingredientes ri

INNER JOIN recetas r
    ON r.id = ri.receta_id

WHERE LOWER(ri.unidad) IN (
    'litro',
    'litros',
    'l'
)

GROUP BY r.id
"""

df_volumen = pd.read_sql_query(volumen_query, conn)

# UNIR RESUMEN + LITROS
resumen = resumen.merge(
    df_volumen,
    on="receta_id",
    how="left"
)

resumen["litros_totales"] = (
    resumen["litros_totales"]
    .fillna(0)
)

# COSTO POR LITRO
resumen["costo_por_litro"] = resumen.apply(
    lambda x: round(
        x["costo_total_receta"] /
        x["litros_totales"],
        2
    ) if x["litros_totales"] > 0 else 0,
    axis=1
)

# MOSTRAR RESUMEN
st.subheader("Resumen de Costos")

st.dataframe(
    resumen,
    use_container_width=True
)

# DESCARGA CSV RESUMEN
csv_resumen = resumen.to_csv(
    index=False
).encode("utf-8")

st.download_button(
    label="Descargar resumen CSV",
    data=csv_resumen,
    file_name="costos_recetas.csv",
    mime="text/csv"
)

# DETALLE
st.subheader("Detalle por Ingrediente")

st.dataframe(
    df,
    use_container_width=True
)

# DESCARGA CSV DETALLE
csv_detalle = df.to_csv(
    index=False
).encode("utf-8")

st.download_button(
    label="Descargar detalle CSV",
    data=csv_detalle,
    file_name="detalle_costos_recetas.csv",
    mime="text/csv"
)

conn.close()