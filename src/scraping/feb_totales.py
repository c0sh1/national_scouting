
import argparse
import logging
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from src.scraping.cliente import ClienteHTTP
from src.scraping.feb import COMPETICIONES
from src.scraping.feb_fichas import ARCHIVO_ENLACES, CARPETA_FICHAS, CARPETA_RANKINGS, RE_ENLACE

log = logging.getLogger(__name__)

BASE = "https://baloncestoenvivo.feb.es"
CARPETA_RAW = Path("data/raw")
ARCHIVO_PARES = CARPETA_RAW / "feb_enlaces_temporadas.csv"

# Columnas de la tabla de totales, en orden. "TC" aparece dos veces en la web:
# primero tiros de campo y después tapones en contra.
COLUMNAS_TOTALES = [
    "fase", "partidos", "minutos", "puntos", "t2", "t3", "tc", "tl",
    "reb_of", "reb_def", "rebotes", "asistencias", "recuperaciones", "perdidas",
    "tapones_favor", "tapones_contra", "mates", "faltas_cometidas", "faltas_recibidas", "valoracion",
]
TIROS = ["t2", "t3", "tc", "tl"]
PREFIJOS_COMPETICION = {nombre.replace("_", "-"): nombre for nombre in COMPETICIONES}


def pares_desde_cache(carpeta=CARPETA_RANKINGS, archivo=ARCHIVO_PARES):
    """Pares (jugador, equipo) con la competición y temporada de su ranking.

    Igual que los enlaces de las fichas, se guardan en un CSV para no releer
    las páginas en cada ejecución. Si se descargan rankings nuevos, hay que
    borrar ese CSV.
    """
    if archivo.exists():
        return pd.read_csv(archivo, dtype={"c": str, "i": str})
    pares = {}
    for ruta in sorted(carpeta.glob("*.html")):
        partes = ruta.stem.split("_")
        competicion = PREFIJOS_COMPETICION.get(partes[0])
        if competicion is None or len(partes) < 2 or not partes[1].isdigit():
            continue  # páginas de exploración u otras
        temporada = int(partes[1])
        for i, c in RE_ENLACE.findall(ruta.read_text(encoding="utf-8", errors="ignore")):
            pares.setdefault((c, i), (competicion, temporada))
    tabla = pd.DataFrame(
        [(c, i, comp, temp) for (c, i), (comp, temp) in pares.items()],
        columns=["c", "i", "competicion", "temporada"],
    )
    tabla.to_csv(archivo, index=False)
    return tabla


def a_numero(texto):
    texto = (texto or "").strip()
    if ":" in texto:
        minutos, segundos = texto.split(":")
        return int(minutos) + int(segundos) / 60
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def temporada_mostrada(soup):
    """Temporada de la ficha: la opción elegida en el desplegable de temporadas
    o, si no lo hay, el texto "Temporada AAAA/AAAA" fuera de los desplegables.
    No basta con buscar el texto en toda la página, porque el desplegable
    también lista todas las temporadas."""
    for desplegable in soup.find_all("select"):
        elegida = desplegable.find("option", selected=True)
        if elegida and re.fullmatch(r"\d{4}/\d{4}", elegida.get_text(strip=True)):
            return int(elegida.get_text(strip=True)[:4])
    copia = BeautifulSoup(str(soup), "html.parser")
    for desplegable in copia.find_all("select"):
        desplegable.decompose()
    encontrada = re.search(r"Temporada\s+(\d{4})/\d{4}", copia.get_text(" "))
    return int(encontrada.group(1)) if encontrada else None


def parsear_totales(html):
    """Filas de la tabla de totales de la temporada, una por fase.

    Hay dos tablas con las mismas cabeceras (medias y totales); la de totales
    se reconoce porque los tiros vienen como "anotados/intentados".
    """
    soup = BeautifulSoup(html, "html.parser")
    temporada = temporada_mostrada(soup)
    filas = []
    for tabla in soup.find_all("table"):
        cabecera = " ".join(tabla.get_text(" ").split()[:40])
        if not ("Part" in cabecera and "MIN" in cabecera and "T2" in cabecera):
            continue
        candidatas = []
        for tr in tabla.find_all("tr"):
            celdas = [" ".join(td.get_text(" ").split()) for td in tr.find_all("td")]
            if len(celdas) == len(COLUMNAS_TOTALES) and "/" in celdas[4]:
                candidatas.append(dict(zip(COLUMNAS_TOTALES, celdas)))
        if candidatas:
            filas = candidatas
            break

    resultado = []
    for fila in filas:
        limpia = {"fase": fila["fase"] or None}
        for columna in COLUMNAS_TOTALES[1:]:
            if columna in TIROS:
                anotados, _, intentados = fila[columna].partition("/")
                limpia[f"{columna}_anotados"] = a_numero(anotados)
                limpia[f"{columna}_intentados"] = a_numero(intentados)
            else:
                limpia[columna] = a_numero(fila[columna])
        resultado.append(limpia)
    return temporada, resultado


def main():
    parser = argparse.ArgumentParser(description="Totales por temporada desde las fichas de la FEB")
    parser.add_argument("--limite", type=int)
    parser.add_argument("--pausa", type=float, default=1.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    pares = pares_desde_cache()
    log.info("Pares jugador-equipo en la caché de rankings: %d", len(pares))
    if args.limite:
        pares = pares.head(args.limite)

    # Enlace usado para la ficha de datos personales: esa página ya está en disco.
    base = {}
    if ARCHIVO_ENLACES.exists():
        enlaces = pd.read_csv(ARCHIVO_ENLACES, dtype=str)
        base = dict(zip(enlaces["c"], enlaces["i"]))

    cliente = ClienteHTTP(CARPETA_FICHAS, pausa=args.pausa)
    filas = []
    for n, par in enumerate(pares.itertuples(), start=1):
        if n % 500 == 0:
            log.info("Procesadas %d de %d fichas", n, len(pares))
        nombre_cache = f"{par.c}.html" if base.get(par.c) == par.i else f"{par.c}_{par.i}.html"
        html = cliente.get(f"{BASE}/Jugador.aspx?i={par.i}&c={par.c}", nombre_cache)
        if not html:
            continue
        temporada_pagina, totales = parsear_totales(html)
        for fila in totales:
            filas.append({"id_feb": par.c, "i": par.i, "competicion": par.competicion,
                          "temporada": par.temporada, "temporada_pagina": temporada_pagina, **fila})

    tabla = pd.DataFrame(filas)
    tabla.to_csv(CARPETA_RAW / "feb_totales.csv", index=False)
    if tabla.empty:
        log.warning("No se ha leído ninguna tabla de totales")
        return
    distinta = (tabla["temporada_pagina"] != tabla["temporada"]).sum()
    log.info("Guardadas %d filas de %d pares. Filas cuya ficha muestra otra temporada: %d",
             len(tabla), tabla[["id_feb", "i"]].drop_duplicates().shape[0], distinta)
    log.info("Fases encontradas: %s", tabla["fase"].fillna("(total)").value_counts().to_dict())


if __name__ == "__main__":
    main()