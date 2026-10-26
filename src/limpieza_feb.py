"""Limpieza de la FEB: una fila por jugador y temporada, y trayectorias por categoría."""

from pathlib import Path

import pandas as pd

CARPETA_RAW = Path("data/raw")
CARPETA_PROCESSED = Path("data/processed")
# Una fila por jugador, competición y temporada.
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

# La FEB al cambiar de nombres de sus ligas durante años, las unificamos.
CATEGORIAS = {
    "LEB": "primera_feb", "LEB ORO": "primera_feb", "ORO": "primera_feb", "PRIMERA FEB": "primera_feb",
    "LEB 2": "segunda_feb", "LEB PLATA": "segunda_feb", "PLATA": "segunda_feb", "SEGUNDA FEB": "segunda_feb",
    "BRONCE": "leb_bronce",
    "EBA": "tercera_feb", "LIGA EBA": "tercera_feb", "TERCERA FEB": "tercera_feb",
    "1ª División M.": "primera_division",
    "LIGA U": "liga_u",
}

POR_40_MINUTOS = [
    "puntos", "rebotes", "reb_of", "reb_def", "asistencias",
    "recuperaciones", "perdidas", "tapones_favor", "valoracion",
    "tapones_contra", "faltas_cometidas", "faltas_recibidas",
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
        .reindex(columns=list(ESTADISTICAS_CONTEO.values()))
    )

    tiro = df[df["estadistica"].isin(ESTADISTICAS_TIRO)]
    tiros = (
        tiro.assign(tipo=tiro["estadistica"].map(ESTADISTICAS_TIRO))
        .pivot_table(index=CLAVE, columns="tipo", values=["anotados", "intentados"], aggfunc="sum")
    )
    tiros.columns = [f"{tipo}_{medida}" for medida, tipo in tiros.columns]

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
    # El ranking no lista los ceros: si jugó minutos y no aparece, esa estadística = 0.
    tabla.loc[con_minutos, columnas_conteo] = tabla.loc[con_minutos, columnas_conteo].fillna(0)

    ids_nacionales = set(map(tuple, nacionales[CLAVE].astype({"id_feb": str}).values))
    tabla["es_nacional_feb"] = [tuple(fila) in ids_nacionales for fila in tabla[CLAVE].values]
    return calcular_derivadas(tabla)


COLUMNAS_SOLO_FICHA = ["tc_anotados", "tc_intentados", "tapones_contra", "mates",
                       "faltas_cometidas", "faltas_recibidas"]
# Diferencia máxima de 2 % entre ficha y ranking para dar los datos de la ficha por buenos.
TOLERANCIA = 0.02  


def candidatos_ficha(totales):
    """Sumas por jugador y temporada para cada fase y para todas juntas."""
    validos = totales[totales["fase"].notna()
                      & (totales["temporada_pagina"] == totales["temporada"])]
    numericas = [c for c in validos.columns
                 if c not in CLAVE + ["i", "fase", "temporada_pagina"]]
    por_fase = validos.groupby(CLAVE + ["fase"])[numericas].sum(min_count=1).reset_index()
    todas = validos.groupby(CLAVE)[numericas].sum(min_count=1).reset_index().assign(fase="todas")
    candidatos = pd.concat([por_fase, todas], ignore_index=True)
    # Se prefiere la liga regular (LR). La suma de todas las fases, en último lugar.
    candidatos["prioridad"] = candidatos["fase"].map({"LR": 0, "todas": 2}).fillna(1)
    return candidatos


def integrar_totales(tabla, totales):
    """Completa la tabla de los rankings con los totales de las fichas. Devuelve la tabla y un resumen de la comprobación ficha-ranking."""
    totales = totales.copy()
    totales["id_feb"] = totales["id_feb"].astype(str)
    candidatos = candidatos_ficha(totales)

    referencia = tabla[CLAVE + ["minutos", "puntos"]]
    cruce = candidatos.merge(referencia, on=CLAVE, suffixes=("_ficha", ""))
    coincide = pd.Series(True, index=cruce.index)
    for columna in ["minutos", "puntos"]:
        base = cruce[columna].where(cruce[columna] > 0)
        diferencia = (cruce[f"{columna}_ficha"] - cruce[columna]).abs() / base
        coincide &= diferencia.fillna(0) <= TOLERANCIA
    elegidos = (cruce[coincide].sort_values(["prioridad", "minutos_ficha"], ascending=[True, False])
                .drop_duplicates(CLAVE))
    columnas_ficha = [c for c in candidatos.columns if c not in CLAVE + ["fase", "prioridad"]]
    elegidos = elegidos[CLAVE + ["fase"]].merge(candidatos, on=CLAVE + ["fase"])
    elegidos = elegidos.rename(columns={c: f"{c}_ficha" for c in columnas_ficha + ["fase"]})

    unida = tabla.merge(elegidos.drop(columns="prioridad"), on=CLAVE, how="left")
    usar = unida["fase_ficha"].notna()
    for tipo in ["t2", "t3", "tl"]:
        for medida in ["anotados", "intentados"]:
            columna = f"{tipo}_{medida}"
            unida.loc[usar, columna] = unida.loc[usar, f"{columna}_ficha"]
    for columna in COLUMNAS_SOLO_FICHA:
        unida[columna] = unida[f"{columna}_ficha"].where(usar)

    con_ficha = tabla.set_index(CLAVE).index.isin(candidatos.set_index(CLAVE).index)
    resumen = {
        "filas": len(unida),
        "con_ficha": int(con_ficha.sum()),
        "usadas": int(usar.sum()),
        "descartadas_por_no_coincidir": int(con_ficha.sum() - usar.sum()),
        "fase_elegida": unida["fase_ficha"].value_counts().to_dict(),
    }
    unida = unida.drop(columns=[c for c in unida.columns if c.endswith("_ficha")])
    return calcular_derivadas(unida), resumen


