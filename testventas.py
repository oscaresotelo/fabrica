import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- Funciones de conexión y consulta a la base de datos ---
def conectar_bd():
    try:
        conn = sqlite3.connect('minerva.db')
        return conn
    except sqlite3.Error as e:
        st.error(f"Error al conectar a la base de datos: {e}")
        return None

def obtener_productos(conn, cliente_id):
    """Obtiene los productos de un cliente específico."""
    try:
        query = f"""
        SELECT
            p.id,
            p.nombre,
            {'' if cliente_id == 8 else 'e.descripcion AS envase,'}
            COALESCE(ppb.precio_unitario, 0) AS precio_unitario_bekim,
            COALESCE(pr.cantidad_real_litros, 0) AS cantidad_stock_bekim
        FROM productos p
        JOIN productos_clientes pc ON p.id = pc.producto_id
        LEFT JOIN producciones pr ON p.id = pr.pedido_id
        LEFT JOIN precios_productos_bekim ppb ON p.id = ppb.producto_id AND pc.cliente_id = {cliente_id}
        LEFT JOIN envases e ON p.envase_id = e.id
        WHERE pc.cliente_id = {cliente_id}
        """

        df = pd.read_sql_query(query, conn)
        return df
    except Exception as e:
        st.error(f"Error al obtener los productos: {e}")
        return pd.DataFrame()

def insertar_venta(conn, cliente_id, total_venta, items):
     """Inserta la venta y sus detalles en la base de datos."""
     try:
         fecha_venta = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
         cursor = conn.cursor()

         # Insertar la venta
         cursor.execute("""
             INSERT INTO ventas (cliente_id, fecha_venta, total_venta)
             VALUES (?, ?, ?)
         """, (cliente_id, fecha_venta, total_venta))
         venta_id = cursor.lastrowid

         # Insertar los detalles de la venta
         for item in items:
             producto_id = item['producto_id']
             cantidad = item['cantidad']
             precio_unitario = item['precio_unitario']
             subtotal = cantidad * precio_unitario

             cursor.execute("""
                 INSERT INTO detalle_venta (venta_id, stock_id, cantidad, precio_unitario, subtotal)
                 VALUES (?, ?, ?, ?, ?)
             """, (venta_id, producto_id, cantidad, precio_unitario, subtotal))

             # Actualizar el stock (asumiendo egreso)
             if cliente_id == 6: #Minerva
                 cursor.execute("""
                     UPDATE stock_productos_envasados
                     SET cantidad = cantidad - ?
                     WHERE receta_id = ?
                 """, (cantidad, producto_id))

                 # Agregar movimiento de stock
                 cursor.execute("""
                     INSERT INTO movimientos_productos_envasados (stock_id, fecha, cantidad, tipo_movimiento)
                     SELECT id, ?, ?, 'Egreso' FROM stock_productos_envasados WHERE receta_id = ?
                 """, (fecha_venta, cantidad, producto_id))
             else:  # Bekim
                cursor.execute("""
                     UPDATE producciones
                     SET cantidad_real_litros = cantidad_real_litros - ?
                     WHERE pedido_id = ?
                 """, (cantidad, producto_id))

                cursor.execute("""
                     INSERT INTO movimientos_productos_envasados (stock_id, fecha, cantidad, tipo_movimiento)
                     SELECT id, ?, ?, 'Egreso' FROM producciones WHERE pedido_id = ?
                 """, (fecha_venta, cantidad, producto_id))

         conn.commit()
         return venta_id
     except Exception as e:
         conn.rollback()
         st.error(f"Error al insertar la venta: {e}")
         return None


# --- Interfaz Streamlit ---
st.title('Sistema de Ventas Minerva/Bekim')

# --- Selección del cliente ---
cliente = st.selectbox('Seleccione el cliente:', ['Minerva', 'Bekim'])
cliente_id = 6 if cliente == 'Minerva' else 8

# --- Conexión a la base de datos ---
conn = conectar_bd()
if conn is None:
    st.stop()

# --- Obtener productos ---
productos_df = obtener_productos(conn, cliente_id)

if productos_df.empty:
    st.warning("No se encontraron productos para este cliente.")
    st.stop()

# --- Mostrar productos y cantidades ---
st.subheader(f'Productos de {cliente}')

# Diccionario para almacenar las cantidades seleccionadas
cantidades = {}

for index, row in productos_df.iterrows():
    producto_nombre = row['nombre']
    if cliente_id == 6:
        producto_nombre = f"{row['nombre']} ({row['envase']})"
        cantidad_maxima = int(row['cantidad_stock'])  # Convertir a entero
        precio_unitario = row['precio_unitario']
    else:
        cantidad_maxima = int(row['cantidad_stock_bekim'])  # Convertir a entero
        precio_unitario = row['precio_unitario_bekim']

    # Widgets para seleccionar la cantidad
    cantidades[row['id']] = st.number_input(
        label=producto_nombre,
        min_value=0,
        max_value=cantidad_maxima,
        value=0,
        step=1,
        format="%d",  # Para evitar errores con floats
    )

# --- Carrito de compras ---
st.subheader('Carrito de Compras')

carrito_items = []
total_venta = 0

for producto_id, cantidad in cantidades.items():
    if cantidad > 0:
        producto = productos_df[productos_df['id'] == producto_id].iloc[0]

        if cliente_id == 6:
            precio_unitario = producto['precio_unitario']
            nombre = producto['nombre']
            envase = producto['envase']
        else:
            precio_unitario = producto['precio_unitario_bekim']
            nombre = producto['nombre']
            envase = ""
        subtotal = cantidad * precio_unitario
        carrito_items.append({
            'producto_id': producto['id'],
            'cantidad': cantidad,
            'precio_unitario': precio_unitario,
            'subtotal': subtotal,
            'nombre': nombre,
            'envase': envase
        })
        total_venta += subtotal

if carrito_items:
    carrito_df = pd.DataFrame(carrito_items)
    st.dataframe(carrito_df[['nombre', 'envase', 'cantidad', 'precio_unitario', 'subtotal']])
    st.write(f'**Total:** ${total_venta}')
else:
    st.info('El carrito está vacío.')

# --- Botón de generar venta ---
if carrito_items:
    if st.button('Generar Venta'):
        venta_id = insertar_venta(conn, cliente_id, total_venta, carrito_items)
        if venta_id:
            st.success(f'Venta generada con éxito. ID de venta: {venta_id}')

            # Generar comprobante (ejemplo básico)
            st.subheader('Comprobante de Venta')
            st.write(f'**ID de Venta:** {venta_id}')
            st.write(f'**Cliente:** {cliente}')
            st.write(f'**Fecha:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
            st.dataframe(carrito_df[['nombre', 'envase', 'cantidad', 'precio_unitario', 'subtotal']])
            st.write(f'**Total:** ${total_venta}')

            # Botón de descarga (simulación)
            st.download_button(
                label="Descargar Comprobante",
                data=f"Comprobante de Venta ID: {venta_id}\nCliente: {cliente}\nTotal: {total_venta}",
                file_name=f"comprobante_venta_{venta_id}.txt",
                mime="text/plain"
            )
        else:
            st.error('Hubo un error al generar la venta.')
else:
    st.warning('No hay productos en el carrito para generar la venta.')

conn.close()