import pandas as pd
import sqlite3

# Nombre del archivo de la base de datos
DB_FILE = 'minerva.db'
# Nombre del archivo CSV
CSV_FILE = 'revendedores.csv'
# Nombre de la tabla de destino
TABLE_NAME = 'revendedores'

def load_csv_to_existing_table(db_file, csv_file, table_name):
    """
    Carga los datos de un archivo CSV en una tabla de una base de datos SQLite
    existente, mapeando las columnas del CSV a las de la tabla.
    """
    try:
        # Cargar el archivo CSV en un DataFrame de pandas
        df_revendedores = pd.read_csv(csv_file)

        # Limpiar y preparar los datos
        # Eliminar filas donde la columna 'Nombre' está vacía
        df_revendedores.dropna(subset=['Nombre'], inplace=True)
        # Rellenar los valores vacíos en 'Porcentaje' con 0
        df_revendedores['Porcentaje'] = df_revendedores['Porcentaje'].fillna(0)
        # Convertir la columna 'Porcentaje' a tipo entero
        df_revendedores['Porcentaje'] = df_revendedores['Porcentaje'].astype(int)

        # Renombrar las columnas del DataFrame para que coincidan con la tabla
        df_revendedores.rename(columns={'Nombre': 'nombre', 'Porcentaje': 'descuento'}, inplace=True)

        # Conectar a la base de datos
        conn = sqlite3.connect(db_file)

        # Insertar el DataFrame en la tabla existente.
        # 'if_exists="append"' añade los datos sin borrar la tabla.
        # Las columnas del DataFrame deben coincidir con las de la tabla de destino.
        df_revendedores.to_sql(table_name, conn, if_exists='append', index=False)

        # Confirmar los cambios y cerrar la conexión
        conn.commit()
        conn.close()

        print(f"Datos de '{csv_file}' cargados exitosamente en la tabla '{table_name}'.")

    except Exception as e:
        print(f"Ocurrió un error: {e}")

# Lógica principal del script
if __name__ == "__main__":
    load_csv_to_existing_table(DB_FILE, CSV_FILE, TABLE_NAME)