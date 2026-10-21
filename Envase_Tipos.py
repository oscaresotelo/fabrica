import streamlit as st
import sqlite3
import pandas as pd

DB_PATH = "minerva.db"

def get_connection():
    try:
        conn = sqlite3.connect(DB_PATH)
        return conn
    except Exception as e:
        st.error(f"Error al conectar a la base de datos: {e}")
        return None

def cargar_envases():
    conn = get_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql_query("SELECT id, descripcion, unidad, cliente FROM envases ORDER BY cliente, descripcion", conn)
        if df.empty:
            st.info("No hay envases cargados en la base de datos.")
        return df
    except Exception as e:
        st.error(f"Error al cargar envases: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def insertar_envase(descripcion, unidad, cliente):
    conn = get_connection()
    if conn is None:
        return
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO envases (descripcion, unidad, cliente) VALUES (?, ?, ?)",
            (descripcion.strip(), unidad.strip(), cliente.strip())
        )
        conn.commit()
        st.success("Envase agregado correctamente.")
    except sqlite3.IntegrityError:
        st.error("Ya existe un envase con esa descripción y cliente.")
    except Exception as e:
        st.error(f"Error al insertar envase: {e}")
    finally:
        conn.close()

def modificar_envase(envase_id, descripcion, unidad, cliente):
    conn = get_connection()
    if conn is None:
        return
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE envases SET descripcion=?, unidad=?, cliente=?
            WHERE id=?
        """, (descripcion.strip(), unidad.strip(), cliente.strip(), envase_id))
        conn.commit()
        st.success("Envase modificado correctamente.")
    except sqlite3.IntegrityError:
        st.error("No se puede modificar. Ya existe un envase con esa descripción y cliente.")
    except Exception as e:
        st.error(f"Error al modificar envase: {e}")
    finally:
        conn.close()

def main():
    st.title("📦 Gestión de Envases")

    df_envases = cargar_envases()

    if df_envases.empty:
        st.warning("No se encontraron envases para mostrar.")
    else:
        st.subheader("Listado de Envases")
        st.dataframe(df_envases)

    st.markdown("---")

    modo = st.radio("¿Qué deseas hacer?", ("Agregar nuevo envase", "Modificar envase existente"))

    if modo == "Agregar nuevo envase":
        with st.form("form_agregar"):
            descripcion = st.text_input("Descripción (ej: 1kg, 250gr, 30cc)")
            unidad = st.text_input("Unidad (ej: kg, gr, cc)")
            cliente = st.text_input("Cliente (ej: Minerva)")
            enviar = st.form_submit_button("Agregar envase")

            if enviar:
                if not descripcion or not unidad or not cliente:
                    st.error("Completa todos los campos.")
                else:
                    insertar_envase(descripcion, unidad, cliente)
                    st.experimental_rerun()

    else:  # Modificar envase
        if df_envases.empty:
            st.info("No hay envases para modificar.")
            return

        opciones = df_envases.apply(lambda row: f"{row['id']} - {row['descripcion']} ({row['cliente']})", axis=1).tolist()
        envase_seleccionado = st.selectbox("Selecciona un envase para modificar", opciones)

        if envase_seleccionado:
            envase_id = int(envase_seleccionado.split(" - ")[0])
            envase_data = df_envases[df_envases["id"] == envase_id].iloc[0]

            with st.form("form_modificar"):
                descripcion = st.text_input("Descripción", envase_data["descripcion"])
                unidad = st.text_input("Unidad", envase_data["unidad"])
                cliente = st.text_input("Cliente", envase_data["cliente"])
                enviar = st.form_submit_button("Modificar envase")

                if enviar:
                    if not descripcion or not unidad or not cliente:
                        st.error("Completa todos los campos.")
                    else:
                        modificar_envase(envase_id, descripcion, unidad, cliente)
                        st.experimental_rerun()

if __name__ == "__main__":
    main()
