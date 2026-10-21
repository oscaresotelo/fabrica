import streamlit as st
import google.generativeai as genai
import os
from dotenv import load_dotenv

# --- 1. Configuración de la API y la página ---

# Cargar la clave de API desde un archivo .env
load_dotenv()
try:
    # Asegúrate de que tu .env tiene GOOGLE_API_KEY="TU_CLAVE"
    GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GOOGLE_API_KEY:
        st.error("No se encontró la clave de API de Gemini. Por favor, asegúrate de que tu archivo .env contiene GOOGLE_API_KEY='TU_CLAVE'.")
        st.stop()
    genai.configure(api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"Error al configurar la API de Gemini: {e}")
    st.stop()

# Configuración de la página
st.set_page_config(
    page_title="Generador de Estrategias de Marketing y Ventas con Gemini",
    page_icon="💡",
    layout="wide"
)

# --- 2. Interfaz de Usuario (UI) y Manejo del Estado ---

st.title("Transforma tu idea en un plan de acción con IA 🚀")
st.markdown("Ingresa tu idea de negocio a continuación y deja que **Gemini** te ayude a crear una estrategia de marketing y ventas completa.")

# Inicializar el historial de conversación en `st.session_state` si no existe
if "messages" not in st.session_state:
    st.session_state.messages = []

# Botón para borrar el historial de la conversación
def clear_history():
    st.session_state.messages = []

st.button("Borrar Historial", on_click=clear_history)

# Mostrar los mensajes del historial
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Campo de entrada para la idea de negocio
idea_de_negocio = st.chat_input("Describe tu idea de negocio:")

if idea_de_negocio:
    # --- 3. Lógica del Prompt Generator y llamada a la API de texto ---
    with st.chat_message("user"):
        st.markdown(idea_de_negocio)
    
    st.session_state.messages.append({"role": "user", "content": idea_de_negocio})

    with st.spinner("Analizando tu idea y creando un plan con la ayuda de Gemini..."):
        
        # --- PROMPT MODIFICADO: AHORA EL PROMPT ES FLEXIBLE ---
        prompt_optimizada = f"""
        Actúa como un consultor de negocios y marketing que es altamente adaptable y experto en el mercado argentino. Tu objetivo es crear un plan de negocios completo y, al mismo tiempo, responder directamente a cualquier solicitud adicional que el cliente haga.
        Basado en la siguiente idea de negocio: '{idea_de_negocio}', realiza un análisis **FODA** (explica qué significa cada sigla) y genera un plan de marketing y ventas completo. Las respuestas deben ser creativas, pero realistas y adaptadas al mercado argentino. La respuesta debe estar estructurada en las siguientes secciones, usando markdown para su formato:

        ---
        ## Plan de Estrategia de Marketing y Ventas
        ---
        
        ### Sugerencias Específicas y Respuestas a tus Preguntas
        Analiza la solicitud del cliente y, si hay preguntas o pedidos que no encajan en las otras categorías (como sugerir nombres, ideas para logos, etc.), respóndelos aquí de forma directa y creativa. Si no hay solicitudes adicionales, simplemente escribe 'No se detectaron solicitudes adicionales.'

        ### Análisis de Público Objetivo (Buyer Persona)
        Explica de forma simple qué es un **Buyer Persona** y por qué es tan importante. Luego, crea 3 perfiles de clientes ideales detallados para este negocio.

        ### Estrategias de Marketing Digital
        Propón 5 acciones concretas para redes sociales (Instagram, Pinterest), email marketing y **SEO**. Explica qué es el SEO y por qué te ayuda a ser visible en internet.

        ### Estrategias de Marketing Convencional
        Sugiere 3 ideas para marketing offline (eventos, colaboraciones, ferias, etc.).

        ### Estrategias de Venta Digital
        Explica qué es un **Embudo de Ventas Digital** y cómo funciona. Luego, detalla uno para esta idea de negocio y menciona las herramientas a usar (tienda online, marketplaces).

        ### Estrategias de Venta Convencional
        Plantea 2 modelos de venta en persona (puntos de venta, ferias de artesanía).

        ### Prompt para Imagen Publicitaria
        Genera un prompt detallado, creativo y visual para una imagen publicitaria de alta calidad. El prompt debe ser directo, sin explicaciones, listo para ser usado en una herramienta como Midjourney o DALL-E. No uses texto sobre la imagen.
        
        ### Métricas Clave (KPIs)
        Explica qué son los **KPIs** y por qué son cruciales para saber si un negocio está funcionando. Luego, enumera 3 indicadores de éxito para monitorear el desempeño del plan.
        """
        
        try:
            # Llamar al modelo de Gemini para generar el plan de marketing
            model_text = genai.GenerativeModel('gemini-2.0-flash')
            response_text = model_text.generate_content(prompt_optimizada)
            
            # --- 4. Mostrar la respuesta y el prompt de la imagen ---
            full_response_text = response_text.text
            
            # Extraer el prompt de la imagen del texto completo
            image_prompt_start_marker = "### Prompt para Imagen Publicitaria"
            image_prompt_end_marker = "### Métricas Clave (KPIs)"
            
            if image_prompt_start_marker in full_response_text and image_prompt_end_marker in full_response_text:
                start_index = full_response_text.find(image_prompt_start_marker) + len(image_prompt_start_marker)
                end_index = full_response_text.find(image_prompt_end_marker)
                
                image_prompt = full_response_text[start_index:end_index].strip()
                main_response_text = full_response_text[:start_index] + full_response_text[end_index:]
            else:
                image_prompt = "No se pudo extraer un prompt de imagen específico."
                main_response_text = full_response_text

            with st.chat_message("assistant"):
                st.markdown(main_response_text)
                
            st.markdown("---")
            st.subheader("🖼️ Prompt para generar tu Imagen Publicitaria")
            st.info(image_prompt)
            st.markdown("Copia este texto y úsalo en tu generador de imágenes de IA favorito (como Midjourney, DALL-E, etc.).")
            
            st.session_state.messages.append({"role": "assistant", "content": full_response_text})

        except Exception as e:
            st.error(f"Ocurrió un error al generar la estrategia: {e}")