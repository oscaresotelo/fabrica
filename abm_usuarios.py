import streamlit as st
import sqlite3
import pandas as pd
import bcrypt

# Nombre del archivo de la base de datos
DB_FILE = "minerva.db"

def get_connection():
    """Conexión a la base de datos SQLite."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row  # Permite acceder a las filas como diccionarios
    return conn

def create_users_table():
    """Crea la tabla de usuarios si no existe."""
    conn = get_connection()
    c = conn.cursor()
    # Usamos la misma estructura de tu login.py (tabla 'usuarios')
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            rol TEXT NOT NULL CHECK("rol" IN ('Administrador', 'Operador')),
            PRIMARY KEY("id" AUTOINCREMENT)
        )
    """)
    conn.commit()
    conn.close()

def get_users():
    """Obtiene todos los usuarios de la base de datos."""
    conn = get_connection()
    # No seleccionamos la contraseña por seguridad
    df = pd.read_sql_query("SELECT id, nombre, username, rol FROM usuarios ORDER BY username", conn)
    conn.close()
    return df

def add_user(nombre, username, password, rol):
    """Agrega un nuevo usuario a la base de datos, encriptando la contraseña."""
    # Encriptar la contraseña con bcrypt
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO usuarios (nombre, username, password, rol) VALUES (?, ?, ?, ?)",
                  (nombre, username, password_hash, rol))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        st.error(f"Error: El nombre de usuario '{username}' ya existe.")
        return False
    finally:
        conn.close()

def update_user(user_id, new_nombre, new_username, new_password, new_rol):
    """Actualiza la información de un usuario."""
    conn = get_connection()
    try:
        c = conn.cursor()
        if new_password:
            # Encriptar la nueva contraseña si se proporcionó
            password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
            c.execute("UPDATE usuarios SET nombre = ?, username = ?, password = ?, rol = ? WHERE id = ?",
                      (new_nombre, new_username, password_hash, new_rol, user_id))
        else:
            # Si no hay nueva contraseña, solo actualiza los otros campos
            c.execute("UPDATE usuarios SET nombre = ?, username = ?, rol = ? WHERE id = ?",
                      (new_nombre, new_username, new_rol, user_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        st.error(f"Error: El nombre de usuario '{new_username}' ya existe.")
        return False
    finally:
        conn.close()

def delete_user(user_id):
    """Elimina un usuario por su ID."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True

# --- Interfaz de usuario para la gestión de usuarios ---

def abm_usuarios():
    """Muestra la interfaz para la gestión de usuarios (ABM)."""
    create_users_table()  # Asegura que la tabla exista al cargar la página

    st.title("👥 Administración de Usuarios")

    df_users = get_users()
    
    st.subheader("Lista de Usuarios Existentes")
    if not df_users.empty:
        st.dataframe(df_users, use_container_width=True)
    else:
        st.info("No hay usuarios registrados.")

    st.markdown("---")

    # --- Formulario para Agregar Usuario ---
    st.subheader("➕ Agregar Nuevo Usuario")
    with st.form("add_user_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_nombre = st.text_input("Nombre Completo", key="new_nombre")
            new_username = st.text_input("Nombre de Usuario", key="new_username")
        with col2:
            new_password = st.text_input("Contraseña", type="password", key="new_password")
            
        # Roles ajustados a los de la base de datos
        rol_options = ["Administrador", "Operador"]
        new_rol = st.selectbox("Rol", rol_options, key="new_rol")
        
        submit_add = st.form_submit_button("Crear Usuario")

    if submit_add:
        if new_nombre and new_username and new_password:
            if add_user(new_nombre, new_username, new_password, new_rol):
                st.success(f"Usuario '{new_username}' creado exitosamente.")
                st.rerun()
        else:
            st.error("Por favor, complete todos los campos.")

    st.markdown("---")

    # --- Formulario para Editar y Eliminar Usuario ---
    st.subheader("✏️ Editar o Eliminar Usuario")
    if not df_users.empty:
        user_list = df_users.apply(lambda row: f"{row['username']} (ID: {row['id']})", axis=1).tolist()
        selected_user_str = st.selectbox("Seleccione un Usuario", user_list, key="edit_user_select")
        
        selected_user_id = int(selected_user_str.split('(ID: ')[-1].replace(')', ''))
        selected_user_row = df_users[df_users['id'] == selected_user_id].iloc[0]
        
        with st.form("edit_user_form"):
            col1_edit, col2_edit = st.columns(2)
            with col1_edit:
                edited_nombre = st.text_input("Nombre Completo", value=selected_user_row['nombre'], key="edited_nombre")
                edited_username = st.text_input("Nombre de Usuario", value=selected_user_row['username'], key="edited_username")
            with col2_edit:
                edited_password = st.text_input("Nueva Contraseña (Dejar vacío para no cambiar)", type="password", key="edited_password")
            
            # Roles ajustados a los de la base de datos
            rol_options = ["Administrador", "Operador"]
            edited_rol = st.selectbox("Rol", rol_options, index=rol_options.index(selected_user_row['rol']), key="edited_rol")

            submit_edit = st.form_submit_button("Guardar Cambios")

        # El botón de eliminar se coloca fuera del formulario
        if st.button("Eliminar Usuario", key="delete_button_final"):
            if st.session_state.get("usuario", {}).get("id") == selected_user_id:
                st.error("No puedes eliminar tu propia cuenta de usuario.")
            else:
                delete_user(selected_user_id)
                st.success(f"Usuario '{selected_user_row['username']}' eliminado.")
                st.rerun()

        if submit_edit:
            if edited_nombre and edited_username:
                if update_user(selected_user_id, edited_nombre, edited_username, edited_password, edited_rol):
                    st.success(f"Usuario '{edited_username}' actualizado exitosamente.")
                    st.rerun()
            else:
                st.error("Los campos de nombre y usuario no pueden estar vacíos.")