def calcular_derivadas(tabla):
    """Añade rebotes, minutos por partido, estadísticas por 40 minutos y % de tiro."""
    tabla = tabla.copy()
    if {"reb_of", "reb_def"} <= set(tabla.columns):
        tabla["rebotes"] = tabla["reb_of"] + tabla["reb_def"]
    partidos = tabla["partidos"].where(tabla["partidos"] > 0)
    tabla["minutos_partido"] = tabla["minutos"] / partidos

    minutos = tabla["minutos"].where(tabla["minutos"] > 0)
    for columna in POR_40_MINUTOS:
        if columna in tabla:
            tabla[f"{columna}_40"] = 40 * tabla[columna] / minutos

    tipos = list(ESTADISTICAS_TIRO.values()) + (["tc"] if "tc_intentados" in tabla else [])
    for tipo in tipos:
        anotados, intentados = f"{tipo}_anotados", f"{tipo}_intentados"
        if intentados not in tabla:
            tabla[anotados] = pd.NA
            tabla[intentados] = pd.NA
        tabla[f"{tipo}_pct"] = 100 * tabla[anotados] / tabla[intentados].where(tabla[intentados] > 0)
        tabla[f"{tipo}_falta"] = tabla[intentados].isna()
    return tabla


def validar(tabla):
    """Lista de problemas de calidad: minutos imposibles, más anotados que intentados..."""
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


def anio_temporada(texto):
    """'09/10' -> 2009 · '97/98' -> 1997. SIempre el año de inicio de la temporada."""
    yy = int(texto[:2])
    return 1900 + yy if yy >= 50 else 2000 + yy


def limpiar_trayectorias(trayectorias):
    """Unifica los nombres de categoría y quita las que no son de la pirámide masculina. Devuelve la tabla limpia y las filas excluidas."""
    tabla = trayectorias.copy()
    tabla["id_feb"] = tabla["id_feb"].astype(str)
    tabla["anio"] = tabla["temporada"].map(anio_temporada)
    tabla["nivel"] = tabla["categoria"].map(CATEGORIAS)
    excluidas = tabla[tabla["nivel"].isna()]
    tabla = tabla.dropna(subset=["nivel"]).drop_duplicates(["id_feb", "anio", "nivel", "club"])
    return tabla.reset_index(drop=True), excluidas


def main():
    """Crea feb_temporadas.csv, feb_trayectorias.csv y el informe de calidad de la FEB."""
    rankings = pd.read_csv(CARPETA_RAW / "feb_rankings.csv", dtype={"id_feb": str})
    tabla = construir_temporadas(rankings)
    ceros = tabla.attrs.get("ceros_rellenados", pd.Series(dtype=int))
    resumen_fichas = None
    if (CARPETA_RAW / "feb_totales.csv").exists():
        totales = pd.read_csv(CARPETA_RAW / "feb_totales.csv", dtype={"id_feb": str, "i": str})
        tabla, resumen_fichas = integrar_totales(tabla, totales)
    CARPETA_PROCESSED.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(CARPETA_PROCESSED / "feb_temporadas.csv", index=False)
    trayectorias, excluidas = limpiar_trayectorias(
        pd.read_csv(CARPETA_RAW / "feb_trayectorias.csv", dtype={"id_feb": str}))
    trayectorias.to_csv(CARPETA_PROCESSED / "feb_trayectorias.csv", index=False)

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
        "Totales de las fichas: " + (
            "no hay feb_totales.csv" if resumen_fichas is None else
            f"{resumen_fichas['usadas']} de {resumen_fichas['filas']} filas completadas; "
            f"{resumen_fichas['descartadas_por_no_coincidir']} descartadas porque minutos o puntos "
            f"no coinciden con el ranking; fase de la ficha que coincidió: "
            f"{resumen_fichas['fase_elegida']}"),
        "",
        "Porcentaje de filas sin datos de tiro:",
        *[f"  {t}: {tabla[f'{t}_falta'].mean():.1%}" for t in ESTADISTICAS_TIRO.values()],
        "",
        f"Trayectorias: {len(trayectorias)} filas; excluidas por categoría: {len(excluidas)} "
        f"({', '.join(sorted(excluidas['categoria'].unique()))})",
        "",
        "Problemas de calidad:" if problemas else "Sin problemas de calidad detectados.",
        *[f"- {p}" for p in problemas],
    ]
    informe = "\n".join(lineas)
    (CARPETA_PROCESSED / "informe_calidad_feb.txt").write_text(informe, encoding="utf-8")
    print(informe)


if __name__ == "__main__":
    main()