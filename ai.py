import streamlit as st
import google.generativeai as genai
import io
import traceback
from google.api_core import exceptions

# --- Configuración de la Página ---
st.set_page_config(page_title="COPILOT DE OSCAR", layout="wide", page_icon="⚡")

# --- Configuración de la API ---
# Nota: Asegúrate de que tu API Key sea válida para modelos 1.5
API_KEY = "AIzaSyABFNeXQMQNy-MFlPf9818zmFn5wnuFZHc" 

try:
    genai.configure(api_key=API_KEY)
except Exception as e:
    st.error(f"Error de configuración: {e}")
    st.stop()

# --- PROMPT DEL AGENTE ---
BASE_PROMPT = """
### 🕵️‍♀️ Agente de Programación — "Códex Gemini 1.5"
Eres un experto en desarrollo de software. Tu prioridad es el código limpio, 
seguro y funcional. Analiza el contexto de los archivos proporcionados 
y responde a las dudas del usuario con precisión técnica.
"""

# --- Inicialización del Modelo Gemini 1.5 Flash ---
@st.cache_resource
def get_gemini_model():
    return genai.GenerativeModel(
        model_name='gemini-1.5-flash', # Cambio a versión estable 1.5
        system_instruction=BASE_PROMPT
    )

model = get_gemini_model()

# --- Gestión del historial ---
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("⚡ COPILOT DE OSCAR (Gemini 1.5 Flash)")

# Renderizar historial
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["parts"][0]["text"])

# --- Sidebar ---
st.sidebar.header("📁 Contexto del Proyecto")
uploaded_sql_file = st.sidebar.file_uploader("Esquema de Base de Datos (.sql)", type=["sql"])
uploaded_py_files = st.sidebar.file_uploader("Scripts de Python (.py)", type=["py"], accept_multiple_files=True)

if st.sidebar.button("🗑️ Reiniciar Chat"):
    st.session_state.messages = []
    st.rerun()

# --- Entrada de usuario ---
user_query = st.chat_input("¿Qué código revisamos hoy?")

if user_query:
    st.session_state.messages.append({"role": "user", "parts": [{"text": user_query}]})
    with st.chat_message("user"):
        st.markdown(user_query)

    # Preparar el contexto de archivos
    context_files = ""
    if uploaded_py_files:
        for f in uploaded_py_files:
            context_files += f"\n--- ARCHIVO: {f.name} ---\n```python\n{f.getvalue().decode()}\n```"
    
    if uploaded_sql_file:
        context_files += f"\n--- SCHEMA SQL ---\n```sql\n{uploaded_sql_file.getvalue().decode()}\n```"

    # Prompt final para este turno
    prompt_final = f"{context_files}\n\nPREGUNTA DEL USUARIO: {user_query}" if context_files else user_query

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        try:
            # Iniciamos sesión de chat con el historial acumulado
            chat_session = model.start_chat(history=st.session_state.messages[:-1])
            response_generator = chat_session.send_message(prompt_final, stream=True)

            for chunk in response_generator:
                if chunk.text:
                    full_response += chunk.text
                    response_placeholder.markdown(full_response + "▌")
            
            response_placeholder.markdown(full_response)
            
            # Guardar respuesta final en historial
            st.session_state.messages.append({"role": "assistant", "parts": [{"text": full_response}]})

        except exceptions.ResourceExhausted:
            st.warning("⚠️ **Límite de cuota alcanzado.** Gemini 1.5 Flash (Free) tiene un límite de peticiones por minuto. Por favor, espera unos 60 segundos.")
        except Exception as e:
            st.error(f"❌ Error inesperado: {e}")
            st.expander("Traza del error").code(traceback.format_exc())