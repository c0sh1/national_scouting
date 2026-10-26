"""Scraping de la web de la FEB y de la ACB, con caché en disco y pausas entre peticiones."""


import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

ERRORES_TEMPORALES = {429, 500, 502, 503, 504}


class ClienteHTTP:
    """Hace las peticiones de todos los scrapers: con pausa, reintentos y caché."""
    def __init__(self, carpeta_cache, pausa=1.0, reintentos=3, timeout=25):
        self.carpeta_cache = Path(carpeta_cache)
        self.carpeta_cache.mkdir(parents=True, exist_ok=True)
        self.pausa = pausa
        self.reintentos = reintentos
        self.timeout = timeout
        self._ultima_peticion = 0.0

        """El correo va en el User-Agent para que la web pueda contactar. Se lee de .env."""
        contacto = os.getenv("CONTACTO_SCRAPER", "sin-contacto")
        self.sesion = requests.Session()
        self.sesion.headers.update({
            "User-Agent": f"proyecto-academico-baloncesto/1.0 ({contacto})",
            "Accept-Language": "es-ES,es;q=0.9",
        })

    def _esperar_turno(self):
        """Espera lo necesario para no hacer más de una petición."""
        transcurrido = time.monotonic() - self._ultima_peticion
        if transcurrido < self.pausa:
            time.sleep(self.pausa - transcurrido)
        self._ultima_peticion = time.monotonic()

    def ruta_cache(self, nombre):
        """Ruta del fichero donde se guarda una página descargada."""
        return self.carpeta_cache / nombre

    def post(self, url, datos):
        """POST con la misma pausa y reintentos que get(), sin caché. Lo usan los formularios ASP.NET de la FEB."""
        espera = 2.0
        for intento in range(1, self.reintentos + 1):
            self._esperar_turno()
            try:
                respuesta = self.sesion.post(url, data=datos, timeout=self.timeout)
            except requests.RequestException as error:
                log.warning("Fallo de red en POST %s (%s), intento %d", url, error, intento)
                time.sleep(espera)
                espera *= 2
                continue
            if respuesta.status_code in ERRORES_TEMPORALES:
                log.warning("HTTP %d en POST %s, intento %d", respuesta.status_code, url, intento)
                time.sleep(espera)
                espera *= 2
                continue
            respuesta.raise_for_status()
            return respuesta
        raise RuntimeError(f"Sin respuesta válida tras {self.reintentos} intentos: POST {url}")

    def get_respuesta(self, url):
        """GET sin caché que devuelve la respuesta completa (para conocer la URL final)."""
        self._esperar_turno()
        respuesta = self.sesion.get(url, timeout=self.timeout)
        respuesta.raise_for_status()
        return respuesta

    def get(self, url, nombre_cache=None):
        """Devuelve el texto de la página, o None si no existe (404). Si se indica nombre_cache y el fichero ya está en disco, no hay petición."""
        if nombre_cache:
            ruta = self.ruta_cache(nombre_cache)
            if ruta.exists():
                return ruta.read_text(encoding="utf-8")

        espera = 2.0
        for intento in range(1, self.reintentos + 1):
            self._esperar_turno()
            try:
                respuesta = self.sesion.get(url, timeout=self.timeout)
            except requests.RequestException as error:
                log.warning("Fallo de red en %s (%s), intento %d", url, error, intento)
                time.sleep(espera)
                espera *= 2
                continue

            if respuesta.status_code == 200:
                if nombre_cache:
                    self.ruta_cache(nombre_cache).write_text(respuesta.text, encoding="utf-8")
                return respuesta.text
            if respuesta.status_code == 404:
                return None
            if respuesta.status_code in ERRORES_TEMPORALES:
                log.warning("HTTP %d en %s, intento %d", respuesta.status_code, url, intento)
                time.sleep(espera)
                espera *= 2
                continue
            respuesta.raise_for_status()

        raise RuntimeError(f"Sin respuesta válida tras {self.reintentos} intentos: {url}")