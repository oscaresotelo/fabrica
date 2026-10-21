import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import math
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from io import BytesIO

# --- Funciones de consulta a la base de datos ---
def get_recetas():
    conn = sqlite3.connect('minerva.db')
    query = "SELECT id, nombre FROM recetas"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_envases():
    conn = sqlite3.connect('minerva.db')
    query = "SELECT id, descripcion, capacidad_litros FROM envases" # Incluir capacidad_litros
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_ultimo_precio_materia_prima(materia_prima_id, fecha_presupuesto):
    conn = sqlite3.connect('minerva.db')
    query = f"""
        SELECT precio_unitario
        FROM precios_materias_primas
        WHERE materia_prima_id = {materia_prima_id}
          AND fecha <= '{fecha_presupuesto}'
        ORDER BY fecha DESC
        LIMIT 1
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    if not df.empty:
        return df['precio_unitario'][0]
    else:
        return None

def get_ingredientes_receta(receta_id):
    conn = sqlite3.connect('minerva.db')
    query = f"""
        SELECT ri.materia_prima_id, mp.nombre, ri.cantidad, ri.unidad
        FROM receta_ingredientes ri
        JOIN materias_primas mp ON ri.materia_prima_id = mp.id
        WHERE ri.receta_id = {receta_id}
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_ultimo_precio_envase(envase_id, fecha_presupuesto):
    conn = sqlite3.connect('minerva.db')
    query = f"""
        SELECT precio_unitario
        FROM entradas_envases
        WHERE envase_id = {envase_id}
        AND fecha_ingreso <= '{fecha_presupuesto}'
        ORDER BY fecha_ingreso DESC
        LIMIT 1
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    if not df.empty:
        return df['precio_unitario'][0]
    else:
        return None

# --- Interfaz Streamlit ---
st.title('Calculador de Presupuestos')

# 0. Valor del dolar
valor_dolar = st.number_input('Ingrese el valor del Dólar (ARS):', min_value=0.0, value=1300.0)

# 1. Selección de receta
recetas_df = get_recetas()
if recetas_df is not None and not recetas_df.empty:
    receta_seleccionada = st.selectbox('Seleccione una receta:', recetas_df['nombre'], index=0)
    receta_id = recetas_df[recetas_df['nombre'] == receta_seleccionada]['id'].iloc[0]

    # 2. Selección de envase
    envases_df = get_envases()
    if envases_df is not None and not envases_df.empty:
        envase_seleccionado = st.selectbox('Seleccione un envase:', envases_df['descripcion'], index=0)
        envase_id = envases_df[envases_df['descripcion'] == envase_seleccionado]['id'].iloc[0]
        capacidad_envase = envases_df[envases_df['descripcion'] == envase_seleccionado]['capacidad_litros'].iloc[0]

        #3. Seleccionar fecha de presupuesto
        fecha_presupuesto = st.date_input("Fecha del presupuesto", datetime.today())
        fecha_presupuesto = fecha_presupuesto.strftime("%Y-%m-%d")

        # 4. Cantidad
        cantidad_a_presupuestar = st.number_input('Cantidad a presupuestar (litros):', min_value=0.01, value=1.0)

        # 5. Obtener ingredientes y calcular costo
        ingredientes_df = get_ingredientes_receta(receta_id)
        cantidad_total_receta = 200
        factor_proporcion = cantidad_a_presupuestar / cantidad_total_receta

        if ingredientes_df is not None and not ingredientes_df.empty:
            st.subheader('Costo de Materias Primas')
            costo_total_materias_primas = 0
            data = []
            for index, row in ingredientes_df.iterrows():
                precio_unitario = get_ultimo_precio_materia_prima(row['materia_prima_id'], fecha_presupuesto)
                cantidad_necesaria = row['cantidad'] * factor_proporcion
                if precio_unitario is not None:
                    costo_ingrediente = cantidad_necesaria * precio_unitario
                    costo_total_materias_primas += costo_ingrediente
                    data.append({
                        'Materia Prima': row['nombre'],
                        'Cantidad': cantidad_necesaria,
                        'Unidad': row['unidad'],
                        'Precio Unitario': precio_unitario,
                        'Costo': costo_ingrediente
                    })
                else:
                    st.warning(f"No se encontró precio para la materia prima: {row['nombre']}")
            df_para_mostrar = pd.DataFrame(data)
            st.dataframe(df_para_mostrar)
            st.write(f"**Costo Total Materias Primas:** {costo_total_materias_primas:.2f}")

            # 6. Obtener costo del envase
            precio_envase_usd = 0
            costo_total_envase = 0

            if envase_id is not None:
                precio_envase_usd = get_ultimo_precio_envase(envase_id, fecha_presupuesto)

                if precio_envase_usd:
                    st.subheader('Costo del Envase')

                    # Calcular la cantidad de envases necesarios
                    cantidad_envases_necesarios = math.ceil(cantidad_a_presupuestar / capacidad_envase)

                    costo_total_envase = precio_envase_usd * cantidad_envases_necesarios * valor_dolar # Precio en pesos
                    precio_envase_pesos = precio_envase_usd * valor_dolar

                    st.write(f"**Precio Unitario Envase (USD):** {precio_envase_usd:.2f}")
                    st.write(f"**Precio Unitario Envase (ARS):** {precio_envase_pesos:.2f}")
                    st.write(f"**Capacidad por envase:** {capacidad_envase:.2f} litros")
                    st.write(f"**Cantidad de envases necesarios:** {cantidad_envases_necesarios}")
                    st.write(f"**Costo Total Envase:** {costo_total_envase:.2f}")
                else:
                    st.warning("No se encontró precio para el envase.")
            else:
                st.warning("No se seleccionó un envase.")

            # 7. Otros costos y margen de ganancia
            st.subheader('Otros Costos')
            otros_costos = st.number_input('Ingrese otros costos:', value=0.0)
            margen_ganancia = st.number_input('Margen de ganancia (%):', value=20.0)

            # 8. Cálculo del presupuesto final
            costo_total = costo_total_materias_primas + (costo_total_envase if envase_id is not None and precio_envase_usd else 0) + otros_costos
            precio_venta = costo_total * (1 + margen_ganancia / 100)

            st.subheader('Presupuesto Final')
            st.write(f"**Costo Total:** {costo_total:.2f}")
            st.write(f"**Precio de Venta:** {precio_venta:.2f}")
            def generar_pdf_bytes(receta, envase, cantidad_envases_necesarios, costo_total):
                buffer = BytesIO()
                c = canvas.Canvas(buffer, pagesize=letter)
                c.setFont('Helvetica', 12)
                c.drawString(inch, 10.5 * inch, "Presupuesto para el cliente:")
                c.drawString(inch, 10 * inch, f"Fecha: {datetime.today().strftime('%Y-%m-%d')}")
                c.drawString(inch, 9.5 * inch, f"Receta: {receta}")
                c.drawString(inch, 9 * inch, f"Envase: {envase}")
                c.drawString(inch, 8.5 * inch, f"Cantidad de envases: {cantidad_envases_necesarios}")
                c.drawString(inch, 8 * inch, f"Costo Total (sin ganancia): {costo_total:.2f} ARS")
                c.save()
                buffer.seek(0)
                return buffer

            #Genera el PDF
            if precio_envase_usd:
                # Preparar los datos para la función
                # Generar el texto del presupuesto
                pdf_buffer = generar_pdf_bytes(receta_seleccionada, envase_seleccionado, cantidad_envases_necesarios, costo_total)

                # --- Botón de descarga para el PDF ---
                b64pdf = base64.b64encode(pdf_buffer.read()).decode('utf-8')
                href = f'<a href="data:application/pdf;base64,{b64pdf}" download="presupuesto_cliente.pdf">Descargar Presupuesto (PDF)</a>'
                st.markdown(href, unsafe_allow_html=True)
        else:
            st.warning('No se encontraron ingredientes para esta receta.')
    else:
        st.warning("No se encontraron envases en la base de datos.")

else:
    st.warning("No se encontraron recetas en la base de datos.")