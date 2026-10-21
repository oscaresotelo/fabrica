import streamlit as st
from login import mostrar_login

def main():
    if "usuario" not in st.session_state:
        mostrar_login()
    else:
        st.switch_page("app.py")  # o cualquier otra página principal

if __name__ == "__main__":
    main()
