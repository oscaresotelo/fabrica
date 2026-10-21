
CREATE TABLE IF NOT EXISTS receta_procedimiento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receta_id INTEGER,
    orden INTEGER, -- Para saber si es el paso 1, 2, 3...
    instruccion TEXT, -- Ejemplo: "Cargar agua en reactor a 65-70°C"
    control_esperado TEXT, -- Ejemplo: "Rango: 65°C - 70°C"
    FOREIGN KEY (receta_id) REFERENCES recetas (id)
);


CREATE TABLE IF NOT EXISTS receta_control_calidad (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receta_id INTEGER,
    parametro TEXT, -- Ejemplo: "pH Final", "Aspecto", "Viscosidad"
    valor_referencia TEXT, -- Ejemplo: "4.00 - 5.5", "Crema homogénea"
    FOREIGN KEY (receta_id) REFERENCES recetas (id)
);