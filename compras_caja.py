import sqlite3
import streamlit as st
from datetime import datetime
import pandas as pd
import uuid

DB_FILE = 'minerva.db'

# ===============================
# UTILIDADES
# ===============================

def generar_lote_caja(tipo_caja_id):
    ahora = datetime.now().strftime("%Y%m%d%H%M")
    codigo_unico = uuid.uuid4().hex[:4].upper()
    return f"LCAJA{tipo_caja_id}_{ahora}_{codigo_unico}"

def get_proveedores():
    with sqlite3.connect(DB_FILE) as conn:
        return conn.execute("SELECT id, nombre FROM proveedores ORDER BY nombre").fetchall()

def get_tipos_caja():
    with sqlite3.connect(DB_FILE) as conn:
        # Usamos las columnas reales de tu tabla tipo_cajas
        return conn.execute("""
            SELECT id, descripcion, unidades_por_caja 
            FROM tipo_cajas 
            ORDER BY descripcion
        """).fetchall()

# ===============================
# REGISTRAR COMPRA
# ===============================

def registrar_compra_cajas(proveedor_id, tipo_caja_id, cantidad, precio_unitario, costo_flete, fecha, numero_comprobante, observaciones):
    lote = generar_lote_caja(tipo_caja_id)

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()

        # Prorrateo de flete: si el comprobante ya existe en ingresos, flete = 0 para no duplicar costo total
        cursor.execute("""
            SELECT COUNT(*) FROM movimientos_cajas 
            WHERE numero_comprobante = ? AND tipo_movimiento = 'Ingreso'
        """, (numero_comprobante,))
        costo_flete_real = 0 if cursor.fetchone()[0] > 0 else costo_flete

        # Obtener descripción del molde para el registro
        caja_info = cursor.execute("SELECT descripcion FROM tipo_cajas WHERE id = ?", (tipo_caja_id,)).fetchone()
        caja_nombre = caja_info[0] if caja_info else "Caja Genérica"

        # 1. Actualizar Stock Único del Molde
        cursor.execute("""
            UPDATE stock_cajas 
            SET cantidad_actual = cantidad_actual + ? 
            WHERE tipo_caja_id = ?
        """, (cantidad, tipo_caja_id))
        
        if cursor.rowcount == 0:
            cursor.execute("""
                INSERT INTO stock_cajas (tipo_caja_id, tipo_caja, cantidad_actual)
                VALUES (?, ?, ?)
            """, (tipo_caja_id, caja_nombre, cantidad))

        # 2. Registrar el movimiento (CORREGIDO: 10 signos '?' para 11 columnas, 1 fija)
        cursor.execute("""
            INSERT INTO movimientos_cajas (
                fecha, 
                tipo_caja_id, 
                tipo_caja, 
                cantidad, 
                tipo_movimiento, 
                numero_comprobante, 
                observacion, 
                precio_unitario, 
                costo_flete, 
                lote, 
                proveedor_id
            ) VALUES (?, ?, ?, ?, 'Ingreso', ?, ?, ?, ?, ?, ?)
        """, (
            fecha,               # 1
            tipo_caja_id,        # 2
            caja_nombre,         # 3
            cantidad,            # 4
            # 'Ingreso' va fijo    --
            numero_comprobante,  # 5
            observaciones,       # 6
            precio_unitario,     # 7
            costo_flete_real,    # 8
            lote,                # 9
            proveedor_id         # 10
        ))

        conn.commit()
    return lote

# ===============================
# INTERFAZ STREAMLIT
# ===============================

def compras_cajas():
    st.header("📦 Suministros: Compra de Cajas Genéricas")
    
    proveedores = get_proveedores()
    tipos_caja = get_tipos_caja()

    if not tipos_caja:
        st.warning("No hay moldes de cajas definidos en la base de datos.")
        return

    with st.form("form_compra_cajas", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            prov_sel = st.selectbox("Proveedor", proveedores, format_func=lambda x: x[1])
            caja_sel = st.selectbox("Modelo de Caja", tipos_caja, 
                                    format_func=lambda x: f"{x[1]} (x{x[2]}u)")
            cantidad = st.number_input("Cantidad de cajas compradas", min_value=1, value=100)
        
        with col2:
            nro_fac = st.text_input("N° Factura / Remito")
            p_unit = st.number_input("Precio por Caja ($)", min_value=0.0, format="%.2f")
            flete = st.number_input("Flete Total del comprobante ($)", min_value=0.0, format="%.2f")

        fecha = st.date_input("Fecha de recepción", value=datetime.now())
        obs = st.text_area("Observaciones")
        
        if st.form_submit_button("Confirmar Ingreso a Depósito"):
            if not nro_fac:
                st.warning("El N° de comprobante es obligatorio para el seguimiento.")
            else:
                try:
                    lote = registrar_compra_cajas(prov_sel[0], caja_sel[0], cantidad, p_unit, flete, 
                                                fecha.isoformat(), nro_fac, obs)
                    st.success(f"✅ Ingreso registrado con éxito. Lote: {lote}")
                except Exception as e:
                    st.error(f"Error al guardar en la base de datos: {e}")

    # --- Historial ---
    st.markdown("---")
    st.subheader("📊 Historial de Compras y Costos Reales")
    
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql("""
            SELECT 
                fecha, 
                tipo_caja as Modelo, 
                cantidad, 
                precio_unitario, 
                costo_flete, 
                numero_comprobante as Factura, 
                lote
            FROM movimientos_cajas 
            WHERE tipo_movimiento = 'Ingreso'
            ORDER BY id DESC
        """, conn)

    if not df.empty:
        # Cálculo de prorrateo para el Costo Real
        resumen = df.groupby("Factura").agg(tot_cant=("cantidad", "sum"), tot_flete=("costo_flete", "sum")).reset_index()
        df = df.merge(resumen, on="Factura")
        df["Costo Final"] = df["precio_unitario"] + (df["tot_flete"] / df["tot_cant"])

        st.dataframe(
            df[["fecha", "Modelo", "cantidad", "precio_unitario", "Costo Final", "Factura"]],
            column_config={
                "precio_unitario": st.column_config.NumberColumn("P. Unit.", format="$ %.2f"),
                "Costo Final": st.column_config.NumberColumn("Costo Real", format="$ %.2f")
            }, 
            use_container_width=True, 
            hide_index=True
        )

if __name__ == "__main__":
    compras_cajas()