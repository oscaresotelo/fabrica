import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date # <- MODIFICADO: Se agrega 'date'
import time

def envasar():
    DB_PATH = "minerva.db"

    def get_connection():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def fetch_data(query, params=()):
        conn = get_connection()
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df

    # --- FUNCIÓN ELIMINADA / INTEGRADA ---
    # La lógica de agregar stock de productos envasados se mueve al bloque 'Confirmar Producción'
    
    st.title("🏭 Producción de Envasado (Cajas Acumulativas)")

    # --- Órdenes Pendientes ---
    with st.expander("📦 Órdenes de Envasado Pendientes", expanded=True):
        ordenes_query = """
        SELECT
            oe.id,
            oe.fecha,
            c.nombre AS cliente,
            pr.nombre AS producto,
            e.descripcion AS envase,
            oe.cantidad_unidades,
            oe.estado,
            oe.produccion_id,
            oe.envase_id,
            oe.producto_cliente_id,
            pp.cliente_id,
            pp.receta_id,
            p.lote,
            pc.producto_id
        FROM ordenes_envasado oe
        JOIN producciones p ON oe.produccion_id = p.id
        JOIN pedidos_produccion pp ON p.pedido_id = pp.id
        JOIN clientes c ON pp.cliente_id = c.id
        JOIN recetas r ON pp.receta_id = r.id
        JOIN envases e ON oe.envase_id = e.id
        JOIN productos_clientes pc ON oe.producto_cliente_id = pc.id
        JOIN productos pr ON pc.producto_id = pr.id
        WHERE oe.estado = 'pendiente'
        ORDER BY oe.fecha ASC, oe.id ASC;
        """
        df_ordenes_raw = fetch_data(ordenes_query)

        if df_ordenes_raw.empty:
            st.info("✅ No hay órdenes de envasado pendientes.")
        else:
            st.subheader("Órdenes y cálculo acumulado de cajas")
            saldos_cajas = {}
            tabla_resultados = []
            orden_map = {}

            for idx, row in df_ordenes_raw.iterrows():
                producto_id_general = row["producto_id"]
                envase_id = row["envase_id"]
                key = (producto_id_general, envase_id)

                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT multiplicador_unidades_base, nombre_presentacion
                    FROM producto_presentaciones
                    WHERE producto_id = ? AND envase_base_id = ?
                    ORDER BY orden_jerarquico ASC
                    LIMIT 1
                """, (producto_id_general, envase_id))
                presentacion = cursor.fetchone()
                conn.close()

                if presentacion:
                    multiplicador = presentacion["multiplicador_unidades_base"]
                    nombre_presentacion = presentacion["nombre_presentacion"]
                else:
                    multiplicador = 1
                    nombre_presentacion = "Unidad"

                saldo_anterior = saldos_cajas.get(key, 0)
                acumulado = saldo_anterior + row["cantidad_unidades"]
                cajas_completas = acumulado // multiplicador
                saldo_restante = acumulado % multiplicador

                tabla_resultados.append({
                    "Orden": row["id"],
                    "Fecha": row["fecha"],
                    "Cliente": row["cliente"],
                    "Producto": row["producto"],
                    "Envase": row["envase"],
                    "Unidades en orden": row["cantidad_unidades"],
                    "Presentación": nombre_presentacion,
                    "Unidades por caja": multiplicador,
                    "Cajas completas acumuladas": int(cajas_completas),
                    "Unidades pendientes para próxima caja": int(saldo_restante)
                })

                orden_map[f"Orden #{row['id']} - {row['cliente']} - {row['producto']} ({row['envase']}) - {row['cantidad_unidades']} unidades"] = row
                saldos_cajas[key] = saldo_restante

            st.dataframe(pd.DataFrame(tabla_resultados))

            st.markdown("""
            - **Cajas completas acumuladas**: suma las unidades de la orden actual y las anteriores (del mismo producto y envase) y muestra cuántas cajas completas se pueden armar.
            - **Unidades pendientes para próxima caja**: lo que falta para completar la próxima caja, que se sumará a la siguiente orden.
            """)

            st.subheader("Seleccionar Orden para Confirmar Envasado")
            if not orden_map:
                st.info("No hay órdenes disponibles para seleccionar después de aplicar los filtros.")
                return

            selected_key = st.selectbox("Seleccione una orden para producir:", list(orden_map.keys()))
            selected = orden_map[selected_key]

            st.markdown("### 🧾 Detalles de la Orden")
            st.write(f"**Cliente:** {selected['cliente']}")
            st.write(f"**Producto:** {selected['producto']}")
            st.write(f"**Envase:** {selected['envase']}")
            st.write(f"**Cantidad:** {selected['cantidad_unidades']}")
            st.write(f"**Fecha:** {selected['fecha']}")
            st.write(f"**Lote Producción:** {selected['lote']}")

            producto_id_general = selected["producto_id"]
            envase_id = selected["envase_id"]
            cantidad_unidades = selected["cantidad_unidades"]

            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT multiplicador_unidades_base, nombre_presentacion
                FROM producto_presentaciones
                WHERE producto_id = ? AND envase_base_id = ?
                ORDER BY orden_jerarquico ASC
                LIMIT 1
            """, (producto_id_general, envase_id))
            presentacion = cursor.fetchone()
            conn.close()

            if presentacion:
                multiplicador = presentacion["multiplicador_unidades_base"]
                nombre_presentacion = presentacion["nombre_presentacion"]
            else:
                multiplicador = 1
                nombre_presentacion = "Unidad"

            cantidad_cajas = cantidad_unidades / multiplicador

            st.write(f"**Presentación:** {nombre_presentacion}")
            st.write(f"**Cajas necesarias (solo esta orden):** {cantidad_cajas:.2f}")
            
            # --- NUEVO: Selector de Fecha de Envasado ---
            fecha_envasado_input = st.date_input(
                "📅 Seleccionar Fecha de Envasado", 
                value=date.today(), 
                key=f"fecha_envasado_input_{selected['id']}"
            )
            # --- FIN NUEVO ---

            st.markdown("---")
            st.subheader("Stock de Envases Vacíos Disponibles")

            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT cantidad FROM stock_envases_clientes
                WHERE cliente_id = ? AND envase_id = ?
            """, (selected["cliente_id"], envase_id))
            stock_row = cursor.fetchone()
            conn.close()

            disponible = stock_row["cantidad"] if stock_row else 0
            st.write(f"**Stock de envases disponible:** {disponible}")

            if disponible == 0:
                st.info("No hay stock de envases para esta combinación. Si necesita reponer, registre una nueva compra.")
            else:
                if disponible < cantidad_unidades:
                    st.warning(f"Solo hay {disponible} envases disponibles. Puede envasar una cantidad menor.")
                    cantidad_a_envasar = st.number_input(
                        "Cantidad a envasar", min_value=1, max_value=disponible, value=disponible, step=1
                    )
                else:
                    cantidad_a_envasar = cantidad_unidades

                # ========== BLOQUE DE CAJAS ==========
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, descripcion, unidades_por_caja
                    FROM tipo_cajas
                    WHERE producto = ?
                    LIMIT 1
                """, (selected["producto"],))
                caja_row = cursor.fetchone()
                conn.close()

                if caja_row:
                    tipo_caja_id, tipo_caja_desc, unidades_por_caja = caja_row["id"], caja_row["descripcion"], caja_row["unidades_por_caja"]
                    cajas_necesarias = (cantidad_a_envasar + unidades_por_caja - 1) // unidades_por_caja
                else:
                    tipo_caja_id, tipo_caja_desc, unidades_por_caja, cajas_necesarias = None, "Sin caja definida", 1, 0

                stock_cajas_actual = 0
                if tipo_caja_id:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT cantidad_actual FROM stock_cajas WHERE tipo_caja_id = ?", (tipo_caja_id,))
                    stock_cajas_row = cursor.fetchone()
                    conn.close()
                    stock_cajas_actual = stock_cajas_row["cantidad_actual"] if stock_cajas_row else 0

                st.write(f"**Stock de cajas de este tipo disponible:** {stock_cajas_actual} (se necesitarán {cajas_necesarias})")
                if stock_cajas_actual < cajas_necesarias:
                    st.warning("⚠️ Atención: No hay cajas suficientes en stock. El sistema le permitirá envasar igual, pero registre reposición a la brevedad.")

                # ========== CONFIRMACIÓN E INTEGRACIÓN CAJAS ==========
                if st.button("✅ Confirmar Producción de Envasado"):
                    try:
                        conn = get_connection()
                        cursor = conn.cursor()

                        orden_id = selected["id"]
                        cliente_id = selected["cliente_id"]
                        receta_id = selected["receta_id"]
                        lote = selected["lote"] if selected["lote"] else f"L{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        cantidad_envases = cantidad_a_envasar

                        # Formatear la fecha seleccionada con la hora actual
                        fecha_envasado_dt = datetime.combine(fecha_envasado_input, datetime.now().time())
                        fecha_str = fecha_envasado_dt.strftime("%Y-%m-%d %H:%M:%S")
                        fecha_iso = fecha_envasado_dt.isoformat()
                        
                        # INICIO DE TRANSACCIÓN ATÓMICA
                        cursor.execute("BEGIN;")

                        # ---- Envases (Egreso) ----
                        cursor.execute("""
                            UPDATE stock_envases_clientes
                            SET cantidad = cantidad - ?
                            WHERE cliente_id = ? AND envase_id = ?
                        """, (cantidad_envases, cliente_id, envase_id))

                        # ---- Cajas (Egreso) ----
                        if tipo_caja_id:
                            cursor.execute("""
                                UPDATE stock_cajas
                                SET cantidad_actual = cantidad_actual - ?
                                WHERE tipo_caja_id = ?
                            """, (cajas_necesarias, tipo_caja_id))
                            cursor.execute("""
                                INSERT INTO movimientos_cajas
                                (fecha, tipo_caja, cantidad, tipo_movimiento, orden_envasado_id, observacion)
                                VALUES (?, ?, ?, 'Egreso', ?, ?)
                            """, (
                                fecha_str, # <- MODIFICADO: Usa la fecha/hora seleccionada
                                tipo_caja_desc,
                                cajas_necesarias,
                                orden_id,
                                f"Egreso de cajas por envasado de orden {orden_id} en fecha {fecha_envasado_input.isoformat()}"
                            ))

                        # ---- Estado y Fecha de Envasado de la Orden (CLAVE) ----
                        cursor.execute("UPDATE ordenes_envasado SET estado = 'envasado', fecha_envasado = ? WHERE id = ?", (fecha_str, orden_id,)) # <- MODIFICADO: Agrega fecha_envasado

                        # ---- Movimiento envases (Egreso) ----
                        observacion_envases = f"Consumo de envases para Orden {orden_id} - Cliente {selected['cliente']} - Producto {selected['producto']}"
                        cursor.execute("""
                            INSERT INTO movimientos_envases (envase_id, fecha, cantidad, tipo_movimiento, observacion)
                            VALUES (?, ?, ?, ?, ?)
                        """, (envase_id, fecha_iso, cantidad_envases, "Egreso", observacion_envases)) # <- MODIFICADO: Usa la fecha/hora seleccionada
                        
                        # ---- REGISTRO DE STOCK DE PRODUCTOS ENVASADOS (INTEGRADO AQUÍ) ----
                        fecha_ingreso = fecha_str # <- MODIFICADO: Usa la fecha/hora seleccionada
                        cursor.execute("""
                            INSERT INTO stock_productos_envasados (cliente_id, receta_id, envase_id, lote, cantidad, fecha_ingreso)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (cliente_id, receta_id, envase_id, lote, cantidad_envases, fecha_ingreso))

                        # COMMIT FINAL DE LA TRANSACCIÓN ATÓMICA
                        conn.commit()

                        st.success(f"🎉 Orden marcada como envasada en {fecha_envasado_input.isoformat()}, stock de envases y cajas actualizado y trazabilidad registrada. Se descontaron {cajas_necesarias} cajas.")
                        time.sleep(3)
                        st.rerun()

                    except Exception as e:
                        conn.rollback() # Si algo falla, se revierte todo.
                        st.error(f"Error al procesar la producción: {e}")
                    finally:
                        conn.close()
    # --- Órdenes Realizadas (Historial) ---
    with st.expander("📦 Órdenes de Envasado Realizadas", expanded=False):
        ordenes_realizadas_query = """
        SELECT
            oe.id,
            oe.fecha AS fecha_creacion,
            oe.fecha_envasado, -- <- MODIFICADO: Se agrega el campo fecha_envasado
            c.nombre AS cliente,
            pr.nombre AS producto,
            e.descripcion AS envase,
            oe.cantidad_unidades,
            oe.estado,
            p.lote
        FROM ordenes_envasado oe
        JOIN producciones p ON oe.produccion_id = p.id
        JOIN pedidos_produccion pp ON p.pedido_id = pp.id
        JOIN clientes c ON pp.cliente_id = c.id
        JOIN recetas r ON pp.receta_id = r.id
        JOIN envases e ON oe.envase_id = e.id
        JOIN productos_clientes pc ON oe.producto_cliente_id = pc.id
        JOIN productos pr ON pc.producto_id = pr.id
        WHERE oe.estado = 'envasado'
        ORDER BY oe.fecha DESC, oe.id DESC;
        """
        df_realizadas = fetch_data(ordenes_realizadas_query)
        if df_realizadas.empty:
            st.info("No hay órdenes de envasado realizadas.")
        else:
            st.dataframe(df_realizadas)
# Llamar a la función principal para ejecutar la aplicación
if __name__ == "__main__":
    envasar()