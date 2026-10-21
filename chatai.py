import streamlit as st
import google.generativeai as genai
import io
import traceback
import os
import base64

# --- Configuración de la API ---
API_KEY = "AIzaSyABFNeXQMQNy-MFlPf9818zmFn5wnuFZHc"  # Cambia por tu clave o usa st.secrets
try:
    genai.configure(api_key=API_KEY)
except Exception as e:
    st.error(f"Error al configurar la clave de API. Verifica tu clave: {e}")
    st.stop()

st.set_page_config(page_title="Copilot de Oscar", layout="wide")
st.title("🕵️‍♀️ Copilot de Oscar")

# --- Prompt optimizado ---
BASE_PROMPT = """
### 🕵️‍♀️ Códex Gemini - Copilot de Oscar

**Rol:** Agente experto en Python, SQL, Streamlit y buenas prácticas. Analiza código, esquemas de BD y peticiones para entregar soluciones completas.

**Flujo de trabajo:**
1. Analizar contexto: código, SQL y petición.
2. Determinar tipo de respuesta:
   - Código completo si se solicita explícitamente.
   - Explicación detallada si es conceptual.
   - Diagnóstico y preguntas si es ambiguo.
3. Generar respuesta:
   - Markdown profesional con bloques de código etiquetados.
   - Explicación breve del "por qué" del código.
   - Validación mental para evitar errores.

**Directrices clave:**
- Siempre entrega solución completa y funcional.
- Validación defensiva de tipos (listas, DataFrames, diccionarios).
- Adaptabilidad y claridad en la explicación.
"""

# --- Inicialización del modelo Gemini ---
@st.cache_resource
def get_gemini_model():
    return genai.GenerativeModel('gemini-2.0-flash')

model = get_gemini_model()

# --- Inicialización del historial ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": BASE_PROMPT}]

# Mostrar historial previo
for message in st.session_state.messages:
    role = message["role"]
    content = message.get("content", "")
    with st.chat_message(role):
        st.markdown(content)

# --- Sidebar: carga de archivos ---
st.sidebar.header("📂 Cargar Archivos")
uploaded_sql_file = st.sidebar.file_uploader("Archivo .sql", type=["sql"])
uploaded_py_files = st.sidebar.file_uploader("Archivos .py", type=["py"], accept_multiple_files=True)

if st.sidebar.button("🗑️ Borrar Conversación"):
    st.session_state.messages = [{"role": "system", "content": BASE_PROMPT}]
    st.rerun()

# --- Entrada de usuario ---
user_query = st.chat_input("Escribe tu petición, pregunta o código aquí...")

if user_query:
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    # --- Preparar contexto para Gemini ---
    full_context = BASE_PROMPT + "\n\n**Petición del usuario:**\n" + user_query

    # Adjuntar archivos de forma segura y limitada
    if uploaded_py_files:
        for py_file in uploaded_py_files:
            try:
                py_content = py_file.getvalue().decode("utf-8")
                if len(py_content) > 10000:
                    py_content = py_content[:10000] + "\n# ...Archivo truncado por tamaño..."
                full_context += f"\n\n---Código {py_file.name}---\n```python\n{py_content}\n```\n---"
            except Exception as e:
                st.warning(f"⚠️ Error al leer {py_file.name}: {e}")

    if uploaded_sql_file:
        try:
            sql_content = uploaded_sql_file.getvalue().decode("utf-8")
            if len(sql_content) > 10000:
                sql_content = sql_content[:10000] + "\n-- ...Archivo truncado por tamaño..."
            full_context += f"\n\n---Esquema SQL---\n```sql\n{sql_content}\n```\n---"
        except Exception as e:
            st.warning(f"⚠️ Error al leer el archivo SQL: {e}")

    # --- Generar respuesta ---
    with st.chat_message("assistant"):
        with st.spinner("🚀 Analizando y generando la respuesta..."):
            try:
                chat_session = model.start_chat(history=st.session_state.messages)
                response_generator = chat_session.send_message(full_context, stream=True)

                full_response_text = ""
                response_placeholder = st.empty()

                for chunk in response_generator:
                    text = getattr(chunk, "text", None)
                    if text:
                        full_response_text += text
                        response_placeholder.markdown(full_response_text)

                # Guardar archivo .txt al final
                output_file = "respuesta_completa.txt"
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(full_response_text)

                # Crear enlace de descarga
                with open(output_file, "rb") as file:
                    b64 = base64.b64encode(file.read()).decode()
                href = f'<a href="data:file/txt;base64,{b64}" download="{output_file}">📥 Descargar respuesta completa</a>'
                st.markdown(href, unsafe_allow_html=True)

                st.success(f"✅ Respuesta guardada en '{output_file}'")
                st.session_state.messages.append({"role": "assistant", "content": full_response_text})

            except Exception as e:
                st.error(f"❌ Error al procesar la petición: {e}")
                st.error(traceback.format_exc())

    st.rerun()

st.markdown("---")
st.markdown("💡 Asistente de Programación AI - Copilot de Oscar")
