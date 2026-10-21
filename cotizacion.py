import streamlit as st
import requests
from bs4 import BeautifulSoup
import time
import sqlite3
from datetime import datetime

# --- Funciones para la base de datos de cotización actual (minerva.db) ---

def crear_tabla_dolar():
    """
    Crea la tabla 'cotizacion_dolar' en la base de datos 'minerva.db'
    si no existe. Esta tabla guarda la última cotización conocida para
    facilitar la comparación de cambios.
    """
    conn = sqlite3.connect('minerva.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS cotizacion_dolar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            compra REAL NOT NULL,
            venta REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def insertar_o_actualizar_cotizacion_dolar(compra, venta):
    """
    Inserta la cotización de compra y venta del dólar o la actualiza si ya existe un registro.
    Elimina cualquier registro anterior para asegurar que solo haya una fila con la última cotización.
    """
    conn = sqlite3.connect('minerva.db')
    c = conn.cursor()
    fecha_hora_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Eliminar cualquier registro anterior para asegurar que solo haya una fila
    c.execute("DELETE FROM cotizacion_dolar")
    
    # Insertar el nuevo registro de la cotización actual
    c.execute("INSERT INTO cotizacion_dolar (fecha_hora, compra, venta) VALUES (?, ?, ?)",
              (fecha_hora_actual, compra, venta))
    conn.commit()
    conn.close()
    st.success(f"Cotización actual guardada/actualizada: Compra ${compra:.2f}, Venta ${venta:.2f}")

def obtener_ultima_cotizacion_dolar():
    """
    Obtiene la última cotización de compra y venta del dólar de la tabla 'cotizacion_dolar'.
    Retorna un diccionario con 'compra' y 'venta', o None si no hay datos.
    """
    conn = sqlite3.connect('minerva.db')
    c = conn.cursor()
    # Recuperamos la última fila insertada para la comparación de cambios
    c.execute("SELECT compra, venta FROM cotizacion_dolar ORDER BY fecha_hora DESC LIMIT 1")
    data = c.fetchone()
    conn.close()
    if data:
        return {"compra": data[0], "venta": data[1]}
    return None

# --- Funciones para la base de datos de historial de cambios (minerva.db) ---

def crear_tabla_historial_cambios():
    """
    Crea la tabla 'historial_cambios_dolar' en la base de datos 'minerva.db'
    si no existe. Esta tabla registra cada cambio de precio (compra o venta).
    """
    conn = sqlite3.connect('minerva.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS historial_cambios_dolar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_cambio TEXT NOT NULL,
            tipo_cambio TEXT NOT NULL, -- Almacena 'compra' o 'venta'
            valor_anterior REAL,
            valor_nuevo REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def insertar_cambio_dolar(tipo_cambio, valor_anterior, valor_nuevo):
    """
    Inserta un registro de cambio en la tabla 'historial_cambios_dolar'.
    """
    conn = sqlite3.connect('minerva.db')
    c = conn.cursor()
    fecha_hora_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("INSERT INTO historial_cambios_dolar (fecha_cambio, tipo_cambio, valor_anterior, valor_nuevo) VALUES (?, ?, ?, ?)",
              (fecha_hora_actual, tipo_cambio, valor_anterior, valor_nuevo))
    conn.commit()
    conn.close()

    # Formateo seguro para mostrar en Streamlit, manejando el caso donde valor_anterior es None
    valor_anterior_str = f"${valor_anterior:.2f}" if valor_anterior is not None else "N/A"
    st.info(f"¡Cambio detectado! {tipo_cambio.capitalize()}: {valor_anterior_str} -> ${valor_nuevo:.2f}")


# --- Función para obtener el precio del dólar del Banco Nación (Web Scraping) ---

def obtener_precio_dolar_bna_real():
    """
    Intenta extraer el precio de compra y venta del dólar de la página de Banco Nación.
    Retorna un diccionario con 'compra' y 'venta' (como floats), o None si falla.
    """
    url = "https://www.bna.com.ar/Personas"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # Lanza una excepción si la respuesta no es 200 OK
        soup = BeautifulSoup(response.text, 'html.parser')

        main_tag = soup.find('main')
        if not main_tag:
            st.warning("No se encontró la etiqueta <main>.")
            return None

        # Navegación a través de divs: Esta parte es sensible a cambios en la estructura de la página
        target_div = main_tag
        try:
            target_div = target_div.find_all('div', recursive=False)[0] 
            target_div = target_div.find_all('div', recursive=False)[0] 
            target_div = target_div.find_all('div', recursive=False)[3] 
            target_div = target_div.find_all('div', recursive=False)[0] 
            target_div = target_div.find_all('div', recursive=False)[0] 
            target_div = target_div.find_all('div', recursive=False)[0] 
            target_div = target_div.find_all('div', recursive=False)[0] 
            
        except IndexError:
            st.warning("La estructura de divs no coincide con el XPath. Los índices pueden haber cambiado.")
            return None

        table = target_div.find('table')
        if not table:
            st.warning("No se encontró la tabla en la ruta especificada.")
            return None

        tbody = table.find('tbody')
        if not tbody:
            st.warning("No se encontró el tbody en la tabla.")
            return None

        first_row = tbody.find_all('tr', recursive=False)
        if not first_row:
            st.warning("No se encontró la primera fila (tr) en el tbody.")
            return None
        
        row_data = first_row[0]
        cols = row_data.find_all('td')

        if len(cols) >= 3:
            compra_raw = cols[1].get_text(strip=True)
            venta_raw = cols[2].get_text(strip=True)

            # Limpiar formato (ej. "1.234,56" a "1234.56" para float)
            compra = compra_raw.replace('.', '').replace(',', '.')
            venta = venta_raw.replace('.', '').replace(',', '.')
            
            try:
                # Convertir a float antes de retornar para facilitar el manejo en la DB
                return {"compra": float(compra), "venta": float(venta)} 
            except ValueError:
                st.warning(f"Valores extraídos no numéricos: Compra='{compra_raw}', Venta='{venta_raw}'")
                return None
        else:
            st.warning("No se encontraron suficientes columnas (td) en la fila esperada.")
            return None

    except requests.exceptions.RequestException as e:
        st.error(f"Error de conexión al intentar obtener datos del Banco Nación: {e}")
        return None
    except Exception as e:
        st.error(f"Error inesperado al procesar la página: {e}")
        return None

# --- Configuración de la página Streamlit ---

st.set_page_config(
    page_title="Cotización Dólar Banco Nación",
    page_icon="💰",
    layout="centered"
)

st.title("💰 Cotización del Dólar Oficial (Banco Nación)")

st.markdown("""
Esta aplicación te muestra la cotización actual del dólar oficial del Banco Nación Argentina y
lleva un **historial de los cambios** detectados en sus precios de compra y venta.
""")

# --- Asegurarse de que las tablas existan al iniciar la aplicación ---
# Es crucial llamar a estas funciones al inicio para que las tablas estén listas
crear_tabla_dolar()
crear_tabla_historial_cambios()

# --- Botón de Actualizar y mostrar cotización ---
if st.button("Actualizar Cotización y Guardar Cambios"):
    st.info("Intentando obtener la cotización...")
    with st.spinner("Cargando datos..."):
        # 1. Obtener la última cotización guardada antes de obtener la nueva.
        # Esto es para poder comparar y detectar cambios.
        ultima_cotizacion_guardada = obtener_ultima_cotizacion_dolar()
        
        # 2. Obtener la nueva cotización en tiempo real del Banco Nación.
        dolar_data = obtener_precio_dolar_bna_real()        
        time.sleep(1) # Pequeña pausa para mejorar la experiencia de usuario

    if dolar_data:
        st.success("Cotización actualizada:")
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="Dólar Compra", value=f"${dolar_data['compra']:.2f}")
        with col2:
            st.metric(label="Dólar Venta", value=f"${dolar_data['venta']:.2f}")
        
        # 3. Guardar la cotización actual. Esta operación sobrescribe la anterior
        # en la tabla `cotizacion_dolar` para mantener siempre el último valor.
        insertar_o_actualizar_cotizacion_dolar(dolar_data['compra'], dolar_data['venta'])

        # 4. Lógica para registrar los cambios en la tabla `historial_cambios_dolar`.
        if ultima_cotizacion_guardada:
            # Comparar el precio de compra actual con el último guardado
            if dolar_data['compra'] != ultima_cotizacion_guardada['compra']:
                insertar_cambio_dolar("compra", ultima_cotizacion_guardada['compra'], dolar_data['compra'])
            
            # Comparar el precio de venta actual con el último guardado
            if dolar_data['venta'] != ultima_cotizacion_guardada['venta']:
                insertar_cambio_dolar("venta", ultima_cotizacion_guardada['venta'], dolar_data['venta'])
        else:
            # Si no había datos previos, los primeros datos se consideran un "cambio inicial"
            insertar_cambio_dolar("compra", None, dolar_data['compra'])
            insertar_cambio_dolar("venta", None, dolar_data['venta'])


        st.caption(f"Última verificación: {datetime.now().strftime('%H:%M:%S del %d/%m/%Y')}")
    else:
        st.error("No se pudo obtener la cotización del dólar.")
        st.info("Recuerda que el web scraping es muy sensible a los cambios en la estructura de la página web. "
                "Si la aplicación deja de funcionar, es probable que la página de Banco Nación haya cambiado su diseño.")

st.markdown("---")
