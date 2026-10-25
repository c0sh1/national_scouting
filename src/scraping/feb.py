" Scraping de la web de la FEB: rankings de jugadores por temporada, fase y estadística."


import argparse
import logging
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import pandas as pd
from bs4 import BeautifulSoup

from src.scraping.cliente import ClienteHTTP

log = logging.getLogger(__name__)

BASE = "https://baloncestoenvivo.feb.es"
COMPETICIONES = {
    "primera_feb": (1, "primerafeb"),
    "segunda_feb": (2, "segundafeb"),
    "liga_u": (74, "ligau"),
}

PREFIJO = "_ctl0:MainContentPlaceHolderMaster:"
CONTROL_TEMPORADA = PREFIJO + "temporadasDropDownList"
CONTROL_FASE = PREFIJO + "gruposDropDownList"
CONTROL_ESTADISTICA = PREFIJO + "rankingsDropDownList"
CONTROL_PROCEDENCIA = PREFIJO + "nacionalDropDownList"

PROCEDENCIA_TODOS = "0"
PROCEDENCIA_NACIONAL = "39"

ESTADISTICAS = [
    "Puntos", "Rebotes Ofensivos", "Rebotes Defensivos", "Asistencias",
    "Balones recuperados", "Balones perdidos", "Tapones a favor", "Valoración",
    "Minutos jugados", "% Tiros de 2", "% Tiros de 3", "% Tiros Libres",
]
MAX_PAGINAS = 60  # tope de seguridad por si la paginación entra en bucle

CARPETA_RAW = Path("data/raw")
CARPETA_HTML = CARPETA_RAW / "html_feb"
CARPETA_PARTES = CARPETA_RAW / "feb_partes"


# --- Utilidades -----------------------------------------------------------------

def a_numero(texto):
    """'15,5' -> 15.5 · '1.234' -> 1234 · '25:30' -> 25.5 · '' -> None"""
    texto = (texto or "").replace("%", "").strip()
    if ":" in texto:
        try:
            minutos, segundos = texto.split(":")
            return int(minutos) + int(segundos) / 60
        except ValueError:
            return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):
        texto = texto.replace(".", "")
    try:
        return float(texto)
    except ValueError:
        return None


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower().strip()


def nombre_archivo(*partes):
    return "_".join(re.sub(r"[^a-z0-9]+", "-", normalizar(str(p))).strip("-") for p in partes)


# --- Lectura del formulario -------------------------------------------------------

def campos_formulario(soup):
    """Campos que ASP.NET necesita de vuelta en cada postback."""
    campos = {}
    for entrada in soup.find_all("input"):
        nombre = entrada.get("name")
        if nombre and entrada.get("type", "text") in ("hidden", "text"):
            campos[nombre] = entrada.get("value", "")
    for desplegable in soup.find_all("select"):
        nombre = desplegable.get("name")
        if not nombre:
            continue
        elegida = desplegable.find("option", selected=True) or desplegable.find("option")
        if elegida is not None:
            campos[nombre] = elegida.get("value", "")
    return campos


def opciones(soup, control):
    desplegable = soup.find("select", attrs={"name": control})
    if desplegable is None:
        return []
    return [(o.get("value"), o.get_text(strip=True)) for o in desplegable.find_all("option")]


def objetivo_postback(soup, control):
    desplegable = soup.find("select", attrs={"name": control})
    onchange = desplegable.get("onchange", "") if desplegable else ""
    coincidencia = re.search(r"__doPostBack\(\\?'([^'\\]+)", onchange)
    return coincidencia.group(1) if coincidencia else control


def fases_regulares(lista_opciones):
    return [(valor, texto) for valor, texto in lista_opciones if "regular" in normalizar(texto)]


def parsear_ranking(soup):
    filas = []
    for enlace in soup.select("a[href*='Jugador.aspx']"):
        texto = " ".join(enlace.get_text(" ").split())
        if not texto:
            continue  
        celdas = enlace.find_parent("tr").find_all("td")
        valores = [" ".join(c.get_text(" ").split()) for c in celdas]
        parametros = parse_qs(urlparse(enlace["href"]).query)
        total = valores[3] if len(valores) > 3 else ""
        tiros = re.fullmatch(r"(\d+)\s*/\s*(\d+)", total)
        filas.append({
            "id_feb": parametros.get("c", [None])[0],
            "jugador": texto,
            "equipo": valores[2] if len(valores) > 2 else None,
            "total": None if tiros else a_numero(total),
            "anotados": int(tiros.group(1)) if tiros else None,
            "intentados": int(tiros.group(2)) if tiros else None,
            "partidos": a_numero(valores[4]) if len(valores) > 4 else None,
            "media": a_numero(valores[5]) if len(valores) > 5 else None,
            "celdas": " | ".join(valores[2:]),
        })
    return filas


