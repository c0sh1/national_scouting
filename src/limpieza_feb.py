
from pathlib import Path

import pandas as pd

CARPETA_RAW = Path("data/raw")
CARPETA_PROCESSED = Path("data/processed")
CLAVE = ["id_feb", "competicion", "temporada"]

ESTADISTICAS_CONTEO = {
    "Puntos": "puntos",
    "Rebotes Ofensivos": "reb_of",
    "Rebotes Defensivos": "reb_def",
    "Asistencias": "asistencias",
    "Balones recuperados": "recuperaciones",
    "Balones perdidos": "perdidas",
    "Tapones a favor": "tapones_favor",
    "Valoración": "valoracion",
    "Minutos jugados": "minutos",
}
ESTADISTICAS_TIRO = {
    "% Tiros de 2": "t2",
    "% Tiros de 3": "t3",
    "% Tiros Libres": "tl",
}
POR_40_MINUTOS = [
    "puntos", "rebotes", "reb_of", "reb_def", "asistencias",
    "recuperaciones", "perdidas", "tapones_favor", "valoracion",
]


def construir_temporadas(rankings):
    """Pasa los rankings en formato largo a una fila por jugador y temporada."""
    df = rankings.copy()
    df["id_feb"] = df["id_feb"].astype(str)
    nacionales = df[df["solo_nacionales"].astype(bool)]
    df = df[~df["solo_nacionales"].astype(bool)]

    conteo = df[df["estadistica"].isin(ESTADISTICAS_CONTEO)]
    totales = (
        conteo.assign(columna=conteo["estadistica"].map(ESTADISTICAS_CONTEO))
        .pivot_table(index=CLAVE, columns="columna", values="total", aggfunc="sum")
        # Todas las columnas existen aunque no se haya descargado alguna estadística.
        .reindex(columns=list(ESTADISTICAS_CONTEO.values()))
    )

    tiro = df[df["estadistica"].isin(ESTADISTICAS_TIRO)]
    tiros = (
        tiro.assign(tipo=tiro["estadistica"].map(ESTADISTICAS_TIRO))
        .pivot_table(index=CLAVE, columns="tipo", values=["anotados", "intentados"], aggfunc="sum")
    )
    tiros.columns = [f"{tipo}_{medida}" for medida, tipo in tiros.columns]

    # Partidos: del ranking de minutos y, si falta, el máximo de los demás.
    partidos_minutos = (
        df[df["estadistica"] == "Minutos jugados"].groupby(CLAVE)["partidos"].sum()
    )
    partidos_otros = (
        df[df["estadistica"] != "Minutos jugados"]
        .groupby(CLAVE + ["estadistica"])["partidos"].sum()
        .groupby(level=CLAVE).max()
    )
    partidos = partidos_minutos.combine_first(partidos_otros).rename("partidos")

    descriptivos = df.groupby(CLAVE).agg(
        jugador=("jugador", "last"),
        equipo=("equipo", lambda e: " / ".join(sorted(e.dropna().unique()))),
    )

    tabla = descriptivos.join(partidos).join(totales).join(tiros).reset_index()
    columnas_conteo = [c for c in ESTADISTICAS_CONTEO.values() if c != "minutos"]
    con_minutos = tabla["minutos"].notna()
    tabla.attrs["ceros_rellenados"] = tabla.loc[con_minutos, columnas_conteo].isna().sum()
    tabla.loc[con_minutos, columnas_conteo] = tabla.loc[con_minutos, columnas_conteo].fillna(0)

    ids_nacionales = set(map(tuple, nacionales[CLAVE].astype({"id_feb": str}).values))
    tabla["es_nacional_feb"] = [tuple(fila) in ids_nacionales for fila in tabla[CLAVE].values]
    return calcular_derivadas(tabla)


def calcular_derivadas(tabla):
    tabla = tabla.copy()
    if {"reb_of", "reb_def"} <= set(tabla.columns):
        tabla["rebotes"] = tabla["reb_of"] + tabla["reb_def"]
    partidos = tabla["partidos"].where(tabla["partidos"] > 0)
    tabla["minutos_partido"] = tabla["minutos"] / partidos

    minutos = tabla["minutos"].where(tabla["minutos"] > 0)
    for columna in POR_40_MINUTOS:
        if columna in tabla:
            tabla[f"{columna}_40"] = 40 * tabla[columna] / minutos

    for tipo in ESTADISTICAS_TIRO.values():
        anotados, intentados = f"{tipo}_anotados", f"{tipo}_intentados"
        if intentados not in tabla:
            tabla[anotados] = pd.NA
            tabla[intentados] = pd.NA
        tabla[f"{tipo}_pct"] = 100 * tabla[anotados] / tabla[intentados].where(tabla[intentados] > 0)
        tabla[f"{tipo}_falta"] = tabla[intentados].isna()
    return tabla


def validar(tabla):
    problemas = []
    excesivos = (tabla["minutos_partido"] > 45).sum()
    if excesivos:
        problemas.append(f"{excesivos} filas con más de 45 minutos por partido")
    for tipo in ESTADISTICAS_TIRO.values():
        imposibles = (tabla[f"{tipo}_anotados"] > tabla[f"{tipo}_intentados"]).sum()
        if imposibles:
            problemas.append(f"{tipo}: {imposibles} filas con más anotados que intentados")
    sin_minutos = tabla["minutos"].isna().sum()
    if sin_minutos:
        problemas.append(f"{sin_minutos} filas sin minutos (no aparecen en el ranking de minutos)")
    return problemas


def main():
    rankings = pd.read_csv(CARPETA_RAW / "feb_rankings.csv", dtype={"id_feb": str})
    tabla = construir_temporadas(rankings)
    CARPETA_PROCESSED.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(CARPETA_PROCESSED / "feb_temporadas.csv", index=False)

    ceros = tabla.attrs.get("ceros_rellenados", pd.Series(dtype=int))
    por_competicion = tabla.groupby("competicion").agg(
        filas=("id_feb", "size"), jugadores=("id_feb", "nunique"),
        nacionales=("es_nacional_feb", "mean"),
    )
    problemas = validar(tabla)
    lineas = [
        f"Filas jugador-temporada: {len(tabla)}",
        f"Jugadores distintos: {tabla['id_feb'].nunique()}",
        "",
        "Por competición (nacionales = proporción de filas):",
        por_competicion.round(3).to_string(),
        "",
        "Ceros rellenados por estadística (jugador con minutos que no sale en el ranking):",
        ceros.to_string(),
        "",
        "Porcentaje de filas sin datos de tiro (pocos intentos):",
        *[f"  {t}: {tabla[f'{t}_falta'].mean():.1%}" for t in ESTADISTICAS_TIRO.values()],
        "",
        "Problemas de calidad:" if problemas else "Sin problemas de calidad detectados.",
        *[f"- {p}" for p in problemas],
    ]
    informe = "\n".join(lineas)
    (CARPETA_PROCESSED / "informe_calidad_feb.txt").write_text(informe, encoding="utf-8")
    print(informe)


if __name__ == "__main__":
    main()