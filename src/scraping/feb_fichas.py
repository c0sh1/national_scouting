
import argparse
import logging
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from src.scraping.cliente import ClienteHTTP

log = logging.getLogger(__name__)

BASE = "https://baloncestoenvivo.feb.es"
CARPETA_RAW = Path("data/raw")
CARPETA_RANKINGS = CARPETA_RAW / "html_feb"
CARPETA_FICHAS = CARPETA_RAW / "html_feb_fichas"

RE_ENLACE = re.compile(r"Jugador\.aspx\?i=(\d+)&(?:amp;)?c=(\d+)")
RE_TEMPORADA = re.compile(r"^\d{2}/\d{2}$")


ARCHIVO_ENLACES = CARPETA_RAW / "feb_enlaces_fichas.csv"


def enlaces_desde_cache(carpeta=CARPETA_RANKINGS, archivo=ARCHIVO_ENLACES):
    """Un enlace por jugador (c), tomado de las páginas de ranking guardadas.

    Leer miles de páginas tarda unos minutos, así que el resultado se guarda en
    un CSV y las siguientes ejecuciones lo leen directamente. Si se descargan
    rankings nuevos, hay que borrar ese CSV.
    """
    if archivo.exists():
        tabla = pd.read_csv(archivo, dtype=str)
        return dict(zip(tabla["c"], tabla["i"]))
    enlaces = {}
    for ruta in sorted(carpeta.glob("*.html")):
        for i, c in RE_ENLACE.findall(ruta.read_text(encoding="utf-8", errors="ignore")):
            enlaces.setdefault(c, i)
    pd.DataFrame({"c": list(enlaces), "i": list(enlaces.values())}).to_csv(archivo, index=False)
    return enlaces


def _valor(soup, etiqueta):
    """Valor de un dato personal, esté en el mismo elemento que la etiqueta
    ("Altura 208 cm") o en el siguiente ("Altura" | "208 cm")."""
    for nodo in soup.find_all(string=re.compile(rf"^\s*{re.escape(etiqueta)}\b")):
        resto = nodo.strip()[len(etiqueta):].strip(" :")
        if resto:
            return resto
        siguiente = nodo.find_next(string=lambda s: s and s.strip())
        if siguiente:
            return siguiente.strip()
    return None


def parsear_ficha(html):
    soup = BeautifulSoup(html, "html.parser")
    for etiqueta in soup(["script", "style", "noscript"]):
        etiqueta.decompose()

    bio = {}
    fecha = re.search(r"\d{2}/\d{2}/(\d{4})", _valor(soup, "Fecha Nacimiento") or "")
    if fecha:
        bio["anio_nacimiento"] = int(fecha.group(1))
    altura = re.search(r"(\d{3})\s*cm", _valor(soup, "Altura") or "")
    if altura:
        bio["altura_cm"] = int(altura.group(1))
    puesto = _valor(soup, "Puesto")
    if puesto and puesto != "-" and len(puesto) <= 20:
        bio["puesto"] = puesto
    nacionalidad = _valor(soup, "Nacionalidad")
    if nacionalidad and len(nacionalidad) <= 40 and not any(ch.isdigit() for ch in nacionalidad):
        bio["nacionalidad"] = nacionalidad

    trayectoria = []
    for tabla in soup.find_all("table"):
        cabecera = " ".join(tabla.get_text(" ").split()[:12])
        if "Categ" not in cabecera:
            continue
        for tr in tabla.find_all("tr"):
            celdas = [" ".join(td.get_text(" ").split()) for td in tr.find_all("td")]
            if len(celdas) < 3 or not RE_TEMPORADA.match(celdas[0]):
                continue
            # La trayectoria mezcla cargos (jugador, entrenador, delegado...).
            # Solo se guardan las temporadas como jugador: los demás cargos no
            # interesan al proyecto y no hace falta conservarlos.
            licencia = celdas[3] if len(celdas) > 3 else ""
            if licencia and not licencia.lower().startswith("jugador"):
                continue
            trayectoria.append({"temporada": celdas[0], "categoria": celdas[1], "club": celdas[2]})
        break
    return bio, trayectoria


def main():
    parser = argparse.ArgumentParser(description="Fichas de jugador de la FEB")
    parser.add_argument("--limite", type=int)
    parser.add_argument("--pausa", type=float, default=1.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    enlaces = enlaces_desde_cache()
    log.info("Jugadores con enlace en la caché de rankings: %d", len(enlaces))
    if args.limite:
        enlaces = dict(list(enlaces.items())[: args.limite])

    cliente = ClienteHTTP(CARPETA_FICHAS, pausa=args.pausa)
    jugadores, trayectorias = [], []
    for n, (c, i) in enumerate(enlaces.items(), start=1):
        if n % 200 == 0:
            log.info("Procesadas %d de %d fichas", n, len(enlaces))
        html = cliente.get(f"{BASE}/Jugador.aspx?i={i}&c={c}", f"{c}.html")
        if not html:
            continue
        bio, trayectoria = parsear_ficha(html)
        jugadores.append({"id_feb": c, **bio})
        trayectorias.extend({"id_feb": c, **fila} for fila in trayectoria)

    pd.DataFrame(jugadores).to_csv(CARPETA_RAW / "feb_jugadores.csv", index=False)
    pd.DataFrame(trayectorias).to_csv(CARPETA_RAW / "feb_trayectorias.csv", index=False)
    df = pd.DataFrame(jugadores)
    log.info("Guardadas %d fichas. Sin año de nacimiento: %d", len(df),
             int(df["anio_nacimiento"].isna().sum()) if "anio_nacimiento" in df else len(df))


if __name__ == "__main__":
    main()