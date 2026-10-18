
from bs4 import BeautifulSoup

from src.scraping.acb import COLUMNAS_TEMPORADA, anio_inicio, parsear_ficha, parsear_temporadas
from src.scraping.feb import (
    a_numero, enlace_siguiente_bloque, enlaces_paginacion, fases_regulares,
    leer_temporadas, objetivo_postback, parsear_ranking,
)


def _fila_temporada(temporada, club, partidos="34"):
    valores = [temporada, f'<a href="/es/liga/equipos/x-1">{club}</a>', partidos]
    valores += ["10"] * (len(COLUMNAS_TEMPORADA) - 3)
    return "<tr>" + "".join(f"<td>{v}</td>" for v in valores) + "</tr>"


def test_temporadas_ignora_esqueleto_y_duplicados():
    esqueleto = "<tr>" + "<td>24-25</td>" + "<td></td>" * (len(COLUMNAS_TEMPORADA) - 1) + "</tr>"
    fila = _fila_temporada("24-25", "Club Uno")
    html = f"<table>{esqueleto}{fila}</table><table>{fila}</table>"
    filas = parsear_temporadas(html)
    assert len(filas) == 1
    assert filas[0]["club"] == "Club Uno"
    assert filas[0]["partidos"] == "34"


def test_temporadas_con_columnas_inesperadas_se_guardan_por_posicion():
    html = "<table><tr><td>23-24</td><td>Club</td><td>1</td><td>2</td><td>3</td></tr></table>"
    filas = parsear_temporadas(html)
    assert filas[0]["temporada"] == "23-24"
    assert "col_4" in filas[0]


def test_ficha_toma_el_valor_real_y_no_el_esqueleto():
    html = """
    <div>Nacionalidad</div><div>Licencia</div>
    <div>Posición</div><div>Base</div>
    <div>Altura</div><div>1,91 m</div>
    <div>Fecha nacimiento</div><div>05/03/2003 (23 años)</div>
    <div>Nacionalidad</div><div>España</div>
    <div>Licencia</div><div>JFL</div>
    """
    bio = parsear_ficha(html)
    assert bio == {
        "posicion": "Base", "altura": "1,91 m", "fecha_nacimiento": "05/03/2003",
        "nacionalidad": "España", "licencia": "JFL",
    }


def test_ficha_acepta_licencias_con_sufijo():
    html = "<div>Licencia</div><div>Globales</div><div>Licencia</div><div>EUR-F</div>"
    assert parsear_ficha(html) == {"licencia": "EUR-F"}


def test_anio_inicio():
    assert anio_inicio("24-25") == 2024
    assert anio_inicio("99-00") == 1999


def test_ranking_feb():
    html = """
    <table>
      <tr><td><a href="Jugador.aspx?i=1&c=555"><img></a></td>
          <td><a href="Jugador.aspx?i=1&c=555">PEREZ GARCIA, JUAN</a></td>
          <td>EQUIPO X</td><td>54</td><td>2</td><td>27,5</td></tr>
      <tr><td>1 <a href="javascript:__doPostBack('grid$_ctl34$_ctl1','')">2</a></td></tr>
    </table>
    """
    soup = BeautifulSoup(html, "html.parser")
    filas = parsear_ranking(soup)
    assert filas == [{"id_feb": "555", "jugador": "PEREZ GARCIA, JUAN", "equipo": "EQUIPO X",
                      "total": 54.0, "anotados": None, "intentados": None,
                      "partidos": 2.0, "media": 27.5, "celdas": "EQUIPO X | 54 | 2 | 27,5"}]
    assert enlaces_paginacion(soup) == [(2, "grid$_ctl34$_ctl1")]


def test_feb_a_numero():
    assert a_numero("15,5") == 15.5
    assert a_numero("1.234") == 1234
    assert a_numero("45,2 %") == 45.2
    assert a_numero("25:30") == 25.5
    assert a_numero("") is None


def test_objetivo_postback_lee_onchange():
    html = """<select name="_ctl0:Main:grupos"
        onchange="javascript:setTimeout(\'__doPostBack(\\\'_ctl0$Main$grupos\\\',\\\'\\\')\', 0)"></select>
        <select name="otro"></select>"""
    soup = BeautifulSoup(html, "html.parser")
    assert objetivo_postback(soup, "_ctl0:Main:grupos") == "_ctl0$Main$grupos"
    assert objetivo_postback(soup, "otro") == "otro"


def test_fases_regulares():
    opciones = [("4", "Play-offs Final"), ("1", "Liga Regular Único"),
                ("2", "LIGA REGULAR ESTE"), ("3", "Copa")]
    assert fases_regulares(opciones) == [("1", "Liga Regular Único"), ("2", "LIGA REGULAR ESTE")]


def _paginador(*textos):
    return "".join(f"<a href=\"javascript:__doPostBack('pag{t}','')\">{t}</a>" for t in textos)


def test_siguiente_bloque():
    primer_bloque = BeautifulSoup(_paginador(*range(2, 11), "..."), "html.parser")
    assert enlace_siguiente_bloque(primer_bloque) == "pag..."
    ultimo_bloque = BeautifulSoup(_paginador("...", 11, 12), "html.parser")
    assert enlace_siguiente_bloque(ultimo_bloque) is None


def test_leer_temporadas():
    assert leer_temporadas("2024") == [2024]
    assert leer_temporadas("2010-2012,2015") == [2010, 2011, 2012, 2015]


def test_ranking_de_porcentaje_separa_anotados_e_intentados():
    html = """<table><tr><td></td>
        <td><a href="Jugador.aspx?i=1&c=7">TOLEDO JIMENEZ, SANTIAGO</a></td>
        <td>PALMA AQUA M.</td><td>24 / 43</td><td>33</td><td>55,81</td></tr></table>"""
    fila = parsear_ranking(BeautifulSoup(html, "html.parser"))[0]
    assert (fila["total"], fila["anotados"], fila["intentados"], fila["media"]) == (None, 24, 43, 55.81)