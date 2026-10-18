
from src.scraping.feb_fichas import RE_ENLACE, parsear_ficha

FICHA = """
<div><span>Puesto</span><span>A-Pivot</span></div>
<div><span>Altura 208 cm</span><span>Peso - Kg</span></div>
<div><span>Fecha Nacimiento</span><span>24/10/1991</span></div>
<div><span>Nacionalidad</span><span>ESPAÑA</span></div>
<table>
  <tr><th>Temp.</th><th>Categ.</th><th>Club [Equipo]</th><th>Licencia</th></tr>
  <tr><td>09/10</td><td>EBA</td><td>ESTUDIANTES [ASEFA ESTUDIANTES]</td><td>Jugador/a</td></tr>
  <tr><td>10/11</td><td>EBA</td><td>ESTUDIANTES [ASEFA ESTUDIANTES]</td><td>Jugador/a</td></tr>
  <tr><td>20/21</td><td>Liga Femenina</td><td>CLUB X</td><td>Entrenador/a</td></tr>
</table>
"""


def test_ficha_feb():
    bio, trayectoria = parsear_ficha(FICHA)
    assert bio == {"anio_nacimiento": 1991, "altura_cm": 208, "puesto": "A-Pivot", "nacionalidad": "ESPAÑA"}
    assert trayectoria[0] == {"temporada": "09/10", "categoria": "EBA",
                              "club": "ESTUDIANTES [ASEFA ESTUDIANTES]"}
    assert len(trayectoria) == 2          # la temporada como entrenador no se guarda


def test_enlaces_con_y_sin_entidad_html():
    assert RE_ENLACE.findall('href="Jugador.aspx?i=1010494&amp;c=1382710"') == [("1010494", "1382710")]
    assert RE_ENLACE.findall("Jugador.aspx?i=5&c=7") == [("5", "7")]