import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# Configuración de la página Streamlit
st.set_page_config(
    page_title="Cálculo de Costo de Producción",
    page_icon=":moneybag:",
    layout="wide",
)

# Título de la aplicación
st.title("Cálculo de Costo de Producción")

# Conexión a la base de datos SQLite - Solución del error de hilo
@st.cache_resource
def conectar_db():
    try:
        conn = sqlite3.connect('minerva.db', check_same_thread=False)
        return conn
    except sqlite3.Error as e:
        st.error(f"Error al conectar a la base de datos: {e}")
        return None

# --- Funciones para los cálculos ---
def obtener_composicion_detallada(conn, receta_id, envase_capacidad_litros):
    query_detalle = """
    SELECT
        mp.nombre AS nombre_materia_prima,
        (ri.cantidad / 200.0) * ? AS cantidad_por_envase,
        COALESCE(pmp.precio_unitario, 0) AS precio_por_unidad_materia_prima,
        ((ri.cantidad / 200.0) * ?) * COALESCE(pmp.precio_unitario, 0) AS costo_total_por_envase
    FROM
        receta_ingredientes ri
    JOIN
        materias_primas mp ON ri.materia_prima_id = mp.id
    LEFT JOIN
        precios_materias_primas pmp ON mp.id = pmp.materia_prima_id AND pmp.fecha = (SELECT MAX(fecha) FROM precios_materias_primas pmp2 WHERE pmp2.materia_prima_id = mp.id)
    WHERE
        ri.receta_id = ?;
    """
    df_detalle = pd.read_sql_query(query_detalle, conn, params=(envase_capacidad_litros, envase_capacidad_litros, receta_id))
    return df_detalle

# --- Sección de Cálculo de Producción Total ---
def mostrar_calculo_produccion_total(conn, df_productos_info):
    st.markdown("---")
    st.header("📈 Cálculo de Producción Total")
    st.markdown("Calcule el costo total de un lote completo de producción.")
    
    productos_disponibles = df_productos_info[['receta_id', 'producto_nombre', 'envase_capacidad_litros', 'precio_envase']].drop_duplicates()
    productos_dict = {
        row['producto_nombre']: {
            'receta_id': row['receta_id'],
            'envase_capacidad_litros': row['envase_capacidad_litros'],
            'precio_envase': row['precio_envase']
        }
        for _, row in productos_disponibles.iterrows()
    }
    
    opciones_productos = sorted(list(productos_dict.keys()))
    producto_seleccionado = st.selectbox(
        "Seleccione un producto:",
        options=[""] + opciones_productos,
        key="selectbox_produccion_total"
    )

    if producto_seleccionado:
        receta_id = productos_dict[producto_seleccionado]['receta_id']
        envase_capacidad = productos_dict[producto_seleccionado]['envase_capacidad_litros']
        precio_envase = productos_dict[producto_seleccionado]['precio_envase']
        
        unidades_a_producir = st.number_input(
            "Ingrese el número de unidades a producir:",
            min_value=1,
            value=100,
            step=1,
            key="unidades_a_producir"
        )

        if unidades_a_producir > 0:
            df_detalle_por_envase = obtener_composicion_detallada(conn, receta_id, envase_capacidad)
            
            df_detalle_total_produccion = df_detalle_por_envase.copy()
            df_detalle_total_produccion['cantidad_total_necesaria'] = df_detalle_total_produccion['cantidad_por_envase'] * unidades_a_producir
            df_detalle_total_produccion['costo_total_lote'] = df_detalle_total_produccion['costo_total_por_envase'] * unidades_a_producir
            
            st.markdown("---")
            st.subheader("Desglose de Materias Primas para el Lote")
            st.dataframe(df_detalle_total_produccion[['nombre_materia_prima', 'cantidad_total_necesaria', 'costo_total_lote']], use_container_width=True)
            
            costo_materia_prima_total = df_detalle_total_produccion['costo_total_lote'].sum()
            costo_envases_total = unidades_a_producir * precio_envase
            costo_total_produccion = costo_materia_prima_total + costo_envases_total
            
            st.markdown("---")
            st.subheader("Resultados del Lote de Producción")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="Total de Materia Prima", value=f"${costo_materia_prima_total:.2f}")
            with col2:
                st.metric(label="Total de Envases", value=f"${costo_envases_total:.2f}")
            with col3:
                st.metric(label="Costo Total de Producción", value=f"${costo_total_produccion:.2f}")

# --- Inicio del Script Principal ---
conn = conectar_db()

# Parámetros iniciales
multiplicador = st.number_input("Ingrese el valor multiplicador:", value=1.0, step=0.01)