def enlaces_paginacion(soup):
    objetivos = []
    for enlace in soup.find_all("a", href=True):
        coincidencia = re.match(r"javascript:__doPostBack\('([^']+)'", enlace["href"])
        if coincidencia and enlace.get_text(strip=True).isdigit():
            objetivos.append((int(enlace.get_text(strip=True)), coincidencia.group(1)))
    return objetivos


def enlace_siguiente_bloque(soup):
    paginador = []
    for enlace in soup.find_all("a", href=True):
        coincidencia = re.match(r"javascript:__doPostBack\('([^']+)'", enlace["href"])
        texto = enlace.get_text(strip=True)
        if coincidencia and (texto.isdigit() or texto == "..."):
            paginador.append((texto, coincidencia.group(1)))
    if paginador and paginador[-1][0] == "..." and any(t.isdigit() for t, _ in paginador):
        return paginador[-1][1]
    return None


# --- Navegación ----------------------------------------------------------------------

class PaginaFEB:

    def __init__(self, cliente):
        self.cliente = cliente
        self.soup = None
        self.accion = None

    def _cargar(self, respuesta):
        self.soup = BeautifulSoup(respuesta.text, "html.parser")
        formulario = self.soup.find("form")
        self.accion = urljoin(respuesta.url, formulario.get("action", "")) if formulario else respuesta.url

    def abrir(self, url):
        self._cargar(self.cliente.get_respuesta(url))

    def postback(self, objetivo, cambios=None):
        datos = campos_formulario(self.soup)
        datos.update(cambios or {})
        datos["__EVENTTARGET"] = objetivo
        datos["__EVENTARGUMENT"] = ""
        self._cargar(self.cliente.post(self.accion, datos))

    def valor_actual(self, control):
        return campos_formulario(self.soup).get(control)

    def elegir(self, control, valor):
        if self.valor_actual(control) != valor:
            self.postback(objetivo_postback(self.soup, control), {control: valor})
        if self.valor_actual(control) != valor:
            raise RuntimeError(f"La web no aceptó {control} = {valor}")

    def todas_las_paginas(self, guardar_como=None):
        filas = parsear_ranking(self.soup)
        pagina = 1
        if guardar_como:
            (CARPETA_HTML / f"{guardar_como}_p01.html").write_text(str(self.soup), encoding="utf-8")
        while pagina < MAX_PAGINAS:
            enlaces = dict(enlaces_paginacion(self.soup))
            objetivo = enlaces.get(pagina + 1) or enlace_siguiente_bloque(self.soup)
            if not objetivo:
                break
            vistos = {f["id_feb"] for f in filas}
            self.postback(objetivo)
            nuevas = parsear_ranking(self.soup)
            if not nuevas or {f["id_feb"] for f in nuevas} <= vistos:
                break
            pagina += 1
            filas.extend(nuevas)
            if guardar_como:
                (CARPETA_HTML / f"{guardar_como}_p{pagina:02d}.html").write_text(str(self.soup), encoding="utf-8")
        return filas


# --- Descarga ------------------------------------------------------------------------

def valor_estadistica(soup, nombre):
    for valor, texto in opciones(soup, CONTROL_ESTADISTICA):
        if normalizar(texto) == normalizar(nombre):
            return valor
    raise ValueError(f"Estadística '{nombre}' no encontrada. Opciones: "
                     f"{[t for _, t in opciones(soup, CONTROL_ESTADISTICA)]}")


