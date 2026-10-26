import streamlit as st
from streamlit_option_menu import option_menu

# ------------------------------------------------------------
# CONFIGURACIÓN GENERAL
# ------------------------------------------------------------
st.set_page_config(page_title="Minerva", layout="wide")

# ------------------------------------------------------------
# IMPORTACIÓN DE MÓDULOS PRINCIPALES
# ------------------------------------------------------------
from login import mostrar_login
from dashboard import mostrar_dashboard
from Proceso_Elaboracion import mostrar_proceso_elaboracion  # 👈 Importación del nuevo archivo
from Compras import mostrar_compras
from moduloenvasar import gestionenvasar
from Ventas import ventas
from Stock_Sin_Envasar import mostrar_stock_sin_envasar
from saldos_sin_envasar import modulo_saldos_sin_envasar

# ------------------------------------------------------------
# IMPORTACIÓN DE MÓDULOS ABM
# ------------------------------------------------------------
from abm_clientes import abm_clientes
from abm_proveedores import abm_proveedores
from abm_lineas import abm_lineas
from abm_materias_primas import abm_materias_primas
from abm_envases import abm_envases
from abm_cajas import abm_cajas
from abm_recetas import abm_recetas
from abm_productos import abm_productos
from abm_productos_clientes import abm_productos_clientes
from abm_presentaciones import abm_presentaciones
from abm_usuarios import abm_usuarios
from abm_ingresos_egresos import abm_ingresos_egresos

# ------------------------------------------------------------
# IMPORTACIÓN DE REPORTES Y CONSULTAS
# ------------------------------------------------------------
from Reportes import modulo_reportes
from ConsultaLote import consulta_lote

# ------------------------------------------------------------
# CONTROL DE SESIÓN / LOGIN
# ------------------------------------------------------------
# ⚠️ Control temporal para evitar que la app quede detenida
# Si el login no ha establecido el usuario aún, cargamos uno por defecto
if "usuario" not in st.session_state:
    # Si querés usar el login real, descomentá estas líneas y borrá el bloque siguiente
    # mostrar_login()
    # st.stop()

    # Usuario temporal (para test)
    st.session_state["usuario"] = {"username": "admin", "rol": "Administrador"}

# ------------------------------------------------------------
# MENÚ LATERAL
# ------------------------------------------------------------
with st.sidebar:
    selected = option_menu(
        menu_title="Menú Principal",
        options=[
            "Dashboard", "Proceso Elaboración", "Compras", "Gestionar Envasado",
            "Stock Sin Envasar", "Ventas", "Reportes", "Consulta de Lote",
            "Administración", "Guía de Usuario", "Salir"
        ],
        icons=[
            "house", "gear", "cart", "box-seam", "archive", "currency-dollar",
            "bar-chart", "search", "tools", "book", "box-arrow-right"
        ],
        menu_icon="cast",
        default_index=0,
        orientation="vertical",
        styles={
            "container": {"padding": "5px", "background-color": "#f0f4ff"},
            "icon": {"color": "#d32f2f", "font-size": "20px"},
            "nav-link": {"font-size": "18px", "margin": "2px", "text-align": "left"},
            "nav-link-selected": {"background-color": "#d32f2f", "color": "#fff"},
        }
    )

# ------------------------------------------------------------
# USUARIO EN ESQUINA SUPERIOR DERECHA
# ------------------------------------------------------------
user = st.session_state["usuario"]
st.markdown(
    f"<div style='text-align:right; color:#555; font-size:1.1rem; margin-top:10px;'>"
    f"Usuario: <b>{user.get('username','')}</b> ({user.get('rol','')})"
    f"</div>",
    unsafe_allow_html=True
)

# ------------------------------------------------------------
# CONTENIDO PRINCIPAL SEGÚN SELECCIÓN DEL MENÚ
# ------------------------------------------------------------
if selected == "Dashboard":
    mostrar_dashboard()

elif selected == "Proceso Elaboración":
    mostrar_proceso_elaboracion()  # 👈 Carga el contenido de Proceso_Elaboracion.py

elif selected == "Compras":
    mostrar_compras()

elif selected == "Ventas":
    ventas()

elif selected == "Gestionar Envasado":
    gestionenvasar()

elif selected == "Stock Sin Envasar":
    mostrar_stock_sin_envasar()

elif selected == "Reportes":
    modulo_reportes()

elif selected == "Consulta de Lote":
    consulta_lote()

elif selected == "Administración":
    # Submenú horizontal dentro de la sección Administración
    abm_selected = option_menu(
        menu_title="Administración de Datos Maestros",
        options=[
            "Clientes", "Proveedores", "Líneas", "Materias Primas", "Envases",
            "Cajas", "Recetas", "Productos", "Productos Clientes",
            "Presentaciones", "Usuarios", "Ingresos/Egresos"
        ],
        icons=[
            "person", "truck", "layers", "droplet", "box", "archive",
            "book", "archive", "people", "gift", "person-gear", "cash"
        ],
        menu_icon="tools",
        orientation="horizontal"
    )

    if abm_selected == "Clientes":
        abm_clientes()
    elif abm_selected == "Proveedores":
        abm_proveedores()
    elif abm_selected == "Líneas":
        abm_lineas()
    elif abm_selected == "Materias Primas":
        abm_materias_primas()
    elif abm_selected == "Envases":
        abm_envases()
    elif abm_selected == "Cajas":
        abm_cajas()
    elif abm_selected == "Recetas":
        abm_recetas()
    elif abm_selected == "Productos":
        abm_productos()
    elif abm_selected == "Productos Clientes":
        abm_productos_clientes()
    elif abm_selected == "Presentaciones":
        abm_presentaciones()
    elif abm_selected == "Usuarios":
        abm_usuarios()
    elif abm_selected == "Ingresos/Egresos":
        abm_ingresos_egresos()

elif selected == "Guía de Usuario":
    try:
        with open("manual_sistema.txt", "r", encoding="utf-8") as f:
            manual_text = f.read()
        st.markdown(manual_text)
    except Exception as e:
        st.warning(f"No se pudo cargar la guía de usuario: {e}")

elif selected == "Salir":
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.success("Sesión cerrada. Recarga la página para volver al login.")
    st.rerun()