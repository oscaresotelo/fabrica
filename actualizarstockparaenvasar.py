import streamlit as st
import sqlite3
import pandas as pd
import time

# --- Ruta de la base de datos ---
DB_PATH = "minerva.db"


# --- Función de conexión ---
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


# --- Leer DataFrame desde SQL ---
def fetch_df(query, params=()):
    conn = get_connection()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


# --- Obtener datos de producción ---
def get_production_data():
    query = """
        SELECT
            p.id AS produccion_id,
            p.lote,
            p.cantidad_real_litros,
            p.litros_envasados,
            (p.cantidad_real_litros - p.litros_envasados) AS disponible,
            r.nombre AS receta_nombre,
            prod.nombre AS producto_nombre
        FROM producciones p
        JOIN pedidos_produccion pp ON p.pedido_id = pp.id
        JOIN recetas r ON pp.receta_id = r.id
        JOIN productos prod ON r.id = prod.id_receta
        WHERE p.cantidad_real_litros > 0
        ORDER BY p.id;
    """
    df = fetch_df(query)
    return df.to_dict(orient="records")


# --- Actualizar litros envasados ---
def actualizar_litros_envasados(produccion_id, nuevo_envasado):
    conn = get_connection()

    try:
        cur = conn.cursor()
        cur.execute("BEGIN;")

        # Obtener valores actuales
        cur.execute("""
            SELECT cantidad_real_litros, litros_envasados
            FROM producciones
            WHERE id = ?
        """, (produccion_id,))
        row = cur.fetchone()

        if not row:
            st.error("❌ No se encontró la producción seleccionada.")
            return False

        total = float(row["cantidad_real_litros"])
        envasado_actual = float(row["litros_envasados"])

        # Validaciones
        if nuevo_envasado < 0:
            conn.rollback()
            raise ValueError("Los litros envasados no pueden ser negativos.")

        if nuevo_envasado > total:
            conn.rollback()
            raise ValueError("No podés envasar más litros de los producidos.")

        # Actualizar litros envasados
        cur.execute("""
            UPDATE producciones
            SET litros_envasados = ?
            WHERE id = ?
        """, (nuevo_envasado, produccion_id))

        conn.commit()

        disponible = total - nuevo_envasado

        st.success(
            f"✅ Actualizado correctamente.\n"
            f"- Total producido: {total:.2f} L\n"
            f"- Ahora envasado: {nuevo_envasado:.2f} L\n"
            f"- Disponible para envasar: {disponible:.2f} L"
        )

        return True

    except Exception as e:
        conn.rollback()
        st.error(f"❌ Error al actualizar: {e}")
        return False

    finally:
        conn.close()


# --- MAIN STREAMLIT ---
def main():
    st.title("📦 Actualizar Litros Envasados por Producción")

    # Obtener producciones
    productions = get_production_data()

    if not productions:
        st.warning("No hay producciones registradas.")
        return

    # Opciones para el selectbox
    opciones = {
        f"Lote {p['lote']} – {p['receta_nombre']} – Producido {p['cantidad_real_litros']:.2f}L – Envasado {p['litros_envasados']:.2f}L – Disponible {p['disponible']:.2f}L":
        p["produccion_id"]
        for p in productions
    }

    with st.form("form_actualizar"):
        st.subheader("Seleccione una producción para actualizar:")

        seleccion = st.selectbox("Producción:", list(opciones.keys()))
        produccion_id = opciones[seleccion]

        # Datos actuales
        datos = next(p for p in productions if p["produccion_id"] == produccion_id)

        total = float(datos["cantidad_real_litros"])
        envasado_actual = float(datos["litros_envasados"])

        nuevo_envasado = st.number_input(
            "Ingrese los litros envasados:",
            min_value=0.0,
            max_value=total,
            value=envasado_actual,
            step=0.1
        )

        enviar = st.form_submit_button("Actualizar")

        if enviar:
            if actualizar_litros_envasados(produccion_id, nuevo_envasado):
                st.rerun()


if __name__ == "__main__":
    main()
