
from types import SimpleNamespace

from src.scraping import feb

POR_PAGINA = 30


class WebFalsa:
    def __init__(self, jugadores=65):
        self.jugadores = jugadores
        self.peticiones = 0

    def _select(self, control, opciones, elegido):
        html = f'<select name="{control}" onchange="__doPostBack(\'{control}\',\'\')">'
        for valor, texto in opciones:
            marca = " selected" if valor == elegido else ""
            html += f'<option value="{valor}"{marca}>{texto}</option>'
        return html + "</select>"

    def _pagina(self, estado):
        inicio = (estado["pagina"] - 1) * POR_PAGINA
        ids = range(inicio, min(inicio + POR_PAGINA, self.jugadores))
        if estado["proc"] == feb.PROCEDENCIA_NACIONAL:
            ids = [i for i in ids if i % 2 == 0]
        filas = "".join(
            f'<tr><td></td><td><a href="Jugador.aspx?i=1&c={i}">J{i}</a></td>'
            f'<td>EQ</td><td>{i}</td><td>10</td><td>{i / 10}</td></tr>' for i in ids
        )
        total_paginas = -(-self.jugadores // POR_PAGINA)
        paginador = "".join(
            f"<a href=\"javascript:__doPostBack('pag${n}','')\">{n}</a>"
            for n in range(1, total_paginas + 1) if n != estado["pagina"]
        )
        return f"""<form action="rankings.aspx?g=1">
            <input type="hidden" name="__VIEWSTATE" value="x">
            {self._select(feb.CONTROL_TEMPORADA, [("2025", "2025/2026"), ("2024", "2024/2025")], estado["temp"])}
            {self._select(feb.CONTROL_FASE, [("9", "Play-offs Final"), ("8", "Liga Regular Único")], estado["fase"])}
            {self._select(feb.CONTROL_ESTADISTICA, [("0", "Puntos"), ("13", "Minutos jugados")], estado["est"])}
            {self._select(feb.CONTROL_PROCEDENCIA, [("0", "Todos"), ("39", "Nacional")], estado["proc"])}
            <table>{filas}<tr><td>{paginador}</td></tr></table></form>"""

    def get_respuesta(self, url):
        self.peticiones += 1
        estado = {"temp": "2025", "fase": "9", "est": "0", "proc": "0", "pagina": 1}
        return SimpleNamespace(text=self._pagina(estado), url=url)

    def post(self, url, datos):
        self.peticiones += 1
        estado = {
            "temp": datos[feb.CONTROL_TEMPORADA], "fase": datos[feb.CONTROL_FASE],
            "est": datos[feb.CONTROL_ESTADISTICA], "proc": datos[feb.CONTROL_PROCEDENCIA],
            "pagina": 1,
        }
        if datos["__EVENTTARGET"].startswith("pag$"):
            estado["pagina"] = int(datos["__EVENTTARGET"].split("$")[1])
        return SimpleNamespace(text=self._pagina(estado), url=url)


def test_descarga_temporada_recorre_fase_estadisticas_y_paginas(tmp_path, monkeypatch):
    monkeypatch.setattr(feb, "CARPETA_HTML", tmp_path / "html")
    monkeypatch.setattr(feb, "CARPETA_PARTES", tmp_path / "partes")
    monkeypatch.setattr(feb, "CARPETA_RAW", tmp_path)
    (tmp_path / "html").mkdir()
    (tmp_path / "partes").mkdir()

    web = WebFalsa(jugadores=65)
    feb.descargar_temporada(web, "primera_feb", 2025, ["Puntos"])
    datos = feb.unir_partes()

    puntos = datos[(datos["estadistica"] == "Puntos") & ~datos["solo_nacionales"]]
    assert len(puntos) == 65                       
    assert set(puntos["fase"]) == {"Liga Regular Único"}
    nacionales = datos[datos["solo_nacionales"]]
    assert len(nacionales) == 33                 
    assert set(nacionales["estadistica"]) == {"Minutos jugados"}

    peticiones = web.peticiones
    feb.descargar_temporada(web, "primera_feb", 2025, ["Puntos"])
    assert web.peticiones == peticiones + 1        