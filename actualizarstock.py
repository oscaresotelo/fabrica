import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import time

# =================================================================================================
# FUNCIÓN DE CONEXIÓN
# =================================================================================================
def get_db_connection():
    try:
        conn = sqlite3.connect('minerva.db') 
        return conn
    except sqlite3.Error as e:
        st.error(f"❌ Error al conectar con la base de datos: {e}")
        return None

st.set_page_config(layout="wide", page_title="Control de Stock Capilar")
st.title("📦 Ajuste de Stock por Cliente, Producto y Envase")
st.markdown("Filtre jerárquicamente para localizar el lote a ajustar.")
st.markdown("---")

conn = get_db_connection()
if conn is None: st.stop()

# =================================================================================================
# CARGA DE DATOS
# =================================================================================================
query = """
    SELECT 
        t1.id AS stock_id, t1.lote, t1.cantidad, t1.cliente_id, t1.receta_id, t1.envase_id,
        t2.nombre AS producto_nombre, t3.descripcion AS envase_nombre, t4.nombre AS cliente_nombre
    FROM stock_productos_envasados t1 
    JOIN recetas t2 ON t1.receta_id = t2.id 
    JOIN envases t3 ON t1.envase_id = t3.id
    JOIN clientes t4 ON t1.cliente_id = t4.id
    WHERE t1.cantidad >= 0 
    ORDER BY t4.nombre ASC, t2.nombre ASC
"""
try:
    df_completo = pd.read_sql_query(query, conn)
finally:
    conn.close()

# =================================================================================================
# FILTROS JERÁRQUICOS
# =================================================================================================
col_f1, col_f2, col_f3, col_f4 = st.columns(4)

with col_f1:
    cliente_sel = st.selectbox("1. Cliente", options=sorted(df_completo['cliente_nombre'].unique()), index=None)
df_c = df_completo[df_completo['cliente_nombre'] == cliente_sel] if cliente_sel else df_completo

with col_f2:
    receta_sel = st.selectbox("2. Producto/Receta", options=sorted(df_c['producto_nombre'].unique()), index=None, disabled=not cliente_sel)
df_r = df_c[df_c['producto_nombre'] == receta_sel] if receta_sel else df_c

with col_f3:
    envase_sel = st.selectbox("3. Envase", options=sorted(df_r['envase_nombre'].unique()), index=None, disabled=not receta_sel)
df_e = df_r[df_r['envase_nombre'] == envase_sel] if envase_sel else df_r

with col_f4:
    opciones_lote = [f"Lote: {r['lote']} (Stock: {r['cantidad']:.2f}L)" for _, r in df_e.iterrows()]
    lote_sel = st.selectbox("4. Lote", options=opciones_lote, index=None, disabled=not envase_sel)

st.markdown("---")

# =================================================================================================
# FORMULARIO CON BOTÓN DE ENVÍO
# =================================================================================================
with st.form("form_ajuste_final"):
    if lote_sel:
        datos_sel = df_e.iloc[opciones_lote.index(lote_sel)]
        stock_actual = float(datos_sel['cantidad'])
        stock_id = int(datos_sel['stock_id'])
        
        st.info(f"📍 **Editando:** {datos_sel['producto_nombre']} | {datos_sel['envase_nombre']} | Lote: {datos_sel['lote']}")
        
        c1, c2 = st.columns(2)
        nueva_cant = c1.number_input("Nueva Cantidad Total (Litros):", min_value=0.0, value=stock_actual, step=0.1)
        motivo = c2.text_area("Justificación del cambio:")
        
        # El botón de submit DEBE estar dentro del formulario
        btn_submit = st.form_submit_button("💾 Confirmar Ajuste")
        
        if btn_submit:
            if nueva_cant == stock_actual:
                st.warning("No hay cambios.")
            elif not motivo.strip():
                st.error("La justificación es obligatoria.")
            else:
                conn_trans = get_db_connection()
                try:
                    cur = conn_trans.cursor()
                    diff = nueva_cant - stock_actual
                    cur.execute("INSERT INTO movimientos_productos_envasados (stock_id, fecha, cantidad, tipo_movimiento, observacion) VALUES (?,?,?,?,?)", 
                                (stock_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), abs(diff), 'Ingreso' if diff > 0 else 'Egreso', f"Ajuste: {motivo}"))
                    cur.execute("UPDATE stock_productos_envasados SET cantidad = ? WHERE id = ?", (nueva_cant, stock_id))
                    conn_trans.commit()
                    st.success("✅ Stock actualizado.")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
                finally:
                    conn_trans.close()
    else:
        st.warning("Seleccione Cliente, Receta, Envase y Lote para habilitar el formulario.")