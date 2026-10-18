
import re
import unicodedata
from pathlib import Path

import pandas as pd

CARPETA_RAW = Path("data/raw")
CARPETA_PROCESSED = Path("data/processed")

COLUMNAS_PORCENTAJE = ["t2_pct", "t3_pct", "tl_pct"]
COLUMNAS_TEXTO = ["id_acb", "temporada", "club"]
# Estadísticas que acb.com publica como media por partido.
MEDIAS_POR_PARTIDO = [
    "minutos", "puntos", "t2_anotados", "t2_intentados",
    "t3_anotados", "t3_intentados", "tl_anotados", "tl_intentados",
    "reb_of", "reb_def", "rebotes", "asistencias", "recuperaciones",
    "perdidas", "tapones_favor", "tapones_contra", "mates",
    "faltas_cometidas", "faltas_recibidas", "valoracion",
]
# Las que tiene sentido expresar por 40 minutos para comparar jugadores con
# distinto tiempo en pista.
POR_40_MINUTOS = [
    "puntos", "rebotes", "reb_of", "reb_def", "asistencias", "recuperaciones",
    "perdidas", "tapones_favor", "valoracion", "t3_intentados", "tl_intentados",
]


# --- Conversión de valores ------------------------------------------------------

def a_numero(valor):
    """'11,7' -> 11.7 · '0.8' -> 0.8 · '55,6 %' -> 55.6 · '1.234,5' -> 1234.5 · '' -> NaN"""
    if pd.isna(valor):
        return float("nan")
    texto = str(valor).strip().replace("%", "").replace("m", "").strip()
    if texto in ("", "-", "--"):
        return float("nan")
    if ":" in texto:
        return a_minutos(texto)
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return float("nan")


def a_minutos(valor):
    """'23:06' -> 23.1 · '1234:30' -> 1234.5"""
    try:
        minutos, segundos = str(valor).strip().split(":")
        return int(minutos) + int(segundos) / 60
    except (ValueError, AttributeError):
        return float("nan")


def anio_inicio(temporada):
    """'24-25' -> 2024 · '95-96' -> 1995"""
    if not isinstance(temporada, str) or not re.fullmatch(r"\d{2}-\d{2}", temporada):
        return pd.NA
    yy = int(temporada[:2])
    return 1900 + yy if yy >= 50 else 2000 + yy


def normalizar_nombre(nombre):
    """Minúsculas, sin tildes y con las palabras ordenadas.

    Sirve para emparejar a un jugador entre fuentes que escriben el nombre en
    distinto orden: 'PÉREZ GARCÍA, JUAN' (FEB) y 'juan-perez-garcia' (ACB).
    """
    if not isinstance(nombre, str):
        return ""
    texto = unicodedata.normalize("NFKD", nombre)
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    palabras = re.findall(r"[a-z]+", texto)
    return " ".join(sorted(palabras))


# --- Limpieza de tablas -----------------------------------------------------------

def limpiar_temporadas(df):
    df = df.copy()
    df["id_acb"] = df["id_acb"].astype(str)
    for columna in df.columns:
        if columna not in COLUMNAS_TEXTO:
            df[columna] = df[columna].map(a_numero)
    df["anio"] = df["temporada"].map(anio_inicio).astype("Int64")
    df = df.dropna(subset=["anio"]).drop_duplicates()
    for columna in MEDIAS_POR_PARTIDO:
        if columna in df:
            df[f"{columna}_total"] = df[columna] * df["partidos"]
    return df.sort_values(["id_acb", "anio"]).reset_index(drop=True)


def agregar_por_temporada(df):
    """Una fila por jugador y temporada, juntando los clubes si hubo traspaso.

    Se suman los totales y después se vuelven a calcular las medias, porque
    promediar las medias de dos clubes daría el mismo peso a 5 partidos que a 30.
    """
    totales = [f"{c}_total" for c in MEDIAS_POR_PARTIDO if f"{c}_total" in df]
    df = df.copy()
    # Para los porcentajes de tiro se usa la media ponderada por intentos. Con un
    # solo club coincide con el porcentaje publicado por acb.com, que es más
    # exacto que recalcularlo desde medias redondeadas.
    for tipo in ("t2", "t3", "tl"):
        if f"{tipo}_pct" in df and f"{tipo}_intentados_total" in df:
            df[f"_{tipo}_ponderado"] = df[f"{tipo}_pct"] * df[f"{tipo}_intentados_total"]

    ponderados = [c for c in df.columns if c.endswith("_ponderado")]
    agregado = df.groupby(["id_acb", "anio"], as_index=False).agg(
        {"partidos": "sum", **{c: "sum" for c in totales + ponderados},
         "club": lambda clubes: " / ".join(clubes.dropna())}
    )

    partidos = agregado["partidos"].where(agregado["partidos"] > 0)
    for total in totales:
        agregado[total.removesuffix("_total")] = agregado[total] / partidos
    for tipo in ("t2", "t3", "tl"):
        if f"_{tipo}_ponderado" in agregado:
            intentos = agregado[f"{tipo}_intentados_total"].where(agregado[f"{tipo}_intentados_total"] > 0)
            agregado[f"{tipo}_pct"] = agregado[f"_{tipo}_ponderado"] / intentos
    agregado = agregado.drop(columns=ponderados)

    minutos = agregado["minutos_total"].where(agregado["minutos_total"] > 0)
    for columna in POR_40_MINUTOS:
        if f"{columna}_total" in agregado:
            agregado[f"{columna}_40"] = 40 * agregado[f"{columna}_total"] / minutos
    return agregado


