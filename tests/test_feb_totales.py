from src.scraping.feb_totales import pares_desde_cache, parsear_totales

CABECERA = ("<tr><th>FASE</th><th>Part</th><th>MIN</th><th>PT</th><th>T2</th><th>T3</th><th>TC</th>"
            "<th>TL</th><th>RO</th><th>RD</th><th>RT</th><th>AS</th><th>BR</th><th>BP</th><th>TF</th>"
            "<th>TC</th><th>MT</th><th>FC</th><th>FR</th><th>VA</th></tr>")


def _fila(*valores):
    return "<tr>" + "".join(f"<td>{v}</td>" for v in valores) + "</tr>"


FICHA = f"""
<select><option>2026/2027</option><option selected>2024/2025</option></select>
<p>Temporada 2024/2025</p>
<table>{CABECERA}
{_fila("LR", 4, "30:10", "18,3", "66,7%", "50%", "58,8%", "100%", "1,8", "5,5", "7,3", "1,5", "0,3", 1, 0, 0, 0, "0,8", "2,5", "22,8")}
</table>
<table>{CABECERA}
{_fila("LR", 4, "120:43", 73, "18/27", "12/24", "30/51", "1/1", 7, 22, 29, 6, 1, 4, 0, 2, 1, 3, 10, 91)}
{_fila("", 4, "120:43", 73, "18/27", "12/24", "30/51", "1/1", 7, 22, 29, 6, 1, 4, 0, 2, 1, 3, 10, 91)}
</table>
"""


def test_totales_usa_la_tabla_de_totales_y_separa_tiros():
    temporada, filas = parsear_totales(FICHA)
    assert temporada == 2024                      
    assert len(filas) == 2
    lr = filas[0]
    assert lr["fase"] == "LR"
    assert abs(lr["minutos"] - 120.7167) < 0.001
    assert (lr["t2_anotados"], lr["t2_intentados"]) == (18, 27)
    assert (lr["tl_anotados"], lr["tl_intentados"]) == (1, 1)
    assert lr["tapones_contra"] == 2 and lr["mates"] == 1      
    assert lr["faltas_recibidas"] == 10
    assert filas[1]["fase"] is None               


def test_temporada_sin_desplegable():
    temporada, _ = parsear_totales("<p>Temporada 2019/2020</p>")
    assert temporada == 2019


def test_pares_desde_nombres_de_pagina(tmp_path):
    carpeta = tmp_path / "html"
    carpeta.mkdir()
    (carpeta / "primera-feb_2024_liga-regular-unico_puntos_0_p01.html").write_text(
        '<a href="Jugador.aspx?i=5&amp;c=7">A</a><a href="Jugador.aspx?i=6&c=8">B</a>')
    (carpeta / "segunda-feb_2010_regular_puntos_0_p01.html").write_text('<a href="Jugador.aspx?i=9&c=7">A</a>')
    (carpeta / "exploracion_primera_feb_2025.html").write_text('<a href="Jugador.aspx?i=1&c=2">X</a>')
    pares = pares_desde_cache(carpeta, tmp_path / "pares.csv")
    assert sorted(map(tuple, pares[["c", "i", "competicion", "temporada"]].values.tolist())) == [
        ("7", "5", "primera_feb", 2024), ("7", "9", "segunda_feb", 2010), ("8", "6", "primera_feb", 2024)]
    assert (tmp_path / "pares.csv").exists()