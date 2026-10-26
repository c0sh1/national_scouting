"""Construye la tabla del modelo y la variable objetivo (se_asienta)."""

from pathlib import Path

import pandas as pd

CARPETA_RAW = Path("data/raw")
CARPETA_PROCESSED = Path("data/processed")

# Asentarse = 15 partidos con 15 minutos por partido en alguna de las 3 temporadas siguientes.
HORIZONTE = 3
MIN_PARTIDOS = 15
MIN_MINUTOS = 15
MIN_MINUTOS_FEB = 100
COMPETICIONES_ENTRENAMIENTO = ["primera_feb", "segunda_feb"]
# Una edad menor es un error de la ficha.
EDAD_MINIMA = 14

VARIABLES_EVOLUCION = ["minutos_partido", "puntos_40", "rebotes_40", "asistencias_40", "valoracion_40"]


def temporadas_asentado(temporadas_acb, min_partidos=MIN_PARTIDOS, min_minutos=MIN_MINUTOS):
    """Temporadas ACB en las que el jugador estuvo asentado (15 partidos y 15 minutos por partido o más)."""
    asentado = (temporadas_acb["partidos"] >= min_partidos) & (temporadas_acb["minutos"] >= min_minutos)
    return temporadas_acb.loc[asentado, ["id_acb", "anio"]]


def definir_objetivo(filas, temporadas_acb, ultima_temporada_acb, horizonte=HORIZONTE,
                     min_partidos=MIN_PARTIDOS, min_minutos=MIN_MINUTOS):
    """Añade la columna se_asienta (1/0). Queda vacía si aún no han pasado las 3 temporadas."""
    asentadas = temporadas_asentado(temporadas_acb, min_partidos, min_minutos)
    por_jugador = asentadas.groupby("id_acb")["anio"].apply(list).to_dict()

    def desenlace(fila):
        """Si ya estaba asentado antes y si se asienta en las 3 temporadas siguientes."""
        anios = por_jugador.get(fila["id_acb"], []) if pd.notna(fila["id_acb"]) else []
        antes = any(a < fila["temporada"] for a in anios)
        despues = any(fila["temporada"] < a <= fila["temporada"] + horizonte for a in anios)
        completo = fila["temporada"] + horizonte <= ultima_temporada_acb
        return pd.Series({
            "ya_asentado_antes": antes,
            "se_asienta": int(despues) if completo else pd.NA,
        })

    return filas.join(filas.apply(desenlace, axis=1))


def anadir_evolucion(tabla):
    """Añade el cambio respecto a la temporada anterior y cuántas temporadas lleva en la FEB."""
    principal = (tabla.sort_values("minutos", ascending=False)
                 .drop_duplicates(["id_feb", "temporada"])
                 .sort_values(["id_feb", "temporada"]))
    anterior = principal.groupby("id_feb")[["temporada"] + VARIABLES_EVOLUCION].shift(1)
    # Solo se compara con la temporada justo anterior.
    consecutiva = principal["temporada"] - anterior["temporada"] == 1
    evolucion = principal[["id_feb", "temporada"]].copy()
    for columna in VARIABLES_EVOLUCION:
        evolucion[f"{columna}_cambio"] = (principal[columna] - anterior[columna]).where(consecutiva)
    evolucion["temporadas_previas_feb"] = principal.groupby("id_feb").cumcount()
    return tabla.merge(evolucion, on=["id_feb", "temporada"], how="left")


def construir(feb_temporadas, fichas, temporadas_acb, emparejamiento, ultima_temporada_acb,
              horizonte=HORIZONTE, min_partidos=MIN_PARTIDOS, min_minutos=MIN_MINUTOS,
              min_minutos_feb=MIN_MINUTOS_FEB):
    """Tabla del modelo: una fila por jugador y temporada FEB, variable + objetivo."""
    tabla = anadir_evolucion(feb_temporadas)
    tabla = tabla[tabla["competicion"].isin(COMPETICIONES_ENTRENAMIENTO)]
    tabla = tabla[tabla["minutos"] >= min_minutos_feb]
    tabla = tabla.merge(fichas, on="id_feb", how="left")
    tabla["edad"] = tabla["temporada"] - tabla["anio_nacimiento"]
    tabla.loc[tabla["edad"] < EDAD_MINIMA, ["anio_nacimiento", "edad"]] = float("nan")
    tabla = tabla.merge(emparejamiento[["id_feb", "id_acb"]], on="id_feb", how="left")
    tabla = definir_objetivo(tabla.reset_index(drop=True), temporadas_acb, ultima_temporada_acb,
                             horizonte, min_partidos, min_minutos)
    # Fuera los que ya estaban asentados en la ACB.
    tabla = tabla[~tabla["ya_asentado_antes"]].drop(columns="ya_asentado_antes")
    return tabla.drop(columns="id_acb").reset_index(drop=True)


def main():
    """Crea data/processed/dataset_modelo.csv y muestra un resumen."""
    feb_temporadas = pd.read_csv(CARPETA_PROCESSED / "feb_temporadas.csv", dtype={"id_feb": str})
    fichas = pd.read_csv(CARPETA_RAW / "feb_jugadores.csv", dtype={"id_feb": str})
    temporadas_acb = pd.read_csv(CARPETA_PROCESSED / "temporadas.csv", dtype={"id_acb": str})
    emparejamiento = pd.read_csv(CARPETA_PROCESSED / "emparejamiento.csv", dtype={"id_acb": str, "id_feb": str})

    """La temporada en curso no ha terminado: no cuenta para el objetivo."""
    ultima_completa = int(temporadas_acb["anio"].max()) - 1
    temporadas_acb = temporadas_acb[temporadas_acb["anio"] <= ultima_completa]

    tabla = construir(feb_temporadas, fichas, temporadas_acb, emparejamiento, ultima_completa)
    tabla.to_csv(CARPETA_PROCESSED / "dataset_modelo.csv", index=False)

    etiquetadas = tabla.dropna(subset=["se_asienta"])
    print(f"Última temporada ACB completa: {ultima_completa}/{ultima_completa + 1}")
    print(f"Filas: {len(tabla)} · con objetivo: {len(etiquetadas)} · "
          f"sin objetivo (solo para aplicar): {len(tabla) - len(etiquetadas)}")
    print(f"Positivos: {int(etiquetadas['se_asienta'].sum())} "
          f"({etiquetadas['se_asienta'].astype(float).mean():.1%})")
    print("\nPositivos por competición y nacionalidad FEB:")
    print(etiquetadas.groupby(["competicion", "es_nacional_feb"])["se_asienta"]
          .agg(["size", "sum"]).to_string())
    print(f"\nFilas sin edad (año de nacimiento imposible o ausente): {tabla['edad'].isna().sum()}")


if __name__ == "__main__":
    main()