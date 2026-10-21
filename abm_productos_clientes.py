import streamlit as st
import sqlite3

def abm_productos_clientes():
    st.header("ABM Productos Clientes")
    conn = sqlite3.connect("minerva.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id, nombre FROM clientes")
    clientes = cursor.fetchall()
    cliente_dict = {nombre: id for id, nombre in clientes}

    cursor.execute("SELECT id, nombre FROM productos")
    productos = cursor.fetchall()
    producto_dict = {nombre: id for id, nombre in productos}

    st.subheader("Agregar Producto Cliente")
    cliente_nombre = st.selectbox("Cliente", list(cliente_dict.keys()))
    producto_nombre = st.selectbox("Producto", list(producto_dict.keys()))
    uso = st.text_input("Uso")
    linea = st.text_input("Línea")
    if st.button("Agregar Producto Cliente"):
        if uso and linea:
            cursor.execute("""
                INSERT INTO productos_clientes (cliente_id, producto_id, uso, linea)
                VALUES (?, ?, ?, ?)""", (cliente_dict[cliente_nombre], producto_dict[producto_nombre], uso, linea))
            conn.commit()
            st.success("Producto Cliente agregado.")
            st.experimental_rerun()
        else:
            st.warning("Uso y línea son obligatorios.")

    st.subheader("Productos Clientes existentes")
    cursor.execute("""
        SELECT pc.id, c.nombre, p.nombre, pc.uso, pc.linea
        FROM productos_clientes pc
        JOIN clientes c ON pc.cliente_id = c.id
        JOIN productos p ON pc.producto_id = p.id
        ORDER BY c.nombre, p.nombre
    """)
    for id, cliente, producto, uso, linea in cursor.fetchall():
        st.write(f"Cliente: {cliente} | Producto: {producto} | Uso: {uso} | Línea: {linea}")
        if st.button("Eliminar", key=f"del_prodcli_{id}"):
            cursor.execute("DELETE FROM productos_clientes WHERE id=?", (id,))
            conn.commit()
            st.warning("Producto Cliente eliminado.")
            st.experimental_rerun()
    conn.close()
