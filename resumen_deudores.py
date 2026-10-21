import streamlit as st
from gestion_cobranza import get_estado_revendedores

def mostrar_resumen_deudores():
    st.subheader("📌 Vista General de Deudores")
    st.markdown("Aquí se listan todos los revendedores con saldo pendiente.")

    df_estado = get_estado_revendedores()

    if df_estado.empty:
        st.success("✅ No hay revendedores registrados.")
        return

    deudores = df_estado[df_estado["saldo_pendiente"] > 0].copy()

    if deudores.empty:
        st.success("✅ Actualmente no hay deudores.")
        return

    deudores = deudores.sort_values(by="saldo_pendiente", ascending=False)

    deudores.rename(columns={
        "nombre": "Revendedor",
        "total_ventas": "Total Ventas",
        "total_pagos": "Total Pagado",
        "saldo_pendiente": "Saldo Pendiente"
    }, inplace=True)

    st.dataframe(
        deudores[["Revendedor", "Total Ventas", "Total Pagado", "Saldo Pendiente"]]
        .style.format({
            "Total Ventas": "AR$ {:,.2f}",
            "Total Pagado": "AR$ {:,.2f}",
            "Saldo Pendiente": "AR$ {:,.2f}"
        }),
        use_container_width=True
    )
