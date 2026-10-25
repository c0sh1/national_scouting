
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
RUTA_DB = RAIZ / "data" / "scouting.db"


def _conectar(ruta=None):
    ruta = Path(ruta or RUTA_DB)
    if not ruta.exists():
        raise FileNotFoundError(
            f"No existe la base de datos {ruta}. Genérala con: python -m src.base_datos")
    return sqlite3.connect(f"{ruta.resolve().as_uri()}?mode=ro", uri=True)


def cargar_datos(tabla, ruta=None):
    """Una tabla o vista completa como DataFrame."""
    with closing(_conectar(ruta)) as conexion:
        nombres = {fila[0] for fila in conexion.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
        if tabla not in nombres:
            raise ValueError(f"La tabla '{tabla}' no existe. Disponibles: {sorted(nombres)}")
        return pd.read_sql_query(f"SELECT * FROM {tabla}", conexion)


def consultar(sql, parametros=(), ruta=None):
    """Resultado de una consulta SQL como DataFrame."""
    with closing(_conectar(ruta)) as conexion:
        return pd.read_sql_query(sql, conexion, params=parametros)


def cargar_csv(nombre, carpeta="raw"):
    """Un CSV de data/raw o data/processed, para revisar datos que no están en la
    base (por ejemplo, los rankings de la FEB en bruto durante el preproceso)."""
    ruta = RAIZ / "data" / carpeta / nombre
    if not ruta.exists():
        raise FileNotFoundError(f"No existe {ruta}")
    return pd.read_csv(ruta, dtype={"id_acb": str, "id_feb": str, "i": str})