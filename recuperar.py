import sqlite3

def recuperar_base_datos(db_dañada, db_nueva):
    print(f"Intentando recuperar datos de {db_dañada}...")
    try:
        # Conectamos a la base dañada
        conn_dañada = sqlite3.connect(db_dañada)
        
        # El comando .iterdump intenta leer la base de datos incluso si hay errores
        # y genera el SQL necesario para recrearla
        with open('temp_script.sql', 'w', encoding='utf-8') as f:
            for line in conn_dañada.iterdump():
                f.write('%s\n' % line)
        
        conn_dañada.close()
        print("Script de recuperación generado correctamente.")

        # Ahora creamos la nueva base de datos y ejecutamos el script
        print(f"Creando {db_nueva}...")
        conn_nueva = sqlite3.connect(db_nueva)
        with open('temp_script.sql', 'r', encoding='utf-8') as f:
            sql_script = f.read()
            conn_nueva.executescript(sql_script)
        
        conn_nueva.close()
        print("¡Proceso finalizado! Revisa si minerva_recuperada.db tiene tus datos.")

    except Exception as e:
        print(f"No se pudo recuperar la base de datos: {e}")

if __name__ == "__main__":
    recuperar_base_datos('minerva.db', 'minerva_recuperada.db')