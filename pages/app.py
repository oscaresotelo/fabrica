import streamlit as st
from streamlit_option_menu import option_menu

# Importa los módulos principales
from login import mostrar_login
from dashboard import mostrar_dashboard
from Proceso_Elaboracion import mostrar_proceso_elaboracion
from Compras import mostrar_compras
from moduloenvasar import gestionenvasar
from Ventas import ventas
from Stock_Sin_Envasar import mostrar_stock_sin_envasar
from saldos_sin_envasar import modulo_saldos_sin_envasar
from abm_ingresos_egresos import abm_categorias
     
# Importa los ABM
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
from abm_revendedores import abm_revendedores

# Importa el nuevo módulo de gestión de cobranza
from gestion_cobranza import mostrar_gestion_cobranza 

# Importa módulo de reportes y consulta de lote
from Reportes import modulo_reportes
from ConsultaLote import consulta_lote

# Configuración general
#st.set_page_config(page_title="Minerva", layout="wide")

# --- LOGIN ---
if "usuario" not in st.session_state:
    mostrar_login()
    st.stop()

# --- MENÚ LATERAL IZQUIERDO ---
with st.sidebar:
    selected = option_menu(
        menu_title="Menú Principal",
        options=[
            "Dashboard", "Proceso Elaboración", "Compras", "Gestionar Envasado",
            "Stock Sin Envasar", "Ventas", "Reportes", "Consulta de Lote", "Administración", "Gestión de Cobranza", "Guía de Usuario", "Salir"
        ],
        icons=[
            "house", "gear", "cart", "box-seam", "archive", "currency-dollar",
            "bar-chart", "search", "tools", "cash-coin", "book", "box-arrow-right"
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

# --- USUARIO ARRIBA A LA DERECHA ---
user = st.session_state["usuario"]
st.markdown(
    f"<div style='text-align:right; color:#888; font-size:1.1rem; margin-top:10px;'>Usuario: <b>{user.get('username','')}</b> ({user.get('rol','')})</div>",
    unsafe_allow_html=True
)

# --- CONTENIDO SEGÚN SELECCIÓN ---
if selected == "Dashboard":
    mostrar_dashboard()
elif selected == "Proceso Elaboración":
    mostrar_proceso_elaboracion()
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
    abm_selected = option_menu(
        menu_title="Administración de Datos Maestros",
        options=[
            "Clientes", "Proveedores", "Revendedores", "Líneas", "Materias Primas", "Envases",
            "Cajas", "Recetas", "Productos", "Productos Clientes", "Presentaciones", "Usuarios","Ingresos/Egresos" 
        ],
        icons=[
            "person", "truck", "person-badge", "layers", "droplet", "box",
            "archive", "book", "archive", "people", "gift", "person-gear"
        ],
        menu_icon="tools",
        orientation="horizontal"
    )
    if abm_selected == "Clientes":
        abm_clientes()
    elif abm_selected == "Proveedores":
        abm_proveedores()
    elif abm_selected == "Revendedores": 
        abm_revendedores()
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
        abm_categorias()

elif selected == "Gestión de Cobranza":
    mostrar_gestion_cobranza()
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