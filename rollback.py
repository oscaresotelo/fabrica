import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

def mostrar_producciones_y_movimientos():
    """Muestra las producciones y sus movimientos de stock relacionados, con opción de anular."""

    st.title("🏭 Producciones y Movimientos de Stock")

    # Conexión a la base de datos
    conn = sqlite3.connect("minerva.db")

    # Consulta para obtener las producciones, incluyendo el nombre de la receta
    query_producciones = """
    SELECT
        p.id AS produccion_id,
        p.pedido_id,
        p.fecha,
        p.lote,
        p.estado,
        p.cantidad_litros,
        p.cantidad_real_litros,
        r.nombre AS nombre_receta
    FROM producciones p
    JOIN pedidos_produccion pp ON p.pedido_id = pp.id
    JOIN recetas r ON pp.receta_id = r.id
    ORDER BY p.fecha DESC
    """
    df_producciones = pd.read_sql_query(query_producciones, conn)

    # Consulta para obtener los movimientos de materia prima
    query_movimientos = """
    SELECT id AS movimiento_id, materia_prima_id, lote, fecha, cantidad, tipo_movimiento, destino
    FROM movimientos_materia_prima
    ORDER BY fecha DESC
    """
    df_movimientos = pd.read_sql_query(query_movimientos, conn)

    # Fusionar los DataFrames basados en la columna 'lote'
    df_fusionado = pd.merge(
        df_producciones,
        df_movimientos,
        on='lote',
        how='left',
        suffixes=('_produccion', '_movimiento')
    )

    # Mostrar los DataFrames fusionados
    st.subheader("Producciones y Movimientos de Stock Relacionados")
    if not df_fusionado.empty:
        st.dataframe(df_fusionado)

        # Opción de anular producción
        st.subheader("⚠️ Anular Producción")
        producciones_para_anular = df_producciones[df_producciones['estado'] == 'producido']
        if not producciones_para_anular.empty:
            # Crear lista con Lote y Nombre de receta para mostrar en selectbox
            opciones_lote = [
                f"Lote {row['lote']} - {row['nombre_receta']}" 
                for _, row in producciones_para_anular.iterrows()
            ]

            seleccion_opcion = st.selectbox(
                "Selecciona el lote a anular:",
                opciones_lote
            )

            # Extraer el número de lote del string seleccionado
            seleccion_lote = seleccion_opcion.split(" - ")[0].replace("Lote ", "")

            if st.button(f"Anular {seleccion_opcion}"):
                try:
                    cur = conn.cursor()
                    conn.execute("BEGIN")

                    # Obtener movimientos de materia prima asociados al lote
                    cur.execute("""
                        SELECT materia_prima_id, cantidad
                        FROM movimientos_materia_prima
                        WHERE lote = ? AND tipo_movimiento = 'egreso' AND destino = 'produccion'
                    """, (seleccion_lote,))
                    movimientos = cur.fetchall()

                    fecha_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    # Revertir stock y registrar movimientos de ingreso
                    for materia_prima_id, cantidad_usada in movimientos:
                        # Sumar stock de nuevo
                        cur.execute("""
                            INSERT INTO stock_materias_primas (materia_prima_id, cantidad)
                            VALUES (?, ?)
                            ON CONFLICT(materia_prima_id) DO UPDATE SET cantidad = cantidad + excluded.cantidad
                        """, (materia_prima_id, -cantidad_usada))

                        # Registrar movimiento de ingreso con destino permitido
                        cur.execute("""
                            INSERT INTO movimientos_materia_prima
                            (materia_prima_id, fecha, cantidad, tipo_movimiento, destino, lote)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (materia_prima_id, fecha_now, abs(cantidad_usada), 'ingreso', 'otro', seleccion_lote))

                    # Actualizar estado de la producción y del pedido
                    cur.execute("UPDATE producciones SET estado = 'anulado' WHERE lote = ?", (seleccion_lote,))
                    cur.execute("""
                        UPDATE pedidos_produccion
                        SET estado = 'pendiente', lote = NULL
                        WHERE id = (SELECT pedido_id FROM producciones WHERE lote = ?)
                    """, (seleccion_lote,))

                    conn.commit()
                    st.success(f"✅ Producción del {seleccion_opcion} anulada correctamente.")
                except sqlite3.Error as e:
                    conn.rollback()
                    st.error(f"❌ Error al anular la producción: {e}")
        else:
            st.info("No hay producciones en estado 'producido' para anular.")

    else:
        st.warning("No se encontraron producciones con movimientos de stock relacionados.")

    # Identificar y mostrar movimientos sin relación
    movimientos_sin_relacion = df_movimientos[~df_movimientos['lote'].isin(df_producciones['lote'])]

    st.subheader("Movimientos de Stock Sin Relación con Producciones")
    if not movimientos_sin_relacion.empty:
        st.dataframe(movimientos_sin_relacion)
    else:
        st.success("Todos los movimientos de stock están relacionados con alguna producción.")

    conn.close()


# Ejecutar la función principal
mostrar_producciones_y_movimientos()
