"""Scraping de la web de la ACB."""
"""	Solo se descarga la ficha si jugó desde 2005 · acb.com da medias por partido, no totales · la fecha viene con “(30 años)” y se recorta"""

import argparse
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from bs4 import BeautifulSoup

from src.scraping.cliente import ClienteHTTP

log = logging.getLogger(__name__)

BASE = "https://www.acb.com"
SITEMAP_JUGADORES = f"{BASE}/sitemaps/jugadores/sitemap.xml"
TEMPORADA_MINIMA = 2005

CARPETA_RAW = Path("data/raw")
CARPETA_HTML = CARPETA_RAW / "html_acb"

RE_FICHA = re.compile(r"^/es/liga/jugadores/([a-z0-9-]+)-(\d{6,})/?$")
RE_TEMPORADA = re.compile(r"^\d{2}-\d{2}$")

COLUMNAS_TEMPORADA = [
    "temporada", "club", "partidos", "minutos", "titular",
    "puntos", "puntos_max",
    "t3_anotados", "t3_intentados", "t3_pct",
    "t2_anotados", "t2_intentados", "t2_pct",
    "tl_anotados", "tl_intentados", "tl_pct",
    "reb_of", "reb_def", "rebotes",
    "asistencias", "recuperaciones", "perdidas",
    "tapones_favor", "tapones_contra", "mates",
    "faltas_cometidas", "faltas_recibidas", "mas_menos", "valoracion",
    "victorias", "derrotas",
]

ETIQUETAS_BIO = {
    "Posición": "posicion",
    "Altura": "altura",
    "Fecha nacimiento": "fecha_nacimiento",
    "Nacionalidad": "nacionalidad",
    "Licencia": "licencia",
}

VALIDADORES_BIO = {
    "posicion": lambda v: re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúÑñ /-]{3,30}", v),
    "altura": lambda v: re.fullmatch(r"\d,\d{2}\s*m", v),
    "fecha_nacimiento": lambda v: re.match(r"\d{2}/\d{2}/\d{4}", v),
    "nacionalidad": lambda v: len(v) >= 2 and not v[0].isdigit() and v not in ETIQUETAS_BIO,
    # Códigos vistos: JFL, ESP, EUR, EUR-F, EXT, COT.
    "licencia": lambda v: re.fullmatch(r"[A-ZÑ]{2,4}(-[A-Z]{1,2})?", v),
}


def anio_inicio(temporada_corta):
    """'24-25' -> 2024, '95-96' -> 1995."""
    yy = int(temporada_corta[:2])
    return 1900 + yy if yy >= 50 else 2000 + yy


# --- Lista de jugadores -------------------------------------------------------

def _locs(xml):
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)


def listar_jugadores(cliente):
    indice = cliente.get(SITEMAP_JUGADORES, "sitemap_indice.xml")
    if not indice:
        raise RuntimeError("No se pudo leer el sitemap de jugadores de acb.com")

    jugadores = {}
    for n, url_parte in enumerate(u for u in _locs(indice) if u.endswith(".xml")):
        xml = cliente.get(url_parte, f"sitemap_{n:02d}.xml") or ""
        for url in _locs(xml):
            coincidencia = RE_FICHA.match(urlparse(url).path)
            if coincidencia:
                slug, id_jugador = coincidencia.groups()
                jugadores[id_jugador] = {
                    "id_acb": id_jugador,
                    "slug": slug,
                    "url": f"{BASE}/es/liga/jugadores/{slug}-{id_jugador}",
                }
    log.info("Jugadores en el sitemap: %d", len(jugadores))
    return list(jugadores.values())


# --- Parsers --------------------------------------------------------------------

def _texto(celda):
    return " ".join(celda.get_text(" ").split())


