import streamlit as st
import sqlite3
from datetime import date
import pandas as pd

# Configuración inicial de la página
st.set_page_config(page_title="Gestión de Pagos e Imputaciones - Minerva", layout="wide")

def inicializar_base_datos(db_path="minerva.db"):
    """Crea la tabla si no existe y asegura que tenga todas las columnas necesarias"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pagos_revendedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            revendedor_id INTEGER NOT NULL,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha_pago DATE NOT NULL,
            numero_pedido TEXT,
            importe REAL NOT NULL,
            destino_pago TEXT NOT NULL,
            proveedor_id INTEGER,
            orden_compra_id TEXT,
            observaciones TEXT,
            FOREIGN KEY (revendedor_id) REFERENCES revendedores(id),
            FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
        )
    """)
    
    cursor.execute("PRAGMA table_info(pagos_revendedores)")
    columnas_existentes = [col[1] for col in cursor.fetchall()]
    
    if "proveedor_id" not in columnas_existentes:
        cursor.execute("ALTER TABLE pagos_revendedores ADD COLUMN proveedor_id INTEGER")
        
    if "orden_compra_id" not in columnas_existentes:
        cursor.execute("ALTER TABLE pagos_revendedores ADD COLUMN orden_compra_id TEXT")
        
    conn.commit()
    conn.close()

