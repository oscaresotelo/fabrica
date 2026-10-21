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
    # CORREGIDO: Se reemplazó 'capacidad' por 'capacidad_litros'
    cursor.execute("SELECT id, descripcion, capacidad_litros FROM envases ORDER BY descripcion")
    envases_desc = cursor.fetchall()

    if not clientes or not recetas:
        st.warning("Debe haber al menos un cliente y una receta registrada para cargar pedidos.")
        cursor.close()
        conn.close()
        return

    # Crear diccionarios para un acceso más rápido a los datos
    cliente_dict = {c[1]: c[0] for c in clientes}
    receta_dict = {r[1]: {'id': r[0]} for r in recetas}
    # Se actualiza el diccionario de envases para incluir la capacidad
    envase_dict = {e[1]: {'id': e[0], 'capacidad': e[2]} for e in envases_desc}
    envase_nombres = [""] + list(envase_dict.keys())

    # Formulario para nuevo pedido
    st.subheader("Nuevo Pedido")
    cliente_nombre = st.selectbox("Cliente", [c[1] for c in clientes])
    receta_nombre = st.selectbox("Producto (Receta)", [r[1] for r in recetas])
    envase_nombre = st.selectbox("Envase", envase_nombres)

    numero_pedido = st.text_input("Número de Pedido (manual)")
    fecha_pedido = st.date_input("Fecha del Pedido", value=date.today())
    divisiones_str = st.text_input("División del pedido (ej: 2x200,1x100)")

    # Parseo de divisiones
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

    # Simulación de costeo
    costo_total_pedido = 0.0
    costo_total_ingredientes = 0.0

    if divisiones and receta_nombre:
        receta_id = next(r[0] for r in recetas if r[1] == receta_nombre)

        # Cálculo del costo total de envases
        costo_total_envases = 0.0
        num_envases = 0
        envase_id = None
        if envase_nombre:
            envase_info = envase_dict.get(envase_nombre)
            envase_id = envase_info['id']
            envase_capacidad = envase_info['capacidad']

            # Sumar el volumen total de la producción
            total_volumen = sum(divisiones)

            # Calcular el número de envases
            num_envases = math.ceil(total_volumen / envase_capacidad)

            # Obtener el costo unitario del envase
            cursor.execute(
                "SELECT precio_unitario FROM entradas_envases WHERE envase_id = ? ORDER BY id DESC LIMIT 1",
                (envase_id,)
            )
            res = cursor.fetchone()
            costo_envase_unitario = res[0] if res else 0.0

            # Calcular el costo total de todos los envases
            costo_total_envases = num_envases * costo_envase_unitario

        cursor.execute("""
            SELECT mp.id, mp.nombre, mp.unidad, ri.cantidad
            FROM receta_ingredientes ri
            JOIN materias_primas mp ON ri.materia_prima_id = mp.id
            WHERE ri.receta_id = ?
        """, (receta_id,))
        ingredientes = cursor.fetchall()

        st.subheader("Detalle de Costeo por División")

        for i, cantidad in enumerate(divisiones, 1):
            st.markdown(f"#### División {i}: {cantidad} litros")
            detalle_costeo = []
            subtotal = 0.0
            for ingr_id, ingr_nombre, unidad, cantidad_base in ingredientes:
                cantidad_escalada = (cantidad / 200) * cantidad_base

                if unidad.upper() in ["CM3", "G"]:
                    cantidad_convertida = cantidad_escalada / 1000
                else:
                    cantidad_convertida = cantidad_escalada

                cursor.execute("""
                    SELECT precio_unitario FROM precios_materias_primas
                    WHERE materia_prima_id = ?
                    ORDER BY fecha DESC LIMIT 1
                """, (ingr_id,))
                res = cursor.fetchone()
                precio_unitario = res[0] if res else 0.0
                costo = cantidad_convertida * precio_unitario
                subtotal += costo

                detalle_costeo.append({
                    "Ingrediente": ingr_nombre,
                    "Cantidad usada": f"{cantidad_escalada:.3f} {unidad}",
                    "Precio unitario": f"${precio_unitario:,.4f}",
                    "Costo total": f"${costo:,.2f}"
                })

            st.dataframe(pd.DataFrame(detalle_costeo), use_container_width=True)
            st.info(f"Costo de Ingredientes para esta división: ${subtotal:,.2f}")
            costo_total_ingredientes += subtotal

        # Se muestra el costo total de los envases y el total del pedido
        st.markdown("### Resumen de Costos")
        st.info(f"Costo Total de Ingredientes: ${costo_total_ingredientes:,.2f}")
        st.info(f"Costo Total de Envases ({num_envases} unidades, ID: {envase_id if envase_id else 'N/A'}): ${costo_total_envases:,.2f}")

        costo_total_pedido = costo_total_ingredientes + costo_total_envases
        st.success(f"Costo total estimado del pedido: ${costo_total_pedido:,.2f}")

    if "pedido_guardado" not in st.session_state:
        st.session_state.pedido_guardado = False

    if st.button("Registrar Pedido(s)"):
        if not numero_pedido or not divisiones:
            st.warning("Complete todos los campos correctamente y asegúrese de ingresar divisiones válidas.")
        elif not st.session_state.pedido_guardado:
            cliente_id = cliente_dict[cliente_nombre]
            receta_id = receta_dict[receta_nombre]['id']
            # el envase_id no se guarda, ya que la columna no existe en pedidos_produccion
            # envase_id = envase_dict.get(envase_nombre)

            try:
                for i, cantidad in enumerate(divisiones, 1):
                    numero_parcial = f"{numero_pedido}-{i}" if len(divisiones) > 1 else numero_pedido

                    cursor.execute("""
                        INSERT INTO pedidos_produccion (cliente_id, receta_id, fecha, numero_pedido, cantidad, estado)
                        VALUES (?, ?, ?, ?, ?, 'pendiente')
                    """, (cliente_id, receta_id, fecha_pedido.strftime("%Y-%m-%d"), numero_parcial, cantidad))

                conn.commit()
                st.session_state.pedido_guardado = True
                st.success(f"{len(divisiones)} pedido(s) registrado(s) correctamente.")
                cursor.close()
                conn.close()
                st.rerun()
            except Exception as e:
                st.error(f"Error al registrar pedido(s): {e}")

    # ------------------------------------------
    # Filtro por estado de pedido
    # ------------------------------------------
    st.subheader("Pedidos Registrados")

    estado_filtro = st.selectbox(
        "Filtrar por estado:",
        options=["Todos", "Pendiente", "Producido", "Anulado"],
        index=0
    )

    estado_map = {
        "Pendiente": "pendiente",
        "Producido": "producido",
        "Anulado": "anulado"
    }

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
            p.id, 
            c.nombre, 
            r.nombre, 
            p.cantidad, 
            p.numero_pedido, 
            p.fecha, 
            p.estado,
            p.receta_id
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

            estado_display = {
                "pendiente": "🟡 Pendiente",
                "producido": "🟢 Producido",
                "anulado": "🔴 Anulado"
            }.get(estado, estado)

            subtotal_ingredientes = 0.0
            cursor.execute("""
                SELECT mp.id, mp.unidad, ri.cantidad
                FROM receta_ingredientes ri
                JOIN materias_primas mp ON ri.materia_prima_id = mp.id
                WHERE ri.receta_id = ?
            """, (receta_id,))
            ingredientes_pedido = cursor.fetchall()

            for ingr_id, unidad, cantidad_base in ingredientes_pedido:
                cantidad_escalada = (cantidad / 200) * cantidad_base

                cursor.execute("""
                    SELECT precio_unitario FROM precios_materias_primas
                    WHERE materia_prima_id = ?
                    ORDER BY fecha DESC LIMIT 1
                """, (ingr_id,))
                res = cursor.fetchone()
                precio_unitario = res[0] if res else 0.0

                if unidad.upper() in ["CM3", "G"]:
                    cantidad_convertida = cantidad_escalada / 1000
                else:
                    cantidad_convertida = cantidad_escalada

                subtotal_ingredientes += cantidad_convertida * precio_unitario

            costo_total = subtotal_ingredientes

            cols = st.columns([8, 1])
            with cols[0]:
                st.markdown(
                    f"**N° Pedido:** {numero} | "
                    f"**Cliente:** {cliente} | "
                    f"**Producto:** {producto} | "
                    f"**Cantidad:** {cantidad} | "
                    f"**Fecha:** {pd.to_datetime(fecha).strftime('%d/%m/%Y')} | "
                    f"**Estado:** {estado_display} | "
                    f"**Costo Total:** ${costo_total:,.2f} *(solo ingredientes)*"
                )
            with cols[1]:
                if estado == "pendiente":
                    if st.button("Anular", key=f"anular_{pid}"):
                        st.session_state.anular_id = pid
                        st.rerun()
    else:
        st.info("No hay pedidos registrados.")

    cursor.close()
    conn.close()