import streamlit as st
from streamlit_option_menu import option_menu
from produccion import gestionar_produccion  # Asegurate que esta función esté definida en produccion.py
from pedidos import gestionar_pedidos        # Si existe un módulo de pedidos
import time

def mostrar_proceso_elaboracion():
    # Verificar sesión iniciada
    if "usuario" not in st.session_state:
        st.warning("Debe iniciar sesión para acceder a esta sección.")
        st.stop()

    st.markdown("## 🧪 Proceso de Elaboración")
    st.markdown("---")

    # Menú horizontal
    selected = option_menu(
        menu_title=None,
        options=["Guía de Usuario", "Producciones", "Pedidos", "Salir"],
        icons=["book", "gear", "list-task", "box-arrow-right"],
        default_index=0,  # 👈 Inicia mostrando la Guía de Usuario
        orientation="horizontal",
        styles={
            "container": {"padding": "0!important", "background-color": "#f0f2f6"},
            "icon": {"color": "#2C3E50", "font-size": "18px"},
            "nav-link": {
                "font-size": "16px",
                "text-align": "center",
                "margin": "2px",
                "--hover-color": "#EEE",
                "border-radius": "8px",
            },
            "nav-link-selected": {"background-color": "#3498db", "color": "white"},
        },
    )

    # ----------------------------
    # 1️⃣ Guía de usuario
    # ----------------------------
    if selected == "Guía de Usuario":
        st.markdown("### 📘 Guía de Usuario del Módulo de Elaboración")
        st.write(
            """
            Este módulo permite gestionar las etapas de producción y pedidos de productos capilares.

            **Funciones principales:**
            - 🧴 **Producciones**: controla la elaboración de recetas, el consumo de materias primas y la generación de reportes.
            - 📦 **Pedidos**: visualiza y gestiona pedidos en estado *pendiente*, *en proceso* o *producido*.
            - 🚪 **Salir**: vuelve al menú principal del sistema.

            > Solo los usuarios con rol **Administrador** pueden acceder a estas funciones.
            """
        )

    # ----------------------------
    # 2️⃣ Producciones
    # ----------------------------
    elif selected == "Producciones":
        st.markdown("### 🧴 Gestión de Producciones")
        gestionar_produccion()  # Llamada a tu función principal de producción

    # ----------------------------
    # 3️⃣ Pedidos
    # ----------------------------
    elif selected == "Pedidos":
        st.markdown("### 📦 Gestión de Pedidos")
        try:
            gestionar_pedidos()  # Llama a la función de pedidos si existe
        except Exception:
            st.info("⚠️ El módulo de pedidos aún no está disponible.")

    # ----------------------------
    # 4️⃣ Salir
    # ----------------------------
    elif selected == "Salir":
        st.info("Cerrando sesión y volviendo al inicio...")
        time.sleep(1)
        if "usuario" in st.session_state:
            del st.session_state["usuario"]
        st.rerun()
