import streamlit as st
import sqlite3
import re
import pandas as pd

DB_PATH = "minerva.db"

def formatear_procedimiento_con_saltos(texto_sucio):
    """
    Limpia el texto y asegura que después de cada fila de datos 
    exista un salto de línea para que el PDF no encime las líneas.
    """
    texto_limpio = re.sub(r'\|{2,}', '|', texto_sucio)
    lineas = texto_limpio.strip().split('\n')
    lineas_procesadas = []
    
    for linea in lineas:
        linea = linea.strip()
        if not linea: continue

        titulos_seccion = ["BITÁCORA", "CONTROL DE CALIDAD", "CIERRE", "LIBERACIÓN", "FIRMAS"]
        if any(titulo in linea.upper() for titulo in titulos_seccion):
            lineas_procesadas.append(f"\n{linea.replace('|', '').strip()}\n")
            continue

        if '\t' in linea: partes = linea.split('\t')
        elif '|' in linea: partes = linea.split('|')
        else: partes = re.split(r'\s{2,}', linea)

        partes = [p.strip() for p in partes if p.strip() != ""]
        while len(partes) < 5: partes.append(" ")
            
        fila_formateada = " | ".join(partes[:5])
        lineas_procesadas.append(fila_formateada)
        lineas_procesadas.append("  |   |   |   |  ") 

    return "\n".join(lineas_procesadas)

def interfaz_procedimientos():
    st.set_page_config(page_title="Editor de Recetas", layout="wide")
    st.title("🧪 Editor de Procedimientos")
    st.markdown("---")

    # 1. Cargar Datos
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Traemos los datos a un DataFrame de Pandas
            df = pd.read_sql_query("SELECT id, nombre, procedimientos FROM recetas ORDER BY nombre", conn)
    except Exception as e:
        st.error(f"Error de base de datos: {e}")
        return

    # 2. Selector mediante Dataframe
    st.subheader("1. Selecciona un producto de la lista")
    
    # Configuramos la selección en el dataframe
    event = st.dataframe(
        df[['id', 'nombre']], 
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    # Obtener la fila seleccionada
    indices_seleccionados = event.selection.rows
    
    if indices_seleccionados:
        # Extraer datos de la fila seleccionada
        idx = indices_seleccionados[0]
        id_receta = df.iloc[idx]['id']
        nombre_receta = df.iloc[idx]['nombre']
        procedimiento_actual = df.iloc[idx]['procedimientos']

        st.markdown(f"### Editando: **{nombre_receta}** (ID: {id_receta})")
        
        # 3. Área de Edición
        procedimiento_input = st.text_area(
            "Pega o edita el procedimiento aquí:",
            value=procedimiento_actual if procedimiento_actual else "",
            height=400
        )

        if st.button("💾 Guardar Cambios con Auto-Enters", type="primary", use_container_width=True):
            texto_listo = formatear_procedimiento_con_saltos(procedimiento_input)
            
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute(
                        "UPDATE recetas SET procedimientos = ? WHERE id = ?",
                        (texto_listo, int(id_receta))
                    )
                    conn.commit()
                
                st.success(f"✅ ¡Guardado con éxito! El procedimiento de '{nombre_receta}' ha sido actualizado.")
                st.rerun() # Refrescar para ver cambios si fuera necesario
                    
            except Exception as e:
                st.error(f"Error al guardar: {e}")
    else:
        st.info("💡 Por favor, haz clic en una fila de la tabla de arriba para empezar a editar.")

if __name__ == "__main__":
    interfaz_procedimientos()