def parsear_temporadas(html):
    """Filas de la tabla de temporadas: una por temporada y club."""
    soup = BeautifulSoup(html, "html.parser")
    filas = []
    for tabla in soup.find_all("table"):
        for tr in tabla.find_all("tr"):
            celdas = tr.find_all(["td", "th"])
            if not celdas:
                continue
            textos = [_texto(c) for c in celdas]
            if not RE_TEMPORADA.match(textos[0]):
                continue
            if sum(1 for t in textos[2:] if t) < 3:
                continue

            if len(textos) == len(COLUMNAS_TEMPORADA):
                fila = dict(zip(COLUMNAS_TEMPORADA, textos))
            else:
                log.warning("Fila con %d celdas (se esperaban %d); se guarda por posición",
                            len(textos), len(COLUMNAS_TEMPORADA))
                fila = {f"col_{i}": t for i, t in enumerate(textos)}
                fila["temporada"] = textos[0]

            enlace_club = celdas[1].find("a") if len(celdas) > 1 else None
            if enlace_club:
                fila["club"] = _texto(enlace_club)
            filas.append(fila)

    unicas = {tuple(sorted(f.items())): f for f in filas}
    return list(unicas.values())


def parsear_ficha(html):
    """Datos biográficos de la ficha del jugador."""
    soup = BeautifulSoup(html, "html.parser")
    for etiqueta in soup(["script", "style", "noscript"]):
        etiqueta.decompose()
    lineas = [ln.strip() for ln in soup.get_text("\n").split("\n") if ln.strip()]

    bio = {}
    for i, linea in enumerate(lineas[:-1]):
        campo = ETIQUETAS_BIO.get(linea)
        if not campo:
            continue
        valor = lineas[i + 1]
        if VALIDADORES_BIO[campo](valor):
            if campo == "fecha_nacimiento":
                valor = valor[:10]  
            bio[campo] = valor 
    return bio


# --- Descarga -------------------------------------------------------------------

def descargar(cliente, jugadores, temporada_minima=TEMPORADA_MINIMA):
    filas_temporadas, filas_jugadores = [], []

    for n, jugador in enumerate(jugadores, start=1):
        id_jugador = jugador["id_acb"]
        if n % 100 == 0:
            log.info("Procesados %d de %d jugadores", n, len(jugadores))

        html_temp = cliente.get(f"{jugador['url']}/temporada", f"{id_jugador}_temporada.html")
        temporadas = parsear_temporadas(html_temp) if html_temp else []
        if not temporadas:
            continue
        if max(anio_inicio(t["temporada"]) for t in temporadas) < temporada_minima:
            continue

        for t in temporadas:
            filas_temporadas.append({"id_acb": id_jugador, **t})

        html_ficha = cliente.get(jugador["url"], f"{id_jugador}_ficha.html")
        bio = parsear_ficha(html_ficha) if html_ficha else {}
        filas_jugadores.append({**jugador, **bio})

    return pd.DataFrame(filas_jugadores), pd.DataFrame(filas_temporadas)


def main():
    parser = argparse.ArgumentParser(description="Descarga jugadores y temporadas de acb.com")
    parser.add_argument("--limite", type=int, help="procesar solo los N primeros jugadores")
    parser.add_argument("--pausa", type=float, default=1.0, help="segundos entre peticiones")
    parser.add_argument("--temporada-minima", type=int, default=TEMPORADA_MINIMA)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cliente = ClienteHTTP(CARPETA_HTML, pausa=args.pausa)

    jugadores = listar_jugadores(cliente)
    if args.limite:
        jugadores = jugadores[: args.limite]

    df_jugadores, df_temporadas = descargar(cliente, jugadores, args.temporada_minima)
    CARPETA_RAW.mkdir(parents=True, exist_ok=True)
    df_jugadores.to_csv(CARPETA_RAW / "acb_jugadores.csv", index=False)
    df_temporadas.to_csv(CARPETA_RAW / "acb_temporadas.csv", index=False)
    log.info("Guardados %d jugadores y %d filas de temporada", len(df_jugadores), len(df_temporadas))


if __name__ == "__main__":
    main()