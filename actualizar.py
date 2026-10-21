import pandas as pd
import sqlite3

# --- Configuración ---
DB_FILE = 'minerva.db'
CSV_FILE = 'envasestipo.csv' # Asegúrate que este archivo esté en la misma carpeta que tu script Python
STOCK_INICIAL_CAJAS = 10 # Cantidad inicial de cada tipo de caja en stock

# --- Conexión a la base de datos ---
conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

try:
    # --- 1. Borrar datos existentes (manejando dependencias) ---

    # Para poder borrar de tipo_cajas, debemos primero borrar de stock_cajas
    # que es la tabla que tiene la CLAVE FORÁNEA a tipo_cajas.
    # SQLITE maneja esto bien en cascada si se definen, pero es más seguro
    # borrar el "hijo" primero.

    print(f"Borrando todos los datos de 'stock_cajas' en {DB_FILE}...")
    cur.execute('DELETE FROM stock_cajas')
    print("Datos de 'stock_cajas' borrados.")

    print(f"Borrando todos los datos de 'tipo_cajas' en {DB_FILE}...")
    cur.execute('DELETE FROM tipo_cajas')
    print("Datos de 'tipo_cajas' borrados.")

    conn.commit() # Confirma los borrados


    # --- 2. Cargar datos del CSV ---
    print(f"Cargando datos desde '{CSV_FILE}'...")
    df = pd.read_csv(CSV_FILE)

    # Limpiar espacios en blanco de las columnas de texto que usaremos
    df['Producto'] = df['Producto'].astype(str).str.strip()
    df['Linea'] = df['Linea'].astype(str).str.strip()
    df['cantidad'] = df['cantidad'].astype(int) # Asegurarse que es int


    # --- 3. Insertar TIPOS DE CAJA únicos en 'tipo_cajas' (el catálogo maestro) ---
    # Usamos drop_duplicates para asegurarnos de que cada combinación (Producto, Linea, cantidad)
    # sea un tipo de caja único en el catálogo.
    unique_types = df.drop_duplicates(subset=['Producto', 'Linea', 'cantidad'])

    for index, row in unique_types.iterrows():
        producto = row['Producto']
        linea = row['Linea']
        unidades_por_caja = row['cantidad']
        descripcion = f"{producto} ({linea}) x{unidades_por_caja}u" # Una descripción útil

        cur.execute("""
            INSERT INTO tipo_cajas (producto, linea, unidades_por_caja, descripcion)
            VALUES (?, ?, ?, ?)
        """, (producto, linea, unidades_por_caja, descripcion))
    
    print(f"Catálogo de {len(unique_types)} tipos de cajas insertado en 'tipo_cajas'.")
    conn.commit() # Confirma la inserción de tipos de cajas


    # --- 4. Insertar STOCK FÍSICO en 'stock_cajas', referenciando 'tipo_cajas.id' ---
    # Iteramos sobre el DataFrame original para cada registro (incluso si tienen el mismo tipo de caja,
    # podríamos querer un registro de stock separado si vinieran de fuentes diferentes, etc.
    # En este caso, cada línea del CSV se asume como una 'unidad' para la que queremos 10 de stock).

    # Si quieres un único registro de stock por tipo de caja único, itera sobre `unique_types` también aquí.
    # Para este ejemplo, seguiremos el CSV original, asumiendo que cada fila del CSV (aún si duplicada en Producto/Linea/cantidad)
    # representa una instancia separada de la cual queremos 10 de stock.
    # Si quieres UN SOLO REGISTRO DE STOCK_CAJAS POR CADA TIPO_CAJA UNICO, cambia `df.iterrows()` a `unique_types.iterrows()`

    for index, row in df.iterrows():
        producto = row['Producto']
        linea = row['Linea']
        unidades_por_caja = row['cantidad']
        
        # Buscar el ID del tipo de caja que acabamos de insertar
        cur.execute("""
            SELECT id FROM tipo_cajas
            WHERE producto = ? AND linea = ? AND unidades_por_caja = ?
        """, (producto, linea, unidades_por_caja))
        
        tipo_caja_info = cur.fetchone() # Obtiene el (id,)
        
        if tipo_caja_info:
            tipo_caja_id = tipo_caja_info[0]
            # Usamos el tipo_caja textual para la columna 'tipo_caja' (compatible con versiones anteriores)
            # y el ID para la relación 'tipo_caja_id'
            tipo_caja_text = f"{producto} ({linea}) x{unidades_por_caja}u"

            cur.execute("""
                INSERT INTO stock_cajas (tipo_caja, capacidad_envase_id, cantidad_actual, ubicacion, tipo_caja_id)
                VALUES (?, ?, ?, ?, ?)
            """, (tipo_caja_text, None, STOCK_INICIAL_CAJAS, None, tipo_caja_id))
        else:
            print(f"Advertencia: No se encontró el tipo de caja en el catálogo para: {producto}, {linea}, {unidades_por_caja}")

    print(f"Stock de cajas con {len(df)} registros iniciales (10 c/u) insertado en 'stock_cajas'.")
    conn.commit() # Confirma la inserción del stock

    print("\n¡Proceso completado exitosamente!")
    print(f"Base de datos '{DB_FILE}' actualizada.")

except sqlite3.Error as e:
    print(f"\n¡Error en la operación de la base de datos!: {e}")
    conn.rollback() # Revierte cualquier cambio en caso de error
except FileNotFoundError:
    print(f"\n¡Error! El archivo CSV '{CSV_FILE}' no se encontró. Asegúrate de que está en la misma carpeta.")
except Exception as e:
    print(f"\nOcurrió un error inesperado: {e}")
finally:
    conn.close() # Cierra la conexión a la base de datos
