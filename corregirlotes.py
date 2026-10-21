import streamlit as st
import sqlite3
import pandas as pd

def limpiar_movimientos_materia_prima():
    st.title("🗑️ Limpieza de Movimientos de Materias Primas Huérfanos")
    st.markdown("---")

    def obtener_movimientos_huerfanos(lote_seleccionado):
        """Obtiene los movimientos de materia prima que no tienen lote correspondiente."""
        with sqlite3.connect("minerva.db") as conn:
            cur = conn.cursor()
            query = """
                SELECT mmp.id, mmp.lote, mmp.fecha, mmp.cantidad, mp.nombre AS materia_prima, mp.id AS materia_prima_id
                FROM movimientos_materia_prima mmp
                LEFT JOIN materias_primas mp ON mmp.materia_prima_id = mp.id
                WHERE mmp.lote IS NOT NULL
                AND mmp.lote NOT IN (SELECT numero FROM lotes)
            """
            params = ()
            if lote_seleccionado:
                query += " AND mmp.lote = ?"
                params = (lote_seleccionado,)
            else:
                 return pd.DataFrame() # Retornar DataFrame vacío si no hay lote seleccionado

            cur.execute(query, params)
            column_names = ["ID", "Lote", "Fecha", "Cantidad", "Materia Prima", "materia_prima_id"]
            movimientos = cur.fetchall()
            return pd.DataFrame(movimientos, columns=column_names)

    def obtener_lotes_huerfanos():
        """Obtiene la lista de lotes huerfanos para el selectbox."""
        with sqlite3.connect("minerva.db") as conn:
            cur = conn.cursor()
            query = """
                SELECT DISTINCT mmp.lote
                FROM movimientos_materia_prima mmp
                WHERE mmp.lote IS NOT NULL
                AND mmp.lote NOT IN (SELECT numero FROM lotes)
            """
            cur.execute(query)
            lotes = [row[0] for row in cur.fetchall()]
            return lotes

    def actualizar_stock(conn, materia_prima_id, cantidad):
        """Actualiza el stock de la materia prima."""
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE stock_materias_primas
                SET cantidad = cantidad + ?
                WHERE materia_prima_id = ?
            """, (cantidad, materia_prima_id))
            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            st.error(f"Error al actualizar el stock: {e}")
            return False

    def eliminar_movimiento(conn, movimiento_id, lote, materia_prima_id, cantidad):
        """Elimina el movimiento de materia prima y actualiza el stock."""
        try:
             conn.execute("BEGIN")
             # Sumar la cantidad al stock (el movimiento es negativo, así que sumamos su valor absoluto)
             if not actualizar_stock(conn, materia_prima_id, -cantidad):
                 conn.rollback()
                 st.error("Error al actualizar el stock. Operación cancelada.")
                 return False

             # Eliminar el movimiento
             cur = conn.cursor()
             cur.execute("DELETE FROM movimientos_materia_prima WHERE id = ?", (movimiento_id,))
             conn.commit()
             st.success(f"✅ Movimiento con ID {movimiento_id} (Lote: {lote}) eliminado correctamente.")
             return True
        except sqlite3.Error as e:
             conn.rollback()
             st.error(f"Ocurrió un error al eliminar el movimiento: {e}")
             return False

    # --- Interfaz Streamlit ---
    lotes_huerfanos = obtener_lotes_huerfanos()
    lote_seleccion = st.selectbox("Seleccionar Lote Huérfano:", [None] + lotes_huerfanos, index=0, format_func=lambda x: "Seleccionar Lote" if x is None else x)

    if lote_seleccion:
        df_movimientos = obtener_movimientos_huerfanos(lote_seleccion)

        if df_movimientos.empty:
            st.info("ℹ️ No se encontraron movimientos huérfanos para este lote.")
        else:
            # Agregar un checkbox para cada fila en el DataFrame
            selected_ids = {}
            for index, row in df_movimientos.iterrows():
                selected_ids[row["ID"]] = st.checkbox(f"Seleccionar Movimiento ID: {row['ID']}", key=f"checkbox_{row['ID']}")

            movimientos_seleccionados = [id for id, seleccionado in selected_ids.items() if seleccionado]

            if st.button("⚠️ Confirmar Eliminación de Movimientos Seleccionados"):
                total_eliminados = 0
                with sqlite3.connect("minerva.db") as conn:
                    for index, row in df_movimientos[df_movimientos['ID'].isin(movimientos_seleccionados)].iterrows():
                        movimiento_id = row["ID"]
                        lote = row["Lote"]
                        materia_prima_id = row["materia_prima_id"]
                        cantidad = row["Cantidad"]

                        if eliminar_movimiento(conn, movimiento_id, lote, materia_prima_id, cantidad):
                             total_eliminados += 1

                st.success(f"✅ Se eliminaron {total_eliminados} movimientos seleccionados del lote {lote_seleccion}.")
                st.rerun() # Recargar la página para actualizar la tabla

    else:
        st.info("ℹ️ Por favor, selecciona un lote para ver los movimientos huérfanos.")

# Ejecutar la función principal
limpiar_movimientos_materia_prima()