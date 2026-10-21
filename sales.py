import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import random
from datetime import date

# Configuración de la base de datos (ajusta la URL según tu configuración)
engine = create_engine('sqlite:///minerva.db')

# Función para obtener los datos de la base de datos
def cargar_datos(query):
    with engine.connect() as con:
        df = pd.read_sql(query, con)
    return df

# Generar número de comprobante único
def generar_numero_comprobante():
    fecha_actual = date.today().strftime("%Y%m%d")
    random_number = random.randint(1000, 9999)
    return f"{fecha_actual}-{random_number}"

# Obtener los clientes
clientes_df = cargar_datos("SELECT id, nombre FROM clientes")
clientes_dict = {row['nombre']: row['id'] for row in clientes_df.to_dict('records')}

# Interfaz con Streamlit
st.title("Gestión de Ventas Minerva")

# Inicializar la sesión state para el carrito de ventas
if 'carrito' not in st.session_state:
    st.session_state['carrito'] = []

# Generar número de comprobante al inicio
if 'numero_comprobante' not in st.session_state:
    st.session_state['numero_comprobante'] = generar_numero_comprobante()

st.write(f"**Número de Comprobante:** {st.session_state['numero_comprobante']}")

# Selección del cliente
cliente_nombre = st.selectbox("Seleccione el cliente:", list(clientes_dict.keys()))
cliente_id = clientes_dict[cliente_nombre]

# Si el cliente es BEKIM
if cliente_nombre == "BEKIM":
    st.subheader("Venta a Granel para BEKIM")

    # Obtener las recetas del cliente BEKIM
    recetas_bekim_df = cargar_datos(f"SELECT id, nombre FROM recetas WHERE cliente_id = {cliente_id}")
    recetas_bekim_dict = {row['nombre']: row['id'] for row in recetas_bekim_df.to_dict('records')}

    receta_nombre = st.selectbox("Seleccione la receta:", list(recetas_bekim_dict.keys()))
    receta_id = recetas_bekim_dict[receta_nombre]

    cantidad_producida = st.number_input("Cantidad producida (litros):", min_value=0.0, step=0.1)
    precio_por_litro = st.number_input("Precio por litro:", min_value=0.0, step=0.01)

    if st.button("Agregar a Venta a Granel"):
        # Aquí iría la lógica para agregar la venta a granel al carrito (session_state)
        st.session_state['carrito'].append({
            'tipo': 'granel',
            'receta_nombre': receta_nombre,
            'cantidad_producida': cantidad_producida,
            'precio_por_litro': precio_por_litro
        })
        st.success(f"{cantidad_producida} litros de {receta_nombre} agregados a la venta a granel.")

else:
    st.subheader("Venta de Productos Envasados")

    # Obtener stock de productos envasados
    stock_df = cargar_datos("""
    SELECT
        spe.id as stock_id,
        p.nombre AS producto,
        e.descripcion AS envase,
        spe.lote,
        spe.cantidad,
        pp.precio_unitario
    FROM
        stock_productos_envasados spe
    JOIN productos p ON spe.receta_id = p.id_receta
    JOIN envases e ON spe.envase_id = e.id
    LEFT JOIN precios_productos_envasados pp ON spe.cliente_id = pp.cliente_id AND spe.receta_id = pp.producto_id AND spe.envase_id = pp.envase_id
    WHERE spe.cliente_id = """+ str(cliente_id) +"""
    """)

    # Selectbox para elegir producto del stock
    producto_seleccionado = st.selectbox("Seleccione un producto del stock:", stock_df['producto'].unique())

    # Filtrar el DataFrame según el producto seleccionado
    stock_producto = stock_df[stock_df['producto'] == producto_seleccionado]

    # Desplegar la información del producto seleccionado
    if not stock_producto.empty:
      st.write("Detalles del producto:")
      st.write(stock_producto)

      # Input para la cantidad a agregar al carrito
      cantidad_a_agregar = st.number_input(f"Cantidad de {producto_seleccionado} a agregar:", min_value=1, max_value=int(stock_producto['cantidad'].values[0]), value=1)

      if st.button("Agregar al carrito"):
            # Aquí iría la lógica para agregar el producto envasado al carrito (session_state)
            st.session_state['carrito'].append({
                'tipo': 'envasado',
                'stock_id': stock_producto['stock_id'].values[0],
                'producto': producto_seleccionado,
                'envase': stock_producto['envase'].values[0],
                'cantidad': cantidad_a_agregar,
                'precio_unitario': stock_producto['precio_unitario'].values[0] if not pd.isna(stock_producto['precio_unitario'].values[0]) else 0
            })
            st.success(f"{cantidad_a_agregar} unidades de {producto_seleccionado} agregadas al carrito.")
    else:
        st.warning("No hay stock disponible para ese producto.")

# Mostrar el carrito de ventas
st.subheader("Carrito de Ventas")
if st.session_state['carrito']:
    carrito_df = pd.DataFrame(st.session_state['carrito'])
    st.dataframe(carrito_df)

    # Calcular el total
    total_venta = 0
    for item in st.session_state['carrito']:
        if item['tipo'] == 'envasado':
            total_venta += item['cantidad'] * item['precio_unitario']
        elif item['tipo'] == 'granel':
            total_venta += item['cantidad_producida'] * item['precio_por_litro']
    st.write(f"**Total de la Venta:** {total_venta}")

    if st.button("Finalizar Venta"):
        # Aquí iría la lógica para guardar la venta en la base de datos
        st.success("Venta registrada correctamente.")
        # Limpiar el carrito después de la venta
        st.session_state['carrito'] = []
        st.session_state['numero_comprobante'] = generar_numero_comprobante() # Generar uno nuevo
        st.write(f"**Número de Comprobante:** {st.session_state['numero_comprobante']}")
else:
    st.info("El carrito está vacío.")