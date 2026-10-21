import streamlit as st
from streamlit_option_menu import option_menu
from login import mostrar_login
from Ordenes_de_Envasado import ordenes_envasado
from Envasar import envasar

def mostrar_manual_envasado():
    try:
        with open("manualenvasado.txt", "r", encoding="utf-8") as f:
            manual_text = f.read()
        with st.expander("📖 Manual de Usuario: Órdenes de Envasado y Envasar", expanded=False):
            st.markdown(manual_text)
    except Exception as e:
        st.warning(f"No se pudo cargar el manual de usuario: {e}")

# Llama a la función donde quieras mostrar el manual


def gestionenvasar():
    # --- LOGIN ---
    if "usuario" not in st.session_state:
        mostrar_login()
        st.stop()

    # --- MENÚ SUPERIOR CON OPTION_MENU ---
    with st.container():
        selected = option_menu(
            menu_title=None,  # Sin título
            options=["Guia de Usuario", "Ordenes de Envasado", "Envasar", "Salir"],
            icons=["book", "list-task", "list-task", "box-arrow-right"],
            orientation="horizontal",
            styles={
                "container": {"padding": "0!important", "background-color": "#d32f2f"},
                "icon": {"color": "#fff", "font-size": "20px"},
                "nav-link": {
                    "font-size": "18px",
                    "color": "#fff",
                    "font-weight": "bold",
                    "margin": "0 10px",
                },
                "nav-link-selected": {"background-color": "#fff", "color": "#2d3eec"},
            }
        )

    # --- CONTENIDO SEGÚN SELECCIÓN ---
    if selected == "Guia de Usuario":
        st.markdown("<h2 style='margin-top:1.5rem;'>Guia de Usuario</h2>", unsafe_allow_html=True)
        mostrar_manual_envasado()

    elif selected == "Ordenes de Envasado":
        ordenes_envasado()
    elif selected == "Envasar":

        envasar()
    elif selected == "Salir":
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.success("Sesión cerrada. Recarga la página para volver al login.")
        st.rerun()
