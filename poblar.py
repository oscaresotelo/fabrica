import sqlite3
import pandas as pd

DB_FILE = "minerva.db"

def analizar_composicion_colorantes():
    """Analiza la consistencia de los datos en composicion_colorantes."""
    conn = sqlite3.connect(DB_FILE)
    try:
        # 1. Obtener todos los colorantes combinados
        colorantes_combinados_query = """
            SELECT id, nombre FROM materias_primas
            WHERE nombre LIKE 'Colorante%'
        """
        colorantes_combinados_df = pd.read_sql_query(colorantes_combinados_query, conn)
        colorantes_combinados_dict = {row['id']: row['nombre'] for _, row in colorantes_combinados_df.iterrows()}

        # 2. Obtener la composición de todos los colorantes combinados
        composicion_query = """
            SELECT colorante_combinado_id, colorante_primario_id, proporcion
            FROM composicion_colorantes
        """
        composicion_df = pd.read_sql_query(composicion_query, conn)

        # 3. Identificar colorantes combinados sin composición
        colorantes_sin_composicion = set(colorantes_combinados_dict.keys()) - set(composicion_df['colorante_combinado_id'])
        if colorantes_sin_composicion:
            print("Colorantes combinados SIN composición definida:")
            for colorante_id in colorantes_sin_composicion:
                print(f"- ID: {colorante_id}, Nombre: {colorantes_combinados_dict[colorante_id]}")
        else:
            print("Todos los colorantes combinados tienen una composición definida.")

        # 4. Verificar la existencia de colorantes primarios en la tabla materias_primas
        colorantes_primarios_ids = set(composicion_df['colorante_primario_id'])
        materias_primas_query = "SELECT id FROM materias_primas"
        materias_primas_df = pd.read_sql_query(materias_primas_query, conn)
        materias_primas_ids = set(materias_primas_df['id'])

        colorantes_primarios_inexistentes = colorantes_primarios_ids - materias_primas_ids
        if colorantes_primarios_inexistentes:
            print("\nColorantes primarios INEXISTENTES en la tabla materias_primas:")
            print(colorantes_primarios_inexistentes)
        else:
            print("\nTodos los colorantes primarios existen en la tabla materias_primas.")

        # 5. Verificar si la suma de las proporciones es igual a 1 para cada colorante combinado
        suma_proporciones = composicion_df.groupby('colorante_combinado_id')['proporcion'].sum()
        suma_proporciones_invalidas = suma_proporciones[abs(suma_proporciones - 1) > 0.001] # Tolerar pequeñas diferencias por punto flotante

        if not suma_proporciones_invalidas.empty:
            print("\nColorantes combinados con SUMA de proporciones INVALIDA:")
            for colorante_id, suma in suma_proporciones_invalidas.items():
                print(f"- ID: {colorante_id}, Nombre: {colorantes_combinados_dict.get(colorante_id, 'Desconocido')}, Suma: {suma}")
        else:
            print("\nTodos los colorantes combinados tienen una suma de proporciones válida (aproximadamente 1).")

        # 6. Buscar Colorantes Combinados sin entradas en composicion_colorantes
        query = """
        SELECT id, nombre FROM materias_primas
        WHERE nombre LIKE 'Colorante%'
        AND id NOT IN (SELECT DISTINCT colorante_combinado_id FROM composicion_colorantes)
        """
        sin_composicion_df = pd.read_sql_query(query, conn)

        if not sin_composicion_df.empty:
            print("\nColorantes combinados definidos en materias_primas pero SIN composición en composicion_colorantes:")
            for _, row in sin_composicion_df.iterrows():
                print(f"- ID: {row['id']}, Nombre: {row['nombre']}")
        else:
            print("\nTodos los colorantes combinados tienen al menos una entrada en composicion_colorantes.")


    except sqlite3.Error as e:
        print(f"Error de SQLite: {e}")
    finally:
        conn.close()

analizar_composicion_colorantes()