def descargar_temporada(cliente, competicion, temporada, estadisticas):
    """Descarga los rankings de una temporada. Cada combinación se guarda en
    data/raw/feb_partes y se salta si ya existe, para poder relanzar."""
    g, nm = COMPETICIONES[competicion]
    pagina = PaginaFEB(cliente)
    pagina.abrir(f"{BASE}/rankings.aspx?g={g}&t={temporada}&nm={nm}")
    pagina.elegir(CONTROL_TEMPORADA, str(temporada))

    fases = fases_regulares(opciones(pagina.soup, CONTROL_FASE))
    if not fases:
        log.warning("%s %s: sin fase regular. Fases disponibles: %s", competicion, temporada,
                    [t for _, t in opciones(pagina.soup, CONTROL_FASE)])
        return

    trabajos = [(e, PROCEDENCIA_TODOS) for e in estadisticas]
    trabajos.append(("Minutos jugados", PROCEDENCIA_NACIONAL))

    for valor_fase, texto_fase in fases:
        for estadistica, procedencia in trabajos:
            clave = nombre_archivo(competicion, temporada, texto_fase, estadistica, procedencia)
            parte = CARPETA_PARTES / f"{clave}.csv"
            if parte.exists():
                continue
            pagina.elegir(CONTROL_FASE, valor_fase)
            pagina.elegir(CONTROL_PROCEDENCIA, procedencia)
            pagina.elegir(CONTROL_ESTADISTICA, valor_estadistica(pagina.soup, estadistica))
            filas = pagina.todas_las_paginas(guardar_como=clave)
            log.info("%s %s %s · %s (%s): %d jugadores", competicion, temporada, texto_fase,
                     estadistica, "nacional" if procedencia == PROCEDENCIA_NACIONAL else "todos", len(filas))
            pd.DataFrame(filas).assign(
                competicion=competicion, temporada=temporada, fase=texto_fase,
                estadistica=estadistica, solo_nacionales=procedencia == PROCEDENCIA_NACIONAL,
            ).to_csv(parte, index=False)


def unir_partes():
    partes = sorted(CARPETA_PARTES.glob("*.csv"))
    if not partes:
        return None
    datos = pd.concat((pd.read_csv(p, dtype={"id_feb": str}) for p in partes), ignore_index=True)
    datos.to_csv(CARPETA_RAW / "feb_rankings.csv", index=False)
    return datos


def leer_temporadas(texto):
    anios = []
    for trozo in texto.split(","):
        if "-" in trozo:
            inicio, fin = trozo.split("-")
            anios.extend(range(int(inicio), int(fin) + 1))
        else:
            anios.append(int(trozo))
    return anios


# --- Exploración -----------------------------------------------------------------------

def explorar(cliente, competicion="primera_feb", temporada=2025):
    g, nm = COMPETICIONES[competicion]
    url = f"{BASE}/rankings.aspx?g={g}&t={temporada}&nm={nm}"
    pagina = PaginaFEB(cliente)
    pagina.abrir(url)
    ruta = CARPETA_HTML / f"exploracion_{competicion}_{temporada}.html"
    ruta.write_text(str(pagina.soup), encoding="utf-8")

    print(f"Formulario envía a: {pagina.accion}")
    print(f"HTML guardado en: {ruta}\n")
    print("Desplegables:")
    for desplegable in pagina.soup.find_all("select"):
        lista = opciones(pagina.soup, desplegable.get("name"))
        print(f"  {desplegable.get('name')}  ({len(lista)} opciones)")
        for valor, texto in lista[:12]:
            print(f"      {valor!r}: {texto}")
    filas = parsear_ranking(pagina.soup)
    print(f"\nFilas de jugador leídas en la primera página: {len(filas)}")
    for fila in filas[:3]:
        print("  ", fila)
    print("\nPáginas del ranking:", [n for n, _ in enlaces_paginacion(pagina.soup)])


def main():
    parser = argparse.ArgumentParser(description="Estadísticas de jugadores de la FEB")
    parser.add_argument("--explorar", action="store_true")
    parser.add_argument("--competicion", nargs="+", default=["primera_feb"], choices=COMPETICIONES)
    parser.add_argument("--temporadas", default="2025", help="'2024', '2010-2025' o '2010,2015'")
    parser.add_argument("--estadisticas", nargs="+", default=ESTADISTICAS)
    parser.add_argument("--pausa", type=float, default=1.0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    CARPETA_HTML.mkdir(parents=True, exist_ok=True)
    CARPETA_PARTES.mkdir(parents=True, exist_ok=True)
    cliente = ClienteHTTP(CARPETA_HTML, pausa=args.pausa)

    if args.explorar:
        explorar(cliente, args.competicion[0], leer_temporadas(args.temporadas)[0])
        return

    for competicion in args.competicion:
        for temporada in leer_temporadas(args.temporadas):
            try:
                descargar_temporada(cliente, competicion, temporada, args.estadisticas)
            except Exception:
                log.exception("Fallo en %s %s; se continúa con la siguiente", competicion, temporada)

    datos = unir_partes()
    if datos is not None:
        log.info("feb_rankings.csv: %d filas, %d jugadores distintos", len(datos), datos["id_feb"].nunique())


if __name__ == "__main__":
    main()