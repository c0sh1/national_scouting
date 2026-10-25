
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

CARPETA_RAW = Path("data/raw")
CARPETA_PROCESSED = Path("data/processed")
RUTA_DB = Path("data/scouting.db")

ESQUEMA = """
CREATE TABLE jugadores_acb (
    id_acb          TEXT PRIMARY KEY,
    slug            TEXT NOT NULL,
    posicion        TEXT,
    altura_cm       REAL,
    anio_nacimiento INTEGER,
    nacionalidad    TEXT,
    licencia        TEXT,
    es_espanol      INTEGER,
    es_jfl          INTEGER
);

CREATE TABLE jugadores_feb (
    id_feb          TEXT PRIMARY KEY,
    nombre          TEXT,
    anio_nacimiento INTEGER,
    altura_cm       REAL,
    puesto          TEXT,
    nacionalidad    TEXT
);

CREATE TABLE emparejamiento (
    id_acb TEXT NOT NULL UNIQUE REFERENCES jugadores_acb (id_acb),
    id_feb TEXT NOT NULL UNIQUE REFERENCES jugadores_feb (id_feb),
    metodo TEXT NOT NULL
);

CREATE TABLE trayectorias_feb (
    id_feb    TEXT NOT NULL REFERENCES jugadores_feb (id_feb),
    anio      INTEGER NOT NULL,
    nivel     TEXT NOT NULL,
    categoria TEXT NOT NULL,
    club      TEXT
);
"""

TABLAS_ANCHAS = {
    "temporadas_acb": ("temporadas.csv", ["id_acb", "anio"]),
    "temporadas_acb_club": ("temporadas_por_club.csv", ["id_acb", "temporada", "club"]),
    "temporadas_feb": ("feb_temporadas.csv", ["id_feb", "competicion", "temporada"]),
    "dataset_modelo": ("dataset_modelo.csv", ["id_feb", "competicion", "temporada"]),
}

VISTAS = """
CREATE VIEW v_debut_acb AS
SELECT j.id_acb, j.licencia, j.es_jfl, MIN(t.anio) AS debut
FROM jugadores_acb j
JOIN temporadas_acb t ON t.id_acb = j.id_acb
GROUP BY j.id_acb;

CREATE VIEW v_cobertura_feb AS
SELECT d.id_acb, d.licencia, d.debut,
       e.id_feb IS NOT NULL AS tiene_pareja_feb
FROM v_debut_acb d
LEFT JOIN emparejamiento e ON e.id_acb = d.id_acb;
"""

COLUMNAS_JUGADORES_ACB = ["id_acb", "slug", "posicion", "altura_cm", "anio_nacimiento",
                          "nacionalidad", "licencia", "es_espanol", "es_jfl"]


def leer_csv(ruta, **kwargs):
    return pd.read_csv(ruta, dtype={"id_acb": str, "id_feb": str}, **kwargs)


def preparar_tablas():
    """Lee los CSV y los deja con las columnas de cada tabla."""
    temporadas_feb = leer_csv(CARPETA_PROCESSED / "feb_temporadas.csv")
    nombres = temporadas_feb.sort_values("temporada").groupby("id_feb")["jugador"].last()

    jugadores_feb = leer_csv(CARPETA_RAW / "feb_jugadores.csv")
    jugadores_feb["nombre"] = jugadores_feb["id_feb"].map(nombres)

    return {
        "jugadores_acb": leer_csv(CARPETA_PROCESSED / "jugadores.csv")[COLUMNAS_JUGADORES_ACB],
        "jugadores_feb": jugadores_feb[["id_feb", "nombre", "anio_nacimiento", "altura_cm",
                                        "puesto", "nacionalidad"]],
        "emparejamiento": leer_csv(CARPETA_PROCESSED / "emparejamiento.csv"),
        "trayectorias_feb": leer_csv(CARPETA_PROCESSED / "feb_trayectorias.csv")[
            ["id_feb", "anio", "nivel", "categoria", "club"]],
    }


def comprobar(conexion):
    """Comprobaciones de integridad que SQLite no hace por sí solo al cargar."""
    consultas = {
        "emparejamientos con id_acb inexistente":
            "SELECT COUNT(*) FROM emparejamiento WHERE id_acb NOT IN (SELECT id_acb FROM jugadores_acb)",
        "emparejamientos con id_feb inexistente":
            "SELECT COUNT(*) FROM emparejamiento WHERE id_feb NOT IN (SELECT id_feb FROM jugadores_feb)",
        "temporadas ACB sin jugador":
            "SELECT COUNT(*) FROM temporadas_acb WHERE id_acb NOT IN (SELECT id_acb FROM jugadores_acb)",
        "temporadas FEB sin ficha":
            "SELECT COUNT(*) FROM temporadas_feb WHERE id_feb NOT IN (SELECT id_feb FROM jugadores_feb)",
    }
    return {nombre: conexion.execute(sql).fetchone()[0] for nombre, sql in consultas.items()}


def construir(ruta=RUTA_DB, tablas=None, anchas=None):
    """Crea la base desde cero. tablas y anchas permiten pasar datos en las pruebas."""
    tablas = tablas if tablas is not None else preparar_tablas()
    if anchas is None:
        anchas = {nombre: leer_csv(CARPETA_PROCESSED / archivo)
                  for nombre, (archivo, _) in TABLAS_ANCHAS.items()}

    ruta = Path(ruta)
    ruta.unlink(missing_ok=True)

    with closing(sqlite3.connect(ruta)) as conexion:
        conexion.executescript(ESQUEMA)
        for nombre, datos in tablas.items():
            datos.to_sql(nombre, conexion, if_exists="append", index=False)
        for nombre, datos in anchas.items():
            datos.to_sql(nombre, conexion, index=False)
            clave = ", ".join(TABLAS_ANCHAS[nombre][1])
            conexion.execute(f"CREATE UNIQUE INDEX ix_{nombre} ON {nombre} ({clave})")
        conexion.executescript(VISTAS)
        conexion.commit()
        return comprobar(conexion)


def main():
    problemas = construir()
    with closing(sqlite3.connect(RUTA_DB)) as conexion:
        for (tabla,) in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY type, name"):
            filas = conexion.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
            print(f"{tabla:20s} {filas:>7d} filas")
    print(f"\nBase de datos: {RUTA_DB} ({RUTA_DB.stat().st_size / 1e6:.1f} MB)")
    for nombre, cantidad in problemas.items():
        print(f"{'OK  ' if cantidad == 0 else 'AVISO'} {nombre}: {cantidad}")


if __name__ == "__main__":
    main()