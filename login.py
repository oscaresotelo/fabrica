import streamlit as st
import sqlite3
import bcrypt
import os

def mostrar_login():
    st.title("Iniciar Sesión")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    
    if st.button("Ingresar"):
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
                st.success("Login exitoso. Redirigiendo...")

                # Redirigir a app.py
                st.switch_page("app.py")
            else:
                st.error("Usuario o contraseña incorrectos")
        else:
            st.error("Usuario o contraseña incorrectos")

# Ejecutar la función principal si se abre este archivo directamente
if __name__ == "__main__":
    mostrar_login()
