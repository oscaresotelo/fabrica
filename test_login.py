import streamlit as st
import sqlite3
import bcrypt

# Configuración inicial de la página
st.set_page_config(page_title="Minerva - Sistema Integral", layout="wide")

def mostrar_login():
    """Pantalla de Inicio de Sesión"""
    st.title("🧪 Minerva - Iniciar Sesión")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("form_login"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submit_login = st.form_submit_button("Ingresar", use_container_width=True)

            if submit_login:
                try:
                    conn = sqlite3.connect("minerva.db")
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, nombre, username, password, rol FROM usuarios WHERE username = ?", (username,))
                    user = cursor.fetchone()
                    conn.close()
                    
                    if user:
                        try:
                            password_ok = bcrypt.checkpw(password.encode(), user[3].encode())
                        except Exception:
                            password_ok = False
                        
                        if password_ok:
                            st.session_state["usuario"] = {
                                "id": user[0],
                                "nombre": user[1],
                                "username": user[2],
                                "rol": user[4]
                            }
                            st.session_state["logged_in"] = True
                            st.rerun()
                        else:
                            st.error("Usuario o contraseña incorrectos")
                    else:
                        st.error("Usuario o contraseña incorrectos")
                except sqlite3.Error as e:
                    st.error(f"Error al conectar con la base de datos: {e}")

def mostrar_selector_modulos():
    """Pantalla intermedia con los dos botones de selección de módulo"""
    usuario_actual = st.session_state["usuario"]["nombre"]
    
    st.title(f"👋 ¡Bienvenido, {usuario_actual}!")
    st.markdown("### Seleccioná el módulo al que deseás ingresar:")
    st.markdown("---")
    
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        st.info("📦 **Módulo de Producción**\n\nControl de recetas, stock, lotes y operaciones de planta.")
        if st.button("🚀 Producción", use_container_width=True, type="primary"):
            st.session_state["modulo_activo"] = "produccion"
            st.rerun()
            
    with col_btn2:
        st.success("💰 **Módulo Contable**\n\nGestión de pagos de revendedores, imputaciones y trazabilidad de OC.")
        if st.button("📊 Contable", use_container_width=True, type="primary"):
            st.session_state["modulo_activo"] = "contable"
            st.rerun()
            
    st.markdown("---")
    if st.button("Cerrar Sesión"):
        st.session_state.clear()
        st.rerun()

def main():
    # Inicializar estados si no existen
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "modulo_activo" not in st.session_state:
        st.session_state["modulo_activo"] = None

    # 1. Si no está logueado, mostrar login
    if not st.session_state["logged_in"]:
        mostrar_login()
    
    # 2. Si está logueado pero no eligió módulo, mostrar los botones
    elif st.session_state["modulo_activo"] is None:
        mostrar_selector_modulos()
        
    # 3. Si eligió un módulo, cargar la página correspondiente mediante st.navigation
    else:
        # Botón lateral para volver a la selección de módulos
        if st.sidebar.button("⬅️ Cambiar de Módulo"):
            st.session_state["modulo_activo"] = None
            st.rerun()
            
        # Definición de páginas usando el sistema nativo de Streamlit
        paginas = {
            "Producción": [
                st.Page("app.py", title="Panel de Producción", icon="📦")
            ],
            "Contable": [
                st.Page("cargapagosclientes.py", title="Gestión Contable y Pagos", icon="💰")
            ]
        }
        
        if st.session_state["modulo_activo"] == "produccion":
            pg = st.navigation(paginas["Producción"])
        else:
            pg = st.navigation(paginas["Contable"])
            
        pg.run()

if __name__ == "__main__":
    main()