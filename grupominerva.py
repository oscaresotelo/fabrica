import streamlit as st
import pandas as pd
from datetime import datetime, date

# Configuración de página con diseño ancho y tema profesional
st.set_page_config(
    page_title="Control de Caja y Trazabilidad - Bekim",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo personalizado para un diseño premium y limpio (light/dark adaptive)
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.1rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .card {
        background-color: #F3F4F6;
        padding: 1.2rem;
        border-radius: 0.6rem;
        border-left: 5px solid #3B82F6;
        margin-bottom: 1rem;
    }
    .whatsapp-box {
        background-color: #E8F5E9;
        border-left: 5px solid #2E7D32;
        padding: 1rem;
        font-family: monospace;
        white-space: pre-wrap;
        border-radius: 0.4rem;
    }
</style>
""", unsafe_allow_html=True)

# =====================================================================
# INICIALIZACIÓN DE DATOS (Pre-carga histórica en Session State)
# =====================================================================

if 'facturas' not in st.session_state:
    st.session_state.facturas = pd.DataFrame([
        {
            "id_factura": "SI2605-1138",
            "proveedor": "Bekim Cosmética",
            "monto_original": 2310880.00,
            "saldo_pendiente": 0.00,
            "estado": "PAGADA",
            "fecha": "2026-05-27",
            "detalle": "Saldada el 08/06/2026 con remanente de Gerardo Montano"
        },
        {
            "id_factura": "SI2606-1145",
            "proveedor": "Acordes Aromáticos",
            "monto_original": 32806100.00,
            "saldo_pendiente": 29094895.46,
            "estado": "PAGO PARCIAL",
            "fecha": "2026-06-03",
            "detalle": "Registra abonos de Montano, Lote Acordes y Guzmán"
        },
        {
            "id_factura": "Cuenta Corriente 1",
            "proveedor": "Acordes Aromáticos",
            "monto_original": 243108.00,
            "saldo_pendiente": 0.00,
            "estado": "PAGADA",
            "fecha": "2026-06-08",
            "detalle": "Saldada de forma directa por Gerardo Montano"
        }
    ])

if 'transacciones' not in st.session_state:
    st.session_state.transacciones = pd.DataFrame([
        # Pagos asignados a Acordes Cta 2 / Factura 1145
        {"fecha": "2026-06-08", "hora": "11:37", "origen": "Franco Monti", "banco": "Mercado Pago", "destino": "Daniela Ferron", "monto": 500000.00, "factura_afectada": "SI2606-1145", "lote": "Lote Acordes Cta 2"},
        {"fecha": "2026-06-08", "hora": "13:53", "origen": "Norma M. Mana", "banco": "BANCOR", "destino": "Daniela Ferron", "monto": 280000.00, "factura_afectada": "SI2606-1145", "lote": "Lote Acordes Cta 2"},
        {"fecha": "2026-06-08", "hora": "16:27", "origen": "Monti Marcelo F.", "banco": "BBVA", "destino": "Daniela Ferron", "monto": 328243.00, "factura_afectada": "SI2606-1145", "lote": "Lote Acordes Cta 2"},
        {"fecha": "2026-06-08", "hora": "16:28", "origen": "Marcelo F. Monti", "banco": "Mercado Pago", "destino": "Daniela Ferron", "monto": 350000.00, "factura_afectada": "SI2606-1145", "lote": "Lote Acordes Cta 2"},
        {"fecha": "2026-06-08", "hora": "16:30", "origen": "Ajuste de Lote", "banco": "Interno", "destino": "Daniela Ferron", "monto": 350000.00, "factura_afectada": "SI2606-1145", "lote": "Lote Acordes Cta 2"},
        
        # Pagos directos / Splits
        {"fecha": "2026-06-08", "hora": "14:25", "origen": "Gladys B. Cerchi", "banco": "Mercado Pago", "destino": "Mary Sol Parra", "monto": 140000.00, "factura_afectada": "N/A (Mary Sol Parra)", "lote": "Ninguno"},
        {"fecha": "2026-06-08", "hora": "14:26", "origen": "Gerardo M. Montano", "banco": "Mercado Pago", "destino": "Mary Sol Parra", "monto": 480708.46, "factura_afectada": "SI2605-1138", "lote": "Split Montano"},
        {"fecha": "2026-06-08", "hora": "14:26", "origen": "Gerardo M. Montano", "banco": "Mercado Pago", "destino": "Mary Sol Parra", "monto": 379291.54, "factura_afectada": "SI2606-1145", "lote": "Split Montano"},
        {"fecha": "2026-06-08", "hora": "14:30", "origen": "Gerardo M. Montano", "banco": "Mercado Pago", "destino": "Acordes S.R.L.", "monto": 243108.00, "factura_afectada": "Cuenta Corriente 1", "lote": "Ninguno"},
        
        # Pagos a Guzmán (Factura 1145)
        {"fecha": "2026-06-09", "hora": "11:21", "origen": "Néstor O. Castillo", "banco": "Bco. Macro", "destino": "J. Manuel Guzmán", "monto": 1000000.00, "factura_afectada": "SI2606-1145", "lote": "Lote Guzmán"},
        {"fecha": "2026-06-09", "hora": "12:47", "origen": "Franco Monti", "banco": "Mercado Pago", "destino": "J. Manuel Guzmán", "monto": 523670.00, "factura_afectada": "SI2606-1145", "lote": "Lote Guzmán"}
    ])

if 'pendientes' not in st.session_state:
    st.session_state.pendientes = pd.DataFrame([
        {"id_pendiente": 1, "concepto": "Pago a Santiago (Belo)", "monto": 1139925.58, "estado": "Esperando Comprobante", "destinatario": "Santiago (BBVA)", "prioridad": "Alta"},
        {"id_pendiente": 2, "concepto": "Cobro de Cliente", "monto": 2700000.00, "estado": "Esperando Acreditación", "destinatario": "Fábrica (Caja Interna)", "prioridad": "Media"},
        {"id_pendiente": 3, "concepto": "Pago Solicitado Mati Medeyro", "monto": 500000.00, "estado": "Pendiente de Ejecución", "destinatario": "Matias Medeyro (Mercado Pago)", "prioridad": "Alta"}
    ])

# =====================================================================
# SIDEBAR - FILTROS Y CONTROLES GLOBALES
# =====================================================================

st.sidebar.image("https://img.icons8.com/clouds/150/000000/accounting.png", width=120)
st.sidebar.title("Navegación de Control")
st.sidebar.info("Utilice las pestañas centrales para interactuar y cargar nuevos datos.")

# Filtro rápido de Proveedores en sidebar
todos_proveedores = ["Todos"] + list(st.session_state.facturas["proveedor"].unique())
prov_filtrado = st.sidebar.selectbox("Filtrar por Proveedor:", todos_proveedores)

# Limpiar todos los datos / Reset
if st.sidebar.button("⚠️ Reiniciar a Datos Históricos"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# =====================================================================
# SECCIÓN PRINCIPAL Y LOGO
# =====================================================================

st.markdown('<div class="main-title">📈 Tablero de Trazabilidad de Caja</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Control Financiero de Cobros, Pagos y Facturas para Fabricación Bekim (Tucumán)</div>', unsafe_allow_html=True)

# Cálculos rápidos para KPIs
total_facturado = st.session_state.facturas["monto_original"].sum()
total_pendiente = st.session_state.facturas["saldo_pendiente"].sum()
total_pagado = total_facturado - total_pendiente
porcentaje_pagado = (total_pagado / total_facturado) * 100 if total_facturado > 0 else 0

# Fila de Indicadores Clave (KPIs)
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total en Obligaciones", f"$ {total_facturado:,.2f}")
col2.metric("Total Pagado/Saldado", f"$ {total_pagado:,.2f}", f"{porcentaje_pagado:.1f}% del total")
col3.metric("Saldo Remanente Deuda", f"$ {total_pendiente:,.2f}", delta="- Disminuyendo", delta_color="inverse")
col4.metric("Tránsitos / Alertas Activas", f"{len(st.session_state.pendientes)} Movimientos")

# =====================================================================
# PESTAÑAS DE TRABAJO (TABS)
# =====================================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Trazabilidad de Caja", 
    "🧾 Facturas y Saldos", 
    "➕ Cargar Transacción / Factura", 
    "⚠️ Alertas y Tránsitos", 
    "📲 Generar WhatsApp"
])

# ---------------------------------------------------------------------
# TAB 1: TRAZABILIDAD DE CAJA (VISTA GENERAL DE TRANSACCIONES)
# ---------------------------------------------------------------------
with tab1:
    st.subheader("🔗 Libro Diario y Trazabilidad de Fondos")
    st.write("Lista completa de todas las transferencias conciliadas de forma cronológica.")
    
    # Aplicar filtros si corresponde
    df_trans_show = st.session_state.transacciones.copy()
    if prov_filtrado != "Todos":
        # Mapeamos qué facturas corresponden al proveedor filtrado
        facturas_prov = st.session_state.facturas[st.session_state.facturas["proveedor"] == prov_filtrado]["id_factura"].tolist()
        df_trans_show = df_trans_show[df_trans_show["factura_afectada"].isin(facturas_prov)]

    # Formatear la tabla para presentación amigable
    df_styled = df_trans_show.copy()
    df_styled["monto"] = df_styled["monto"].apply(lambda x: f"$ {x:,.2f}")
    
    st.dataframe(df_styled, use_container_width=True, hide_index=True)

    # Detalle de cálculo rápido
    st.info("💡 **Trazabilidad cruzada:** El sistema analiza en tiempo real cada peso enviado por los ordenantes originales (Franco Monti, Gerardo Montano, etc.) y computa cómo impacta cada lote en la deuda total con los destinatarios finales.")

# ---------------------------------------------------------------------
# TAB 2: FACTURAS Y SALDOS
# ---------------------------------------------------------------------
with tab2:
    st.subheader("🧾 Control de Facturas (Deuda Corriente)")
    
    df_fact_show = st.session_state.facturas.copy()
    if prov_filtrado != "Todos":
        df_fact_show = df_fact_show[df_fact_show["proveedor"] == prov_filtrado]
        
    # Formateo visual de estados con colores
    def color_estado(val):
        if val == "PAGADA":
            return 'background-color: #D1FAE5; color: #065F46; font-weight: bold;'
        elif val == "PAGO PARCIAL":
            return 'background-color: #FEF3C7; color: #92400E; font-weight: bold;'
        return 'background-color: #FEE2E2; color: #991B1B; font-weight: bold;'

    df_fact_styled = df_fact_show.style.applymap(color_estado, subset=['estado'])
    
    st.write("Estado neto de los compromisos de compra con proveedores:")
    st.dataframe(df_fact_styled, use_container_width=True, hide_index=True)

    # Gráfico simple de progreso del saldo
    st.subheader("📉 Distribución de Deuda Pendiente")
    df_pendientes_chart = st.session_state.facturas[st.session_state.facturas["saldo_pendiente"] > 0]
    if not df_pendientes_chart.empty:
        st.bar_chart(data=df_pendientes_chart, x="id_factura", y="saldo_pendiente", color="#EF4444")
    else:
        st.success("🎉 ¡No hay facturas pendientes de pago en el sistema!")

# ---------------------------------------------------------------------
# TAB 3: CARGAR NUEVA INFORMACIÓN
# ---------------------------------------------------------------------
with tab3:
    col_izq, col_der = st.columns(2)
    
    with col_izq:
        st.subheader("➕ Registrar un Nuevo Pago (Comprobante)")
        with st.form("form_pago", clear_on_submit=True):
            f_fecha = st.date_input("Fecha de Transferencia:", date.today())
            f_hora = st.time_input("Hora de la Operación:", datetime.now().time())
            f_origen = st.text_input("Quién Envía (Ordenante):", placeholder="Ej: Marcelo F. Monti")
            f_banco = st.selectbox("Canal / Banco:", ["Mercado Pago", "BBVA", "Bco. Macro", "Bco. Provincia", "BANCOR", "ICBC", "Otros"])
            f_destino = st.text_input("Destinatario Final:", placeholder="Ej: Daniela Ferron / Mary Sol Parra")
            f_monto = st.number_input("Monto de la Transferencia ($):", min_value=0.0, step=1000.0)
            
            # Elección de factura para imputar
            opciones_facturas = ["N/A"] + list(st.session_state.facturas["id_factura"].unique())
            f_factura = st.selectbox("Imputar / Aplicar a Factura:", opciones_facturas)
            f_lote = st.text_input("Identificador de Lote (Opcional):", placeholder="Ej: Lote Acordes Cta 2")
            
            enviar_pago = st.form_submit_button("💾 Guardar Pago en Sistema")
            
            if enviar_pago:
                if f_monto <= 0 or not f_origen or not f_destino:
                    st.error("Por favor completa los campos obligatorios y un monto válido mayor a $0.")
                else:
                    # Crear nueva fila de transacción
                    nueva_trans = {
                        "fecha": str(f_fecha),
                        "hora": f_hora.strftime("%H:%M"),
                        "origen": f_origen,
                        "banco": f_banco,
                        "destino": f_destino,
                        "monto": f_monto,
                        "factura_afectada": f_factura,
                        "lote": f_lote if f_lote else "Ninguno"
                    }
                    
                    # Añadir a las transacciones
                    st.session_state.transacciones = pd.concat([
                        st.session_state.transacciones, 
                        pd.DataFrame([nueva_trans])
                    ], ignore_index=True)
                    
                    # Actualizar saldo pendiente de la factura si aplica
                    if f_factura != "N/A":
                        idx = st.session_state.facturas[st.session_state.facturas["id_factura"] == f_factura].index
                        if len(idx) > 0:
                            monto_pendiente_actual = st.session_state.facturas.loc[idx[0], "saldo_pendiente"]
                            nuevo_saldo = max(0.0, monto_pendiente_actual - f_monto)
                            st.session_state.facturas.loc[idx[0], "saldo_pendiente"] = nuevo_saldo
                            
                            # Actualizar estado si es necesario
                            if nuevo_saldo == 0:
                                st.session_state.facturas.loc[idx[0], "estado"] = "PAGADA"
                            else:
                                st.session_state.facturas.loc[idx[0], "estado"] = "PAGO PARCIAL"
                                
                    st.success(f"¡Pago de ${f_monto:,.2f} registrado correctamente e imputado a {f_factura}!")
                    st.rerun()

    with col_der:
        st.subheader("➕ Registrar una Nueva Factura de Compra")
        with st.form("form_factura", clear_on_submit=True):
            fact_id = st.text_input("Número / ID de Factura:", placeholder="Ej: SI2606-1145")
            fact_prov = st.text_input("Nombre del Proveedor:", placeholder="Ej: Acordes Aromáticos S.R.L.")
            fact_monto = st.number_input("Monto Total de la Factura ($):", min_value=0.0, step=1000.0)
            fact_fecha = st.date_input("Fecha de Emisión:", date.today())
            fact_detalle = st.text_area("Detalles / Notas Internas:", placeholder="Ej: Referencia MP 3/6...")
            
            enviar_factura = st.form_submit_button("💾 Crear Factura")
            
            if enviar_factura:
                if not fact_id or not fact_prov or fact_monto <= 0:
                    st.error("Por favor, asegúrate de ingresar ID, Proveedor y un Monto de factura mayor a $0.")
                elif fact_id in st.session_state.facturas["id_factura"].values:
                    st.error("Ya existe una factura registrada con ese ID.")
                else:
                    nueva_fact = {
                        "id_factura": fact_id,
                        "proveedor": fact_prov,
                        "monto_original": fact_monto,
                        "saldo_pendiente": fact_monto,
                        "estado": "PENDIENTE",
                        "fecha": str(fact_fecha),
                        "detalle": fact_detalle
                    }
                    
                    st.session_state.facturas = pd.concat([
                        st.session_state.facturas, 
                        pd.DataFrame([nueva_fact])
                    ], ignore_index=True)
                    
                    st.success(f"¡Factura {fact_id} de {fact_prov} por ${fact_monto:,.2f} creada con éxito!")
                    st.rerun()

# ---------------------------------------------------------------------
# TAB 4: ALERTAS Y TRÁNSITOS LOGÍSTICOS
# ---------------------------------------------------------------------
with tab4:
    st.subheader("⚠️ Solicitudes en Espera y Movimientos sin Comprobante")
    st.write("Control de los flujos de dinero que se discutieron en el chat pero que todavía no tienen un comprobante físico para cerrar la conciliación.")
    
    # Mostrar tabla de pendientes interactiva
    df_pendientes = st.session_state.pendientes.copy()
    
    # Formatear el dinero para mostrar
    df_pendientes_display = df_pendientes.copy()
    df_pendientes_display["monto"] = df_pendientes_display["monto"].apply(lambda x: f"$ {x:,.2f}")
    
    st.dataframe(df_pendientes_display, use_container_width=True, hide_index=True)
    
    # Formulario para "Resolver" o dar de baja una alerta
    st.write("---")
    st.subheader("✅ Confirmar y Archivar Alerta (Crear Comprobante)")
    
    col_a, col_b = st.columns(2)
    with col_a:
        alerta_seleccionada = st.selectbox(
            "Seleccionar Alerta a Confirmar:", 
            options=df_pendientes["concepto"].tolist()
        )
    with col_b:
        cuenta_imputacion = st.selectbox(
            "Aplicar el pago de esta Alerta a la Factura:",
            options=["N/A"] + list(st.session_state.facturas["id_factura"].unique())
        )
        
    if st.button("🚀 Confirmar Envío / Recepción de Dinero"):
        # Obtener datos de la alerta seleccionada
        alerta_row = df_pendientes[df_pendientes["concepto"] == alerta_seleccionada].iloc[0]
        
        # Eliminar del listado de alertas pendientes
        st.session_state.pendientes = st.session_state.pendientes[st.session_state.pendientes["concepto"] != alerta_seleccionada]
        
        # Crear transacción correspondiente
        nueva_trans = {
            "fecha": str(date.today()),
            "hora": datetime.now().time().strftime("%H:%M"),
            "origen": "Caja Interna/Cliente" if "Cobro" in alerta_seleccionada else "Administración",
            "banco": "Banco Conciliado",
            "destino": alerta_row["destinatario"],
            "monto": alerta_row["monto"],
            "factura_afectada": cuenta_imputacion,
            "lote": "Resolución Alerta"
        }
        
        st.session_state.transacciones = pd.concat([
            st.session_state.transacciones, 
            pd.DataFrame([nueva_trans])
        ], ignore_index=True)
        
        # Si se imputa a una factura, descontar el dinero
        if cuenta_imputacion != "N/A":
            idx = st.session_state.facturas[st.session_state.facturas["id_factura"] == cuenta_imputacion].index
            if len(idx) > 0:
                saldo_actual = st.session_state.facturas.loc[idx[0], "saldo_pendiente"]
                nuevo_saldo = max(0.0, saldo_actual - alerta_row["monto"])
                st.session_state.facturas.loc[idx[0], "saldo_pendiente"] = nuevo_saldo
                st.session_state.facturas.loc[idx[0], "estado"] = "PAGADA" if nuevo_saldo == 0 else "PAGO PARCIAL"
                
        st.success(f"La alerta '{alerta_seleccionada}' ha sido conciliada y convertida en transacción histórica.")
        st.rerun()

# ---------------------------------------------------------------------
# TAB 5: GENERADOR AUTOMÁTICO DE WHATSAPP
# ---------------------------------------------------------------------
with tab5:
    st.subheader("📲 Generar Resumen para compartir por WhatsApp")
    st.write("Este texto se calcula en tiempo real basándose en los datos cargados actualmente en el sistema. Copialo y pegalo en el grupo de trabajo.")
    
    # Obtener dinámicamente datos para el mensaje
    facturas_saldadas = st.session_state.facturas[st.session_state.facturas["saldo_pendiente"] == 0]
    facturas_pendientes = st.session_state.facturas[st.session_state.facturas["saldo_pendiente"] > 0]
    
    alertas_activas = st.session_state.pendientes
    
    # Construir el cuerpo del mensaje de texto adaptado
    texto_whatsapp = f"""📊 *RESUMEN DE PAGOS Y CONCILIACIÓN* 📊
*(Actualizado al {datetime.now().strftime("%d/%m/%Y")} - {datetime.now().strftime("%H:%M")} hs)*

✅ *FACTURAS SALDADAS (En $0)*"""
    
    if not facturas_saldadas.empty:
        for idx, r in facturas_saldadas.iterrows():
            texto_whatsapp += f"\n• *{r['id_factura']} ({r['proveedor']}):* CANCELADA ({r['detalle']})"
    else:
        texto_whatsapp += "\n• No hay facturas saldadas en este periodo."
        
    texto_whatsapp += "\n\n---"
    texto_whatsapp += "\n\n📉 *FACTURAS EN PROCESO DE PAGO*"
    
    for idx, r in facturas_pendientes.iterrows():
        total_pago = r['monto_original'] - r['saldo_pendiente']
        texto_whatsapp += f"\n• *{r['id_factura']} ({r['proveedor']} - Total $ {r['monto_original']:,.2f})*"
        texto_whatsapp += f"\n  - *Total Pagado hasta hoy:* -$ {total_pago:,.2f}"
        texto_whatsapp += f"\n  - 🔥 *SALDO ACTUAL POR PAGAR:* *$ {r['saldo_pendiente']:,.2f}*"
        texto_whatsapp += "\n"

    texto_whatsapp += "\n---"
    texto_whatsapp += "\n\n⚠️ *PENDIENTES DE COMPROBANTE / TRÁMITE DE CAJA:*"
    
    if not alertas_activas.empty:
        for idx, r in alertas_activas.iterrows():
            texto_whatsapp += f"\n• *{r['concepto']}:* $ {r['monto']:,.2f} ({r['estado']} - Destino: {r['destinatario']})"
    else:
        texto_whatsapp += "\n• ¡Sin alertas activas ni pagos pendientes!"
        
    texto_whatsapp += "\n\n_Generado automáticamente desde el Panel de Control de Caja Bekim_"
    
    # Mostrar el texto formateado
    st.markdown('<div class="whatsapp-box">', unsafe_allow_html=True)
    st.code(texto_whatsapp, language="text")
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.caption("Tip: Hacé click en el botón de copiar que aparece arriba a la derecha de la caja gris de código para guardarlo en tu portapapeles.")