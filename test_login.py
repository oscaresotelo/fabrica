import streamlit as st
import sqlite3
import bcrypt

# Función para la "página" de la aplicación
def mostrar_app():
    st.title("Bienvenido a la aplicación principal")
    st.write(f"Hola, {st.session_state['usuario']['nombre']}! Has iniciado sesión con éxito.")
    # Aquí iría todo el código de tu app.py

def mostrar_login():
    st.title("Iniciar Sesión")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Ingresar"):
        try:
            conn = sqlite3.connect("minerva.db")
            cursor = conn.cursor()
            cursor.execute("SELECT id, nombre, username, password, rol FROM usuarios WHERE username = ?", (username,))
            user = cursor.fetchone()
            conn.close()
            if user:
                try:
                    password_ok = bcrypt.checkpw(password.encode(), user[3].encode())
                except Exception as e:
                    password_ok = False
                    st.error(f"Error al verificar la contraseña: {e}")
                if password_ok:
                    st.session_state["usuario"] = {
                        "id": user[0],
                        "nombre": user[1],
                        "username": user[2],
                        "rol": user[4]
                    }
                    st.success("Login exitoso.")
                    # Establece un estado para mostrar la app
                    st.session_state["logged_in"] = True
                else:
                    st.error("Usuario o contraseña incorrectos")
            else:
                st.error("Usuario o contraseña incorrectos")
        except sqlite3.Error as e:
            st.error(f"Error al conectar o consultar la base de datos: {e}")

# Lógica principal de la aplicación
if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
    mostrar_login()
else:
    mostrar_app()