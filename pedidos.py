import streamlit as st
import sqlite3
from datetime import date
import pandas as pd
import math

def gestionar_pedidos():
    st.header("Gestión de Pedidos de Producción")

    conn = sqlite3.connect("minerva.db")
    cursor = conn.cursor()

    # Obtener clientes, recetas y envases
    cursor.execute("SELECT id, nombre FROM clientes ORDER BY nombre")
    clientes = cursor.fetchall()
    cursor.execute("SELECT id, nombre FROM recetas ORDER BY nombre")
    recetas = cursor.fetchall()
    cursor.execute("SELECT id, descripcion, capacidad_litros FROM envases ORDER BY descripcion")
    envases_desc = cursor.fetchall()

    if not clientes or not recetas:
        st.warning("Debe haber al menos un cliente y una receta registrada para cargar pedidos.")
        cursor.close()
        conn.close()
        return

    cliente_dict = {c[1]: c[0] for c in clientes}
    receta_dict = {r[1]: {'id': r[0]} for r in recetas}
    envase_dict = {e[1]: {'id': e[0], 'capacidad': e[2]} for e in envases_desc}
    envase_nombres = [""] + list(envase_dict.keys())

    st.subheader("Nuevo Pedido")
    cliente_nombre = st.selectbox("Cliente", [c[1] for c in clientes])
    receta_nombre = st.selectbox("Producto (Receta)", [r[1] for r in recetas])
    envase_nombre = st.selectbox("Envase", envase_nombres)

    numero_pedido = st.text_input("Número de Pedido (manual)")

    # 🔄 Reiniciar estado si cambia el número de pedido
    if "last_pedido_numero" not in st.session_state:
        st.session_state.last_pedido_numero = ""

    if numero_pedido != st.session_state.last_pedido_numero:
        st.session_state.pedido_guardado = False
        st.session_state.last_pedido_numero = numero_pedido

    fecha_pedido = st.date_input("Fecha del Pedido", value=date.today())
    divisiones_str = st.text_input("División del pedido (ej: 2x200,1x100)")

    divisiones = []
    if divisiones_str:
        try:
            partes = [p.strip() for p in divisiones_str.split(',')]
            for parte in partes:
                n, x = parte.lower().split('x')
                divisiones.extend([float(x)] * int(n))
        except Exception:
            st.error("Formato incorrecto. Use el formato: 2x200,1x100 para representar cantidades divididas.")
            cursor.close()
            conn.close()
            return

    if not divisiones or not receta_nombre:
        st.warning("Ingrese divisiones válidas y seleccione un producto.")
        cursor.close()
        conn.close()
        return

    receta_id = next(r[0] for r in recetas if r[1] == receta_nombre)

    # -------------------------------------------------------
    # 🔵 Selección de MODO DE PRODUCCIÓN
    # -------------------------------------------------------
    modo_produccion = st.radio(
        "Modo de cálculo:",
        ["Por cantidad de producciones (batch real)", "Escalado por litros finales"],
        horizontal=True
    )

    # Obtener ingredientes originales de la receta
    cursor.execute("""
        SELECT mp.id, mp.nombre, mp.unidad, ri.cantidad
        FROM receta_ingredientes ri
        JOIN materias_primas mp ON ri.materia_prima_id = mp.id
        WHERE ri.receta_id = ?
    """, (receta_id,))
    ingredientes = cursor.fetchall()

    # Calcular litros totales de la receta original
    batch_total = 0
    for _, _, unidad, cantidad_base in ingredientes:
        if unidad.upper() in ["CM3", "G"]:
            batch_total += cantidad_base / 1000.0
        else:
            batch_total += cantidad_base

    # -------------------------------------------------------
    # 🔵 MODO A: Por cantidad de producciones (batch real)
    # -------------------------------------------------------
    pedidos_a_mostrar = []

    if modo_produccion == "Por cantidad de producciones (batch real)":
        cantidad_producciones = st.number_input(
            "Cantidad de producciones completas (batch):",
            min_value=1, step=1
        )
        for i in range(int(cantidad_producciones)):
            factor_batch = 1  # Cada producción completa
            cantidad_final_litros = batch_total

            # Calculo de ingredientes para esta producción
            detalle_final = []
            costo_total_ingredientes = 0.0
            for ingr_id, ingr_nombre, unidad, cantidad_base in ingredientes:
                cantidad_final = cantidad_base * factor_batch
                if unidad.upper() in ["CM3", "G"]:
                    cantidad_convertida = cantidad_final / 1000
                else:
                    cantidad_convertida = cantidad_final
                cursor.execute("""
                    SELECT precio_unitario FROM compras_materia_prima
                    WHERE materia_prima_id = ?
                    ORDER BY fecha DESC, id DESC LIMIT 1
                """, (ingr_id,))
                res = cursor.fetchone()
                precio_unitario = res[0] if res else 0.0
                costo_total = cantidad_convertida * precio_unitario
                costo_total_ingredientes += costo_total

                detalle_final.append({
                    "Ingrediente": ingr_nombre,
                    "Unidad": unidad,
                    "Cantidad Final": f"{cantidad_final:.3f}",
                    "Precio Unitario USD": f"{precio_unitario:.4f}",
                    "Costo Total USD": f"{costo_total:.2f}"
                })

            # Costo de envases
            costo_total_envases = 0.0
            num_envases = 0
            envase_id_local = None
            if envase_nombre:
                envase_info = envase_dict.get(envase_nombre)
                envase_id_local = envase_info['id']
                envase_capacidad = envase_info['capacidad']
                num_envases = math.ceil(cantidad_final_litros / envase_capacidad)
                cursor.execute(
                    "SELECT precio_unitario FROM entradas_envases WHERE envase_id = ? ORDER BY id DESC LIMIT 1",
                    (envase_id_local,)
                )
                res = cursor.fetchone()
                costo_envase_unitario = res[0] if res else 0.0
                costo_total_envases = num_envases * costo_envase_unitario

            pedidos_a_mostrar.append({
                "factor": factor_batch,
                "litros": cantidad_final_litros,
                "detalle_final": detalle_final,
                "costo_ingredientes": costo_total_ingredientes,
                "costo_envases": costo_total_envases
            })

    # -------------------------------------------------------
    # 🟢 MODO B: Escalado por litros finales
    # -------------------------------------------------------
    else:
        cantidad_final_litros = st.number_input(
            "Litros finales deseados:",
            min_value=1.0, step=1.0
        )
        factor_batch = cantidad_final_litros / batch_total
        detalle_final = []
        costo_total_ingredientes = 0.0
        for ingr_id, ingr_nombre, unidad, cantidad_base in ingredientes:
            cantidad_final = cantidad_base * factor_batch
            if unidad.upper() in ["CM3", "G"]:
                cantidad_convertida = cantidad_final / 1000
            else:
                cantidad_convertida = cantidad_final
            cursor.execute("""
                SELECT precio_unitario FROM compras_materia_prima
                WHERE materia_prima_id = ?
                ORDER BY fecha DESC, id DESC LIMIT 1
            """, (ingr_id,))
            res = cursor.fetchone()
            precio_unitario = res[0] if res else 0.0
            costo_total = cantidad_convertida * precio_unitario
            costo_total_ingredientes += costo_total
            detalle_final.append({
                "Ingrediente": ingr_nombre,
                "Unidad": unidad,
                "Cantidad Final": f"{cantidad_final:.3f}",
                "Precio Unitario USD": f"{precio_unitario:.4f}",
                "Costo Total USD": f"{costo_total:.2f}"
            })
        pedidos_a_mostrar.append({
            "factor": factor_batch,
            "litros": cantidad_final_litros,
            "detalle_final": detalle_final,
            "costo_ingredientes": costo_total_ingredientes,
            "costo_envases": 0.0  # envases calculados después
        })

    # -------------------------------------------------------
    # Mostrar cada pedido antes de guardar
    # -------------------------------------------------------
    for idx, pedido in enumerate(pedidos_a_mostrar, 1):
        st.subheader(f"Pedido {idx}")
        st.dataframe(pd.DataFrame(pedido["detalle_final"]), use_container_width=True)
        st.info(f"Costo ingredientes: ${pedido['costo_ingredientes']:.2f}")
        st.info(f"Costo envases: ${pedido['costo_envases']:.2f}")
        st.success(f"Costo total: ${pedido['costo_ingredientes'] + pedido['costo_envases']:.2f} USD")

    # -------------------------------------------------------
    # Guardar pedidos
    # -------------------------------------------------------
    if st.button("Registrar Pedido(s)"):
        if not numero_pedido or not pedidos_a_mostrar:
            st.warning("Complete todos los campos correctamente.")
        else:
            cliente_id = cliente_dict[cliente_nombre]
            try:
                for idx, pedido in enumerate(pedidos_a_mostrar, 1):
                    numero_parcial = f"{numero_pedido}-{idx}" if len(pedidos_a_mostrar) > 1 else numero_pedido
                    cursor.execute("""
                        INSERT INTO pedidos_produccion (cliente_id, receta_id, fecha, numero_pedido, cantidad, estado)
                        VALUES (?, ?, ?, ?, ?, 'pendiente')
                    """, (cliente_id, receta_id, fecha_pedido.strftime("%Y-%m-%d"), numero_parcial, pedido["litros"]))

                conn.commit()
                st.success(f"{len(pedidos_a_mostrar)} pedido(s) registrado(s) correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al registrar pedido(s): {e}")

    # -------------------------------------------------------
    # Pedidos registrados (igual que antes)
    # -------------------------------------------------------
    st.subheader("Pedidos Registrados")
    estado_filtro = st.selectbox(
        "Filtrar por estado:",
        options=["Todos", "Pendiente", "Producido", "Anulado"],
        index=0
    )
    estado_map = {"Pendiente": "pendiente", "Producido": "producido", "Anulado": "anulado"}
    filtro_sql = ""
    params = ()
    if estado_filtro != "Todos":
        filtro_sql = "WHERE p.estado = ?"
        params = (estado_map[estado_filtro],)

    if "anular_id" in st.session_state:
        pedido_id = st.session_state.anular_id
        cursor.execute("UPDATE pedidos_produccion SET estado = 'anulado' WHERE id = ?", (pedido_id,))
        conn.commit()
        st.success(f"Pedido {pedido_id} anulado correctamente.")
        del st.session_state.anular_id
        st.rerun()

    cursor.execute(f"""
        SELECT 
            p.id, c.nombre, r.nombre, p.cantidad, p.numero_pedido, p.fecha, p.estado, p.receta_id
        FROM pedidos_produccion p
        JOIN clientes c ON p.cliente_id = c.id
        JOIN recetas r ON p.receta_id = r.id
        {filtro_sql}
        ORDER BY p.fecha DESC
    """, params)
    pedidos = cursor.fetchall()

    if pedidos:
        for pedido in pedidos:
            pid, cliente, producto, cantidad, numero, fecha, estado, receta_id = pedido
            estado_display = {"pendiente": "🟡 Pendiente", "producido": "🟢 Producido", "anulado": "🔴 Anulado"}.get(estado, estado)
            st.markdown(f"""
            - **Número de Pedido**: {numero}
            - **Cliente**: {cliente}
            - **Producto**: {producto}
            - **Cantidad**: {cantidad:.2f} L
            - **Fecha**: {fecha}
            - **Estado**: {estado_display}
            """)
            if st.button(f"Anular Pedido {numero}", key=pid):
                st.session_state.anular_id = pid
                st.experimental_rerun()

    else:
        st.warning("No hay pedidos registrados en la base de datos.")

    cursor.close()
    conn.close()
