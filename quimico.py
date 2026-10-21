import streamlit as st
import google.generativeai as genai
import io
import traceback
import os
import base64
from PyPDF2 import PdfReader  # 👈 Librería para leer PDFs

# --- Configuración de la API ---
API_KEY = "AIzaSyABFNeXQMQNy-MFlPf9818zmFn5wnuFZHc"  # Usa st.secrets en despliegue real
try:
    genai.configure(api_key=API_KEY)
except Exception as e:
    st.error(f"Error al configurar la clave de API. Por favor, verifica tu clave: {e}")
    st.stop()

st.title("📄 COPILOT DE OSCAR — Lectura de PDFs")

# --- PROMPT DEL AGENTE ---
BASE_PROMPT = """
### 🧪 Agente Químico Capilar — "Códex Minerva"

**Rol y Propósito:**  
Eres un asistente experto en **química cosmética capilar**, especializado en la formulación, fabricación y control de calidad de productos capilares (shampoo, acondicionadores, tratamientos, máscaras, keratinas, etc.).  
Tu objetivo es analizar y extraer conocimiento de los documentos PDF proporcionados para ayudar al usuario a resolver dudas y diseñar procesos seguros, eficaces y alineados con buenas prácticas de manufactura (BPM).

---

### 🧠 Alcance del conocimiento:
- Formulación de productos capilares (ingredientes, proporciones, excipientes, activos y conservantes).  
- Procesos de fabricación (orden de mezcla, temperatura, pH, tiempos de agitación, control de viscosidad, etc.).  
- Normativas y regulaciones aplicables en cosmética capilar.  
- Seguridad en el manejo de materias primas químicas.  
- Innovaciones y tendencias en productos capilares.  

---

### 🎯 Directrices de respuesta:
1. Siempre responde con un **enfoque técnico y práctico**.  
2. Cuando hables de formulaciones, indica tanto la **lógica técnica** como posibles **precauciones de seguridad**.  
3. Si una información no está explícita en los PDFs, indica que debe confirmarse con bibliografía especializada o normativas locales.  
4. Usa explicaciones claras y estructuradas, con pasos o listas cuando sea necesario.  
5. Si la pregunta es sobre un proceso, explica el **por qué** de cada paso, no solo el “cómo”.  

---

### Ejemplo de interacción:
**Usuario:** ¿Cuál es el mejor conservante para un shampoo natural?  
**Códex Minerva:** Explicaría las opciones de conservantes naturales, su rango de pH compatible, dosis recomendada, ventajas y limitaciones, además de advertir sobre compatibilidades y normativas.

---
"""


# --- Inicialización del Modelo Gemini ---
@st.cache_resource
def get_gemini_model():
    return genai.GenerativeModel('gemini-2.0-flash')

model = get_gemini_model()

# --- Gestión del historial ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if "parts" in message and "text" in message["parts"][0]:
            st.markdown(message["parts"][0]["text"])
        else:
            st.markdown(message["content"])

# --- Sidebar ---
st.sidebar.header("📂 Cargar PDFs")
uploaded_pdfs = st.sidebar.file_uploader("Sube archivos PDF", type=["pdf"], accept_multiple_files=True)

if st.sidebar.button("🗑️ Borrar Conversación Actual"):
    st.session_state.messages = []
    st.rerun()

# --- Entrada de usuario ---
user_query = st.chat_input("Escribe tu petición, pregunta o consulta sobre los PDFs...")

if user_query:
    st.session_state.messages.append({"role": "user", "parts": [{"text": user_query}]})
    with st.chat_message("user"):
        st.markdown(user_query)

    full_context_for_gemini = BASE_PROMPT

    # Procesar los PDFs cargados
    if uploaded_pdfs:
        for pdf_file in uploaded_pdfs:
            try:
                pdf_reader = PdfReader(pdf_file)

                # 👇 Verificar si está cifrado
                if pdf_reader.is_encrypted:
                    try:
                        pdf_reader.decrypt("")  # intenta abrir sin contraseña
                    except Exception:
                        st.warning(f"⚠️ El PDF {pdf_file.name} está cifrado y requiere contraseña. No se pudo leer.")
                        continue

                pdf_text = ""
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        pdf_text += page_text + "\n"

                if pdf_text.strip():
                    full_context_for_gemini += f"\n\n---Contenido del PDF: {pdf_file.name}---\n{pdf_text}\n---"
                else:
                    st.warning(f"⚠️ No se pudo extraer texto del PDF {pdf_file.name}. Puede ser un escaneo o estar protegido.")

            except Exception as e:
                st.warning(f"⚠️ Error al leer el PDF {pdf_file.name}: {e}")

    full_context_for_gemini += f"\n\n**Petición del usuario:**\n" + user_query

    with st.chat_message("assistant"):
        with st.spinner("🚀 Copilot de Minerva está analizando los PDFs y generando respuesta..."):
            try:
                chat_session = model.start_chat(history=st.session_state.messages)
                response_generator = chat_session.send_message(full_context_for_gemini, stream=True)

                output_file = "respuesta_completa.txt"
                if os.path.exists(output_file):
                    os.remove(output_file)

                response_placeholder = st.empty()
                full_response_text = ""

                with open(output_file, "a", encoding="utf-8") as f:
                    for chunk in response_generator:
                        if chunk.text:
                            full_response_text += chunk.text
                            f.write(chunk.text)
                            response_placeholder.markdown(full_response_text)

                # Crear enlace de descarga
                with open(output_file, "rb") as file:
                    b64 = base64.b64encode(file.read()).decode()
                href = f'<a href="data:file/txt;base64,{b64}" download="{output_file}">📥 Descargar respuesta completa</a>'
                st.markdown(href, unsafe_allow_html=True)

                st.success(f"✅ Respuesta completa guardada en '{output_file}'")
                st.session_state.messages.append({"role": "assistant", "parts": [{"text": full_response_text}]})

            except Exception as e:
                st.error(f"❌ Error al procesar la petición: {e}")
                st.error(traceback.format_exc())

    st.rerun()

st.markdown("---")
st.markdown("👨‍💻 Asistente AI  — basado en conocimiento de PDFs")
