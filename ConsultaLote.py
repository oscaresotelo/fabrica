import streamlit as st
import sqlite3
import pandas as pd

def consulta_lote():
    st.title("Consulta y Trazabilidad de Lote")
    lote_buscar = st.text_input("Ingrese el número de lote a buscar (ej: L-20250715-01):")

    if lote_buscar:
        conn = sqlite3.connect('minerva.db')

        # 1. Datos básicos del lote y producción
        df_lote = pd.read_sql_query("""
            SELECT l.numero, l.fecha, c.nombre AS cliente, r.nombre AS receta
            FROM lotes l
            LEFT JOIN clientes c ON l.cliente_id = c.id
            LEFT JOIN recetas r ON l.receta_id = r.id
            WHERE l.numero = ?
        """, conn, params=(lote_buscar,))
        if not df_lote.empty:
            st.subheader("Datos del Lote")
            st.dataframe(df_lote)
        else:
            st.warning("No se encontró el lote.")
            conn.close()
            return

        # 2. Producción asociada
        df_prod = pd.read_sql_query("""
            SELECT p.fecha, p.estado, p.cantidad_litros
            FROM producciones p
            WHERE p.lote = ?
        """, conn, params=(lote_buscar,))
        if not df_prod.empty:
            st.subheader("Producción")
            st.dataframe(df_prod)

        # 3. Materias primas usadas en la producción
        df_mp_usada = pd.read_sql_query("""
            SELECT mp.nombre AS materia_prima, pmp.cantidad_usada, pmp.lote
            FROM produccion_materia_prima pmp
            JOIN materias_primas mp ON pmp.materia_prima_id = mp.id
            WHERE pmp.lote = ?
        """, conn, params=(lote_buscar,))
        if not df_mp_usada.empty:
            st.subheader("Materias Primas Usadas")
            st.dataframe(df_mp_usada)

        # 4. Movimientos de materia prima por lote
        df_mov_mp = pd.read_sql_query("""
            SELECT mmp.fecha, mp.nombre AS materia_prima, mmp.cantidad, mmp.tipo_movimiento, mmp.destino
            FROM movimientos_materia_prima mmp
            JOIN materias_primas mp ON mmp.materia_prima_id = mp.id
            WHERE mmp.lote = ?
        """, conn, params=(lote_buscar,))
        if not df_mov_mp.empty:
            st.subheader("Movimientos de Materia Prima")
            st.dataframe(df_mov_mp)

        # 5. Envasado asociado al lote
        df_envasado = pd.read_sql_query("""
            SELECT oe.fecha, v.descripcion AS envase, oe.cantidad_unidades, oe.estado
            FROM ordenes_envasado oe
            JOIN producciones p ON oe.produccion_id = p.id
            JOIN envases v ON oe.envase_id = v.id
            WHERE p.lote = ?
        """, conn, params=(lote_buscar,))
        if not df_envasado.empty:
            st.subheader("Órdenes de Envasado")
            st.dataframe(df_envasado)

        # 6. Movimientos de envases por lote
        df_mov_env = pd.read_sql_query("""
            SELECT me.fecha, v.descripcion AS envase, me.cantidad, me.tipo_movimiento, me.observacion
            FROM movimientos_envases me
            JOIN envases v ON me.envase_id = v.id
            WHERE me.lote = ?
        """, conn, params=(lote_buscar,))
        if not df_mov_env.empty:
            st.subheader("Movimientos de Envases")
            st.dataframe(df_mov_env)

        # 7. Productos envasados por lote
        df_prod_env = pd.read_sql_query("""
            SELECT spe.fecha_ingreso, c.nombre AS cliente, r.nombre AS receta, v.descripcion AS envase, spe.cantidad
            FROM stock_productos_envasados spe
            JOIN clientes c ON spe.cliente_id = c.id
            JOIN recetas r ON spe.receta_id = r.id
            JOIN envases v ON spe.envase_id = v.id
            WHERE spe.lote = ?
        """, conn, params=(lote_buscar,))
        if not df_prod_env.empty:
            st.subheader("Productos Envasados")
            st.dataframe(df_prod_env)

        # 8. Ventas de ese lote (si corresponde)
        df_ventas = pd.read_sql_query("""
            SELECT sp.lote, sp.fecha_ingreso, c.nombre AS cliente, r.nombre AS receta, v.descripcion AS envase, sp.cantidad
            FROM stock_productos_envasados sp
            JOIN clientes c ON sp.cliente_id = c.id
            JOIN recetas r ON sp.receta_id = r.id
            JOIN envases v ON sp.envase_id = v.id
            WHERE sp.lote = ?
        """, conn, params=(lote_buscar,))
        if not df_ventas.empty:
            st.subheader("Ventas/Salidas de ese Lote")
            st.dataframe(df_ventas)

        conn.close()