# Se ejecuta la consulta principal al inicio de la aplicación
query = """
SELECT
    r.id AS receta_id,
    r.nombre AS receta_nombre,
    p.id AS producto_id,
    p.nombre AS producto_nombre,
    e.id AS envase_id,
    e.descripcion AS envase_descripcion,
    e.capacidad_litros AS envase_capacidad_litros,
    COALESCE(ee.precio_unitario * :multiplicador, 0) AS precio_envase,
    SUM(ri.cantidad * pmp.precio_unitario) AS costo_total_materia_prima,
    (SUM(ri.cantidad * pmp.precio_unitario) / 200) * e.capacidad_litros + COALESCE(ee.precio_unitario * :multiplicador,0) AS costo_por_unidad_envasada,
    CASE
        WHEN EXISTS (SELECT 1 FROM receta_ingredientes ri2 JOIN precios_materias_primas pmp2 ON ri2.materia_prima_id = pmp2.materia_prima_id WHERE ri2.receta_id = r.id AND pmp2.precio_unitario IS NULL) THEN 1
        ELSE 0
    END AS falta_precio,
    CASE
        WHEN EXISTS (SELECT 1 FROM receta_ingredientes ri2 LEFT JOIN stock_materias_primas smp ON ri2.materia_prima_id = smp.materia_prima_id WHERE ri2.receta_id = r.id AND (smp.cantidad_actual IS NULL OR smp.cantidad_actual = 0)) THEN 1
        ELSE 0
    END AS falta_stock
FROM
    recetas r
JOIN
    receta_ingredientes ri ON r.id = ri.receta_id
JOIN
    materias_primas mp ON ri.materia_prima_id = mp.id
JOIN
    precios_materias_primas pmp ON mp.id = pmp.materia_prima_id
JOIN
    productos p ON r.id = p.id_receta
JOIN
    envases e ON p.envase_id = e.id
LEFT JOIN (SELECT entradas_envases.envase_id, entradas_envases.precio_unitario, entradas_envases.fecha_ingreso
           FROM entradas_envases) AS ee ON e.id = ee.envase_id
LEFT JOIN
    cotizacion_dolar cd ON DATE(pmp.fecha) = DATE(cd.fecha_hora)
WHERE pmp.fecha = (SELECT MAX(fecha) FROM precios_materias_primas pmp2 WHERE pmp2.materia_prima_id = mp.id)
GROUP BY
    r.id, p.id, e.id;
"""

if 'df_resultados' not in st.session_state:
    st.session_state.df_resultados = pd.DataFrame()

# Llenar el dataframe al inicio o al presionar el botón
calcular_button = st.button("Actualizar Cálculos", key="calcular_button_main")
if conn:
    if not calcular_button and st.session_state.df_resultados.empty:
        try:
            st.session_state.df_resultados = pd.read_sql_query(query, conn, params={"multiplicador": multiplicador})
        except Exception as e:
            st.error(f"Error al cargar los datos iniciales: {e}")
    elif calcular_button:
        try:
            st.session_state.df_resultados = pd.read_sql_query(query, conn, params={"multiplicador": multiplicador})
            st.success("¡Cálculo actualizado! Los resultados están listos.")
        except Exception as e:
            st.error(f"Error al ejecutar la consulta: {e}")

# Lógica de visualización
if not st.session_state.df_resultados.empty:
    df_resultados = st.session_state.df_resultados
    
    def estilo_celda(valor, falta_precio, falta_stock):
        if falta_precio == 1:
            return 'background-color: lightcoral'
        elif falta_stock == 1:
            return 'background-color: lightyellow'
        else:
            return ''

    def estilo_fila(row):
        estilo = [estilo_celda(row["receta_nombre"], row["falta_precio"], row["falta_stock"])] * len(row)
        return estilo

    st.subheader("📊 Costo por Unidad y Composición Detallada")
    df_estilo = df_resultados.style.apply(estilo_fila, axis=1)
    st.dataframe(df_estilo, use_container_width=True)
    

    st.markdown("---")
    st.subheader("🔍 Composición Detallada por Producto")
    with st.expander("Ver composición detallada"):
        productos_disponibles = df_resultados[['receta_id', 'producto_nombre', 'envase_capacidad_litros', 'precio_envase']].drop_duplicates()
        productos_dict = {
            row['producto_nombre']: {
                'receta_id': row['receta_id'],
                'envase_capacidad_litros': row['envase_capacidad_litros'],
                'precio_envase': row['precio_envase']
            }
            for _, row in productos_disponibles.iterrows()
        }

        producto_seleccionado = st.selectbox(
            "Seleccione un producto:",
            options=sorted(list(productos_dict.keys())),
            key="selectbox_unidad"
        )
        
        if producto_seleccionado:
            receta_id_seleccionada = productos_dict[producto_seleccionado]['receta_id']
            envase_capacidad = productos_dict[producto_seleccionado]['envase_capacidad_litros']
            precio_envase = productos_dict[producto_seleccionado]['precio_envase']
            
            df_detalle = obtener_composicion_detallada(conn, receta_id_seleccionada, envase_capacidad)
            
            if not df_detalle.empty:
                costo_total_materia_prima = df_detalle['costo_total_por_envase'].sum()

                df_envase = pd.DataFrame([{
                    'nombre_materia_prima': 'Envase',
                    'cantidad_por_envase': '',
                    'precio_por_unidad_materia_prima': '',
                    'costo_total_por_envase': precio_envase
                }])
                
                df_detalle_final = pd.concat([df_detalle, df_envase], ignore_index=True)
                
                st.write(f"**Composición de {producto_seleccionado}:**")
                st.dataframe(df_detalle_final, use_container_width=True)
                
                st.markdown("---")
                st.markdown(f"**Total Materia Prima:** ${costo_total_materia_prima:.2f}")
                st.markdown(f"**Precio del Envase:** ${precio_envase:.2f}")
                
                costo_total_unidad = costo_total_materia_prima + precio_envase
                st.markdown(f"**Costo Total por Unidad:** ${costo_total_unidad:.2f}")
            else:
                st.info("No se encontraron ingredientes para esta receta.")

    csv = df_resultados.to_csv(index=False)
    st.download_button(
        label="Descargar datos como CSV",
        data=csv,
        file_name=f'costos_produccion_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
        mime='text/csv',
    )
    
else:
    st.info("Presione 'Actualizar Cálculos' para obtener los resultados.")

# Llamada a la nueva función para mostrar la interfaz de cálculo total
if conn:
    mostrar_calculo_produccion_total(conn, st.session_state.df_resultados)