def main():
    st.title("🧪 Minerva - Gestión de Pagos, Imputaciones y Saldos de OC")
    
    db_path = "minerva.db"
    inicializar_base_datos(db_path)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Cargar lista de revendedores
    try:
        cursor.execute("SELECT id, nombre FROM revendedores ORDER BY nombre ASC")
        revendedores = cursor.fetchall()
    except sqlite3.OperationalError:
        revendedores = []
        
    # 2. Cargar lista de proveedores
    try:
        cursor.execute("SELECT id, nombre FROM proveedores ORDER BY nombre ASC")
        proveedores = cursor.fetchall()
    except sqlite3.OperationalError:
        proveedores = []
        
    conn.close()
    
    opciones_revendedores = {r[1]: r[0] for r in revendedores} if revendedores else {"Ejemplo Revendedor": 1}
    opciones_proveedores = {p[1]: p[0] for p in proveedores} if proveedores else {}

    # Creación de Pestañas
    tab_registro, tab_reportes = st.tabs(["📝 Cargar e Imputar Pago", "🔍 Reportes, Trazabilidad y Saldos"])

    # ==========================================
    # PESTAÑA 1: FORMULARIO DE REGISTRO E IMPUTACIÓN
    # ==========================================
    with tab_registro:
        st.subheader("Registrar y Cruce de Pagos (Revendedor ➡️ Proveedor / OC)")
        
        nombre_revendedor = st.selectbox("1. Seleccionar Revendedor que efectúa el pago", list(opciones_revendedores.keys()), key="reg_rev")
        
        col1, col2 = st.columns(2)
        with col1:
            fecha_pago = st.date_input("Fecha de Pago", value=date.today())
            numero_pedido = st.text_input("Nº de Pedido o Comprobante del Revendedor", placeholder="Ej: PED-2026-001")
        
        with col2:
            importe = st.number_input("Importe del Pago ($)", min_value=0.0, format="%.2f", step=100.0)
            
            tipo_destino = st.selectbox("Destino de los fondos", [
                "Cuenta Propia (Banco, Efectivo, MP, etc.)", 
                "Imputar a Proveedor / Orden de Compra"
            ])
        
        proveedor_id = None
        orden_compra_id = None
        destino_pago_texto = ""

        if tipo_destino == "Cuenta Propia (Banco, Efectivo, MP, etc.)":
            destino_pago_texto = st.text_input("Detalle de Cuenta Propia", placeholder="Ej: Banco Macro, Efectivo Taller...")
        else:
            st.markdown("---")
            st.markdown("##### 🏢 Imputación Directa a Proveedor y Orden de Compra")
            
            if opciones_proveedores:
                nombre_proveedor_sel = st.selectbox("2. Seleccionar Proveedor", list(opciones_proveedores.keys()), key="sel_prov")
                proveedor_id = opciones_proveedores[nombre_proveedor_sel]
                
                # Consultar órdenes de compra del proveedor
                conn = sqlite3.connect(db_path)
                try:
                    query_oc = "SELECT id, fecha_orden, estado, observaciones FROM ordenes_de_compra WHERE proveedor_id = ? ORDER BY id DESC"
                    df_ordenes_prov = pd.read_sql(query_oc, conn, params=(proveedor_id,))
                except Exception:
                    df_ordenes_prov = pd.DataFrame()
                conn.close()
                
                if not df_ordenes_prov.empty:
                    st.markdown(f"**📋 Órdenes de Compra y Estado de Deuda para {nombre_proveedor_sel}:**")
                    
                    conn = sqlite3.connect(db_path)
                    saldos_list = []
                    for _, row in df_ordenes_prov.iterrows():
                        oc_id_val = str(row['id'])
                        
                        res_total = conn.execute("""
                            SELECT SUM(cantidad * precio_unitario) FROM detalle_orden_compra WHERE orden_compra_id = ?
                        """, (oc_id_val,)).fetchone()
                        total_oc = res_total[0] if res_total and res_total[0] else 0.0
                        
                        res_pagos = conn.execute("""
                            SELECT SUM(importe) FROM pagos_revendedores WHERE orden_compra_id = ?
                        """, (oc_id_val,)).fetchone()
                        pagos_oc = res_pagos[0] if res_pagos and res_pagos[0] else 0.0
                        
                        saldo_pendiente = total_oc - pagos_oc
                        
                        saldos_list.append({
                            "ID OC": oc_id_val,
                            "Fecha": row['fecha_orden'],
                            "Estado": row['estado'],
                            "Total OC ($)": total_oc,
                            "Pagado ($)": pagos_oc,
                            "Saldo Deudor ($)": saldo_pendiente
                        })
                    conn.close()
                    
                    df_saldos_oc = pd.DataFrame(saldos_list)
                    st.dataframe(df_saldos_oc, use_container_width=True)
                    
                    opciones_ordenes = {f"Orden de Compra #{row['ID OC']} | Total: ${row['Total OC ($)']:,.2f} | Saldo Pendiente: ${row['Saldo Deudor ($)']:,.2f}": row['ID OC'] for _, row in df_saldos_oc.iterrows()}
                    orden_sel_key = st.selectbox("3. Seleccionar Orden de Compra a imputar este pago", list(opciones_ordenes.keys()), key="sel_oc")
                    orden_compra_id = opciones_ordenes[orden_sel_key]
                    
                    if orden_compra_id:
                        conn = sqlite3.connect(db_path)
                        try:
                            query_detalle = """
                                SELECT 
                                    mp.nombre AS 'Materia Prima',
                                    d.cantidad AS 'Cantidad',
                                    d.precio_unitario AS 'Precio Unitario ($)',
                                    (d.cantidad * d.precio_unitario) AS 'Subtotal ($)'
                                FROM detalle_orden_compra d
                                JOIN materias_primas mp ON d.materia_prima_id = mp.id
                                WHERE d.orden_compra_id = ?
                            """
                            df_detalle = pd.read_sql(query_detalle, conn, params=(orden_compra_id,))
                            
                            if not df_detalle.empty:
                                st.markdown(f"📦 **Detalle de Materias Primas de la OC #{orden_compra_id}:**")
                                st.dataframe(df_detalle, use_container_width=True)
                        except Exception:
                            pass
                        finally:
                            conn.close()
                else:
                    st.warning(f"No se encontraron órdenes de compra registradas para {nombre_proveedor_sel}.")
                    orden_compra_id = st.text_input("Nº de Orden de Compra Manual", placeholder="Ej: 1", key="manual_oc")
            else:
                st.warning("No se encontraron registros en la tabla 'proveedores'.")
                nombre_proveedor_sel = st.text_input("Nombre del Proveedor", key="txt_prov_libre")
                orden_compra_id = st.text_input("Nº de Orden de Compra", placeholder="Ej: 1", key="txt_oc_libre")
                
            nombre_prov_str = nombre_proveedor_sel if 'nombre_proveedor_sel' in locals() else "Proveedor Genérico"
            oc_str = orden_compra_id if orden_compra_id else "S/N"
            destino_pago_texto = f"Proveedor: {nombre_prov_str} (OC ID: {oc_str})"
            st.markdown("---")
            
        observaciones = st.text_area("Observaciones / Notas de Imputación", placeholder="Ej: Pago de revendedor aplicado directamente a orden de compra...", key="obs_pago")
        
        if st.button("💾 Guardar e Imputar Pago", type="primary"):
            if importe <= 0:
                st.error("El importe debe ser mayor a 0.")
            elif not destino_pago_texto.strip():
                st.error("Por favor, completá los datos del destino del pago.")
            else:
                rev_id = opciones_revendedores[nombre_revendedor]
                
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO pagos_revendedores 
                    (revendedor_id, fecha_pago, numero_pedido, importe, destino_pago, proveedor_id, orden_compra_id, observaciones)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (rev_id, fecha_pago, numero_pedido, importe, destino_pago_texto.strip(), proveedor_id, orden_compra_id, observaciones))
                
                conn.commit()
                conn.close()
                st.success(f"¡Imputación exitosa! Pago de ${importe:,.2f} registrado y asociado a la orden de compra.")

        st.divider()
        st.subheader("📋 Últimos Pagos e Imputaciones Registradas")
        conn = sqlite3.connect(db_path)
        try:
            query = """
                SELECT 
                    p.id,
                    r.nombre AS revendedor,
                    p.fecha_pago,
                    p.importe,
                    p.destino_pago,
                    p.orden_compra_id AS 'Orden Compra ID',
                    p.observaciones
                FROM pagos_revendedores p
                JOIN revendedores r ON p.revendedor_id = r.id
                ORDER BY p.fecha_pago DESC
                LIMIT 10
            """
            df_recientes = pd.read_sql(query, conn)
            if not df_recientes.empty:
                st.dataframe(df_recientes, use_container_width=True)
            else:
                st.info("No hay pagos registrados aún.")
        except Exception:
            st.info("Registrá un pago para visualizar la tabla.")
        finally:
            conn.close()

    # ==========================================
    # PESTAÑA 2: REPORTES, TRAZABILIDAD Y SALDOS
    # ==========================================
    with tab_reportes:
        st.subheader("📊 Panel de Reportes y Trazabilidad")
        
        # Selector de tipo de reporte dentro de la misma pestaña
        tipo_reporte = st.radio(
            "Seleccioná el tipo de reporte que deseás consultar:",
            ["🏢 Auditoría de Cuenta Corriente por Proveedor", "👥 Trazabilidad de Pagos e Ingresos por Revendedor"],
            horizontal=True
        )
        
        st.markdown("---")
        
        if tipo_reporte == "🏢 Auditoría de Cuenta Corriente por Proveedor":
            st.markdown("##### Estado de Deuda y Pagos Aplicados a Proveedores")
            if opciones_proveedores:
                prov_reporte_nombre = st.selectbox("Seleccionar Proveedor a Auditar", list(opciones_proveedores.keys()), key="rep_prov_sel")
                prov_reporte_id = opciones_proveedores[prov_reporte_nombre]
                
                conn = sqlite3.connect(db_path)
                try:
                    query_oc_rep = "SELECT id, fecha_orden, estado, observaciones FROM ordenes_de_compra WHERE proveedor_id = ? ORDER BY id DESC"
                    df_oc_rep = pd.read_sql(query_oc_rep, conn, params=(prov_reporte_id,))
                except Exception:
                    df_oc_rep = pd.DataFrame()
                
                if not df_oc_rep.empty:
                    reporte_saldos = []
                    total_deuda_general = 0.0
                    total_pagado_general = 0.0
                    total_neto_general = 0.0
                    
                    for _, row in df_oc_rep.iterrows():
                        oc_id = str(row['id'])
                        
                        res_t = conn.execute("SELECT SUM(cantidad * precio_unitario) FROM detalle_orden_compra WHERE orden_compra_id = ?", (oc_id,)).fetchone()
                        t_oc = res_t[0] if res_t and res_t[0] else 0.0
                        
                        res_p = conn.execute("SELECT SUM(importe) FROM pagos_revendedores WHERE orden_compra_id = ?", (oc_id,)).fetchone()
                        p_oc = res_p[0] if res_p and res_p[0] else 0.0
                        
                        s_oc = t_oc - p_oc
                        
                        total_deuda_general += t_oc
                        total_pagado_general += p_oc
                        total_neto_general += s_oc
                        
                        reporte_saldos.append({
                            "ID OC": oc_id,
                            "Fecha Orden": row['fecha_orden'],
                            "Estado": row['estado'],
                            "Total Original ($)": t_oc,
                            "Total Pagado ($)": p_oc,
                            "Saldo Pendiente ($)": s_oc
                        })
                    
                    df_estado_cta = pd.DataFrame(reporte_saldos)
                    
                    col_m1, col_m2, col_m3 = st.columns(3)
                    col_m1.metric("Deuda Total Histórica", f"${total_deuda_general:,.2f}")
                    col_m2.metric("Total Abonado con Revendedores", f"${total_pagado_general:,.2f}")
                    col_m3.metric("Saldo Neto Adeudado Actual", f"${total_neto_general:,.2f}", delta_color="inverse")
                    
                    st.markdown(f"**Desglose por Orden de Compra - {prov_reporte_nombre}**")
                    st.dataframe(df_estado_cta, use_container_width=True)
                    
                    st.markdown("---")
                    st.markdown(f"**Historial de Imputaciones aplicadas a {prov_reporte_nombre}**")
                    query_pagos_prov = """
                        SELECT 
                            p.id AS 'ID Pago',
                            r.nombre AS 'Revendedor que Aportó',
                            p.fecha_pago AS 'Fecha Pago',
                            p.numero_pedido AS 'Nº Pedido Revendedor',
                            p.importe AS 'Importe Imputado ($)',
                            p.orden_compra_id AS 'ID Orden Compra',
                            p.observaciones AS 'Observaciones'
                        FROM pagos_revendedores p
                        JOIN revendedores r ON p.revendedor_id = r.id
                        WHERE p.proveedor_id = ?
                        ORDER BY p.fecha_pago DESC
                    """
                    df_hist_pagos = pd.read_sql(query_pagos_prov, conn, params=(prov_reporte_id,))
                    
                    if not df_hist_pagos.empty:
                        st.dataframe(df_hist_pagos, use_container_width=True)
                        csv_cc = df_hist_pagos.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label=f"📥 Descargar Cuenta Corriente de {prov_reporte_nombre}",
                            data=csv_cc,
                            file_name=f"cuenta_corriente_{prov_reporte_nombre}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.info(f"No hay pagos de revendedores imputados a este proveedor todavía.")
                else:
                    st.warning(f"El proveedor {prov_reporte_nombre} no tiene órdenes de compra registradas.")
                
                conn.close()
            else:
                st.warning("No hay proveedores registrados en la base de datos.")
                
        else:
            st.markdown("##### 👥 Ingresos de Dinero y Destino por Revendedor")
            
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                opciones_filtro_rev = ["Todos los Revendedores"] + list(opciones_revendedores.keys())
                revendedor_seleccionado = st.selectbox("Filtrar por Revendedor", opciones_filtro_rev, key="filtro_rev")
            with col_f2:
                fecha_desde = st.date_input("Fecha Desde", value=date.today().replace(day=1), key="f_desde")
            with col_f3:
                fecha_hasta = st.date_input("Fecha Hasta", value=date.today(), key="f_hasta")

            query_base = """
                SELECT 
                    p.id AS 'ID Pago',
                    r.nombre AS 'Revendedor',
                    p.fecha_pago AS 'Fecha de Pago',
                    p.numero_pedido AS 'Nº Pedido / Comprobante',
                    p.importe AS 'Dinero Ingresado ($)',
                    p.destino_pago AS 'Destino / Imputación (A dónde fue)',
                    p.observaciones AS 'Observaciones'
                FROM pagos_revendedores p
                JOIN revendedores r ON p.revendedor_id = r.id
                WHERE p.fecha_pago BETWEEN ? AND ?
            """
            params = [fecha_desde, fecha_hasta]

            if revendedor_seleccionado != "Todos los Revendedores":
                query_base += " AND r.id = ?"
                params.append(opciones_revendedores[revendedor_seleccionado])

            query_base += " ORDER BY p.fecha_pago DESC"

            conn = sqlite3.connect(db_path)
            df_ingresos = pd.read_sql(query_base, conn, params=params)
            conn.close()

            st.divider()

            if not df_ingresos.empty:
                total_ingresado = df_ingresos['Dinero Ingresado ($)'].sum()
                st.metric(label=f"Total Dinero Ingresado ({revendedor_seleccionado})", value=f"${total_ingresado:,.2f}")
                st.dataframe(df_ingresos, use_container_width=True)
                
                csv_ing = df_ingresos.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Descargar Reporte de Ingresos en CSV",
                    data=csv_ing,
                    file_name=f"ingresos_revendedores_{fecha_desde}_al_{fecha_hasta}.csv",
                    mime="text/csv"
                )
            else:
                st.warning("No se encontraron registros de pagos para los filtros seleccionados.")

if __name__ == "__main__":
    main()