def limpiar_jugadores(df):
    df = df.copy()
    df["id_acb"] = df["id_acb"].astype(str)
    if "altura" in df:
        df["altura_cm"] = (df["altura"].map(a_numero) * 100).round()
    if "fecha_nacimiento" in df:
        # Solo se conserva el año: basta para calcular la edad en cada temporada
        # y evita guardar la fecha exacta, que es un dato personal.
        fecha = pd.to_datetime(df["fecha_nacimiento"], format="%d/%m/%Y", errors="coerce")
        df["anio_nacimiento"] = fecha.dt.year.astype("Int64")
        df = df.drop(columns="fecha_nacimiento")
    nacionalidad = df.get("nacionalidad", pd.Series("", index=df.index)).fillna("")
    df["es_espanol"] = nacionalidad.str.contains(r"españa|espanola|española|spain", case=False)
    licencia = df.get("licencia", pd.Series("", index=df.index)).fillna("").str.upper()
    df["es_jfl"] = licencia.eq("JFL")
    return df.drop_duplicates(subset="id_acb").reset_index(drop=True)


# --- Validación --------------------------------------------------------------------

def validar_temporadas(df):
    """Lista de problemas de calidad encontrados. Vacía si todo está bien."""
    problemas = []
    for columna in COLUMNAS_PORCENTAJE:
        if columna in df:
            fuera = df[(df[columna] < 0) | (df[columna] > 100)]
            if len(fuera):
                problemas.append(f"{columna}: {len(fuera)} valores fuera de [0, 100]")
    if "minutos" in df:
        negativos = (df["minutos"] < 0).sum()
        if negativos:
            problemas.append(f"minutos: {negativos} valores negativos")
    if "minutos" in df:
        # Son minutos por partido: más de 50 es imposible incluso con prórrogas.
        excesivos = (df["minutos"] > 50).sum()
        if excesivos:
            problemas.append(f"minutos: {excesivos} filas con más de 50 minutos por partido")
    if {"partidos", "minutos"} <= set(df.columns):
        incoherentes = ((df["partidos"] == 0) & (df["minutos"] > 0)).sum()
        if incoherentes:
            problemas.append(f"{incoherentes} filas con minutos pero sin partidos")
    if {"partidos", "victorias", "derrotas"} <= set(df.columns):
        descuadre = (df["victorias"] + df["derrotas"] != df["partidos"]).sum()
        if descuadre:
            problemas.append(f"{descuadre} filas donde victorias + derrotas no coincide con partidos")
    if "mas_menos" in df and (df["mas_menos"].fillna(0) == 0).all():
        problemas.append("mas_menos vale 0 en todas las filas: no se publica y no debe usarse")
    for tipo in ("t2", "t3", "tl"):
        anotados, intentados = f"{tipo}_anotados", f"{tipo}_intentados"
        if anotados in df and intentados in df:
            imposibles = (df[anotados] > df[intentados]).sum()
            if imposibles:
                problemas.append(f"{tipo}: {imposibles} filas con más anotados que intentados")
    columnas_posicionales = [c for c in df.columns if c.startswith("col_")]
    if columnas_posicionales:
        problemas.append(f"hay filas sin columnas reconocidas ({len(columnas_posicionales)} columnas col_*): "
                         "la tabla de acb.com puede haber cambiado")
    return problemas


def main():
    CARPETA_PROCESSED.mkdir(parents=True, exist_ok=True)
    temporadas = limpiar_temporadas(pd.read_csv(CARPETA_RAW / "acb_temporadas.csv", dtype=str))
    jugadores = limpiar_jugadores(pd.read_csv(CARPETA_RAW / "acb_jugadores.csv", dtype=str))
    por_temporada = agregar_por_temporada(temporadas)

    temporadas.to_csv(CARPETA_PROCESSED / "temporadas_por_club.csv", index=False)
    por_temporada.to_csv(CARPETA_PROCESSED / "temporadas.csv", index=False)
    jugadores.to_csv(CARPETA_PROCESSED / "jugadores.csv", index=False)

    problemas = validar_temporadas(temporadas)
    lineas = [
        f"Jugadores: {len(jugadores)}",
        f"Filas jugador-temporada: {len(por_temporada)}",
        f"Temporadas cubiertas: {por_temporada['anio'].min()} - {por_temporada['anio'].max()}",
        f"Jugadores con nacionalidad española: {int(jugadores['es_espanol'].sum())}",
        f"Jugadores con licencia JFL: {int(jugadores['es_jfl'].sum())}",
        f"Jugadores sin licencia leída: {int(jugadores.get('licencia', pd.Series(dtype=str)).isna().sum())}",
        "",
        "Problemas de calidad:" if problemas else "Sin problemas de calidad detectados.",
        *[f"- {p}" for p in problemas],
    ]
    informe = "\n".join(lineas)
    (CARPETA_PROCESSED / "informe_calidad.txt").write_text(informe, encoding="utf-8")
    print(informe)


if __name__ == "__main__":
    main()