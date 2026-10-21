# stock.py

import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import io
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
import uuid

DB_PATH = "minerva.db"

def conectar():
    return sqlite3.connect(DB_PATH)

def generar_lote(materia_prima_id):
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    unique = uuid.uuid4().hex[:4].upper()
    return f"L{materia_prima_id}_{now}_{unique}"

def obtener_ultimo_precio(cursor, materia_prima_id):
    cursor.execute("""
        SELECT precio_unitario 
        FROM precios_materias_primas 
        WHERE materia_prima_id = ?
        ORDER BY fecha DESC
        LIMIT 1
    """, (materia_prima_id,))
    res = cursor.fetchone()
    return res[0] if res else None

def convertir_a_unidad_base(cantidad, unidad_base):
    unidad_base = unidad_base.lower()
    if unidad_base in ["ml", "cm3"]:
        return cantidad * 1000
    elif unidad_base in ["g", "gramos"]:
        return cantidad * 1000
    else:
        return cantidad

def convertir_desde_unidad_base(cantidad, unidad_base):
    unidad_base = unidad_base.lower()
    if unidad_base in ["ml", "cm3"]:
        return cantidad / 1000, "litros"
    elif unidad_base in ["g", "gramos"]:
        return cantidad / 1000, "kg"
    else:
        return cantidad, unidad_base

def generar_pdf_reporte_stock(datos_stock):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=60, bottomMargin=40)
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph("Reporte de Verificación de Stock de Materias Primas", styles['Title']))
    elements.append(Spacer(1, 12))
    data = [["Materia Prima", "Stock Actual", "Stock Verificado"]]
    for item in datos_stock:
        nombre = item["Materia Prima"]
        cantidad = float(item["Stock Actual"])
        unidad = item["Unidad Base"].lower()
        cantidad_mostrar, unidad_final = convertir_desde_unidad_base(cantidad, unidad)
        data.append([
            nombre,
            f"{cantidad_mostrar:.2f} {unidad_final}",
            "____________________"
        ])
    table = Table(data, colWidths=[200, 100, 150])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('TEXTCOLOR',(0,0),(-1,0),colors.black),
        ('ALIGN',(1,1),(-1,-1),'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 11),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 36))
    elements.append(Paragraph("Observaciones: ____________________________________________", styles['Normal']))
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("Fecha: ______________________", styles['Normal']))
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("Firma responsable: _______________________________", styles['Normal']))
    doc.build(elements)
    buffer.seek(0)
    return buffer

def ver_stock():
    st.header("Stock de Materias Primas")
    conn = conectar()
    cursor = conn.cursor()

    # Cotización dólar
    venta_dolar = None
    try:
        cursor.execute("""
            SELECT venta, fecha_hora 
            FROM cotizacion_dolar
            ORDER BY datetime(fecha_hora) DESC
            LIMIT 1
        """)
        resultado = cursor.fetchone()
        if resultado:
            venta_dolar, fecha = resultado
            st.metric(label="💵 Cotización Dólar (Venta)", value=f"${venta_dolar:.2f}", help=f"Actualizado: {fecha}")
        else:
            st.warning("No hay datos de cotización del dólar.")
    except Exception as e:
        st.error(f"Error al cargar cotización del dólar: {e}")
        return

    st.markdown("---")

    cursor.execute("""
        SELECT mp.id, mp.nombre, mp.unidad, 
               COALESCE(sm.cantidad, 0) as stock_actual
        FROM materias_primas mp
        LEFT JOIN stock_materias_primas sm ON mp.id = sm.materia_prima_id
        ORDER BY mp.nombre
    """)
    rows = cursor.fetchall()

    datos_stock = []
    for row in rows:
        materia_id, nombre, unidad, stock = row
        datos_stock.append({
            "ID": materia_id,
            "Materia Prima": nombre,
            "Unidad Base": unidad.lower(),
            "Cantidad actual": stock,
            "Cantidad ingresada": 0.0,
            "Precio USD": 0.0,
            "Flete USD": 0.0,
            "Otros costos": 0.0,
        })

    df_stock = pd.DataFrame(datos_stock)

    st.subheader("Editar stock y precios")
    df_editado = st.data_editor(
        df_stock,
        num_rows="dynamic",
        use_container_width=True,
        key="data_editor_stock"
    )

    if st.button("Registrar cambios"):
        errores = []
        cambios = []
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for idx, row in df_editado.iterrows():
            mp_id = row["ID"]
            cantidad_actual = row["Cantidad actual"]
            cantidad_ingresada = row["Cantidad ingresada"]
            unidad_base = row["Unidad Base"]

            precio_usd = row["Precio USD"]
            flete_usd = row["Flete USD"]
            otros = row["Otros costos"]

            if cantidad_ingresada != 0:
                nuevo_stock = cantidad_actual + cantidad_ingresada
                if nuevo_stock < 0:
                    errores.append(f"Stock insuficiente para {row['Materia Prima']}.")
                    continue

                tipo = "ingreso" if cantidad_ingresada > 0 else "egreso"
                lote = generar_lote(mp_id)

                # Calcular precios en ARS y por unidad
                precio_total_ars = (precio_usd + flete_usd) * venta_dolar + otros
                try:
                    precio_unitario_final = precio_total_ars / abs(cantidad_ingresada)
                except ZeroDivisionError:
                    precio_unitario_final = 0.0

                if cursor.execute("SELECT cantidad FROM stock_materias_primas WHERE materia_prima_id = ?", (mp_id,)).fetchone():
                    cursor.execute("UPDATE stock_materias_primas SET cantidad = ? WHERE materia_prima_id = ?", (nuevo_stock, mp_id))
                else:
                    cursor.execute("INSERT INTO stock_materias_primas (materia_prima_id, cantidad) VALUES (?, ?)", (mp_id, nuevo_stock))

                cursor.execute("""
                    INSERT INTO movimientos_materia_prima 
                    (materia_prima_id, fecha, cantidad, tipo_movimiento, destino, costo_flete, otros_costos, lote, precio_unitario)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    mp_id, fecha, abs(cantidad_ingresada), tipo, "otro",
                    flete_usd * venta_dolar, otros, lote, precio_unitario_final
                ))

                if tipo == "ingreso" and precio_unitario_final > 0:
                    cursor.execute("""
                        INSERT INTO precios_materias_primas 
                        (materia_prima_id, precio_unitario, fecha, costo_flete, otros_costos)
                        VALUES (?, ?, ?, ?, ?)
                    """, (mp_id, precio_unitario_final, fecha, flete_usd * venta_dolar, otros))

                cambios.append(f"{row['Materia Prima']}: {tipo} {abs(cantidad_ingresada):.3f} {unidad_base}")

        if errores:
            st.error("Errores encontrados:")
            for e in errores:
                st.error(f"- {e}")

        if cambios:
            conn.commit()
            st.success("Cambios registrados:")
            for c in cambios:
                st.write(f"- {c}")
        elif not errores:
            st.info("No hubo cambios.")

    st.markdown("---")
    st.subheader("📄 Descargar reporte PDF de stock")

    datos_reporte = []
    for _, row in df_stock.iterrows():
        cantidad_mostrar, unidad = convertir_desde_unidad_base(row["Cantidad actual"], row["Unidad Base"])
        datos_reporte.append({
            "Materia Prima": row["Materia Prima"],
            "Stock Actual": cantidad_mostrar,
            "Unidad Base": unidad
        })

    pdf = generar_pdf_reporte_stock(datos_reporte)
    st.download_button("Descargar PDF", data=pdf, file_name="reporte_stock.pdf", mime="application/pdf")

    st.markdown("---")
    st.subheader("Registrar salida de materia prima")

    materias = {f"{row['Materia Prima']} (ID {row['ID']})": row for _, row in df_stock.iterrows()}

    with st.form("form_egreso"):
        materia_seleccionada = st.selectbox("Materia prima", options=list(materias.keys()))
        cantidad_egreso = st.number_input("Cantidad a egresar", min_value=0.0, step=0.01, format="%.3f")
        destino_egreso = st.selectbox("Destino", options=["Laboratorio", "Otro"])
        enviar = st.form_submit_button("Registrar salida")

        if enviar:
            item = materias[materia_seleccionada]
            mp_id = item["ID"]
            stock_actual = item["Cantidad actual"]
            unidad_base = item["Unidad Base"]

            if cantidad_egreso <= 0:
                st.error("Ingrese una cantidad válida.")
            elif cantidad_egreso > stock_actual:
                st.error(f"No hay suficiente stock. Disponible: {stock_actual:.3f}")
            else:
                nuevo_stock = stock_actual - cantidad_egreso
                lote = generar_lote(mp_id)
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                cursor.execute("UPDATE stock_materias_primas SET cantidad = ? WHERE materia_prima_id = ?", (nuevo_stock, mp_id))
                cursor.execute("""
                    INSERT INTO movimientos_materia_prima 
                    (materia_prima_id, fecha, cantidad, tipo_movimiento, destino, costo_flete, otros_costos, lote, precio_unitario)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    mp_id, fecha, cantidad_egreso, "egreso", destino_egreso.lower(), 0.0, 0.0, lote, 0.0
                ))

                conn.commit()
                st.success(f"Salida registrada. Nuevo stock: {nuevo_stock:.3f} {unidad_base}")

    conn.close()

# Control de acceso
if "usuario" not in st.session_state:
    st.error("Acceso denegado. Inicie sesión.")
elif st.session_state.usuario["rol"] != "Administrador":
    st.error("Acceso restringido. Solo para Administradores.")
else:
    ver_stock()
