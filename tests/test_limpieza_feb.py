
import pandas as pd

from src.limpieza_feb import construir_temporadas, validar


def _fila(id_feb, estadistica, total=None, partidos=10, anotados=None, intentados=None,
          solo_nacionales=False, fase="REGULAR", equipo="EQ", temporada=2020):
    return {
        "id_feb": id_feb, "jugador": f"J{id_feb}", "equipo": equipo, "total": total,
        "anotados": anotados, "intentados": intentados, "partidos": partidos,
        "media": None, "celdas": "", "competicion": "segunda_feb", "temporada": temporada,
        "fase": fase, "estadistica": estadistica, "solo_nacionales": solo_nacionales,
    }


def _rankings():
    return pd.DataFrame([
        # Jugador 1: jugó en dos grupos de liga regular la misma temporada.
        _fila("1", "Minutos jugados", 200, 10, fase="GRUPO A"),
        _fila("1", "Minutos jugados", 100, 5, fase="GRUPO B"),
        _fila("1", "Puntos", 80, 10, fase="GRUPO A"),
        _fila("1", "Puntos", 40, 5, fase="GRUPO B"),
        _fila("1", "Rebotes Ofensivos", 10, 10, fase="GRUPO A"),
        _fila("1", "Rebotes Defensivos", 20, 10, fase="GRUPO A"),
        _fila("1", "% Tiros de 3", None, 10, anotados=12, intentados=30, fase="GRUPO A"),
        _fila("1", "% Tiros de 3", None, 5, anotados=3, intentados=10, fase="GRUPO B"),
        _fila("1", "Minutos jugados", 200, 10, solo_nacionales=True, fase="GRUPO A"),
        # Jugador 2: extranjero, sin datos de triples (pocos intentos).
        _fila("2", "Minutos jugados", 400, 20),
        _fila("2", "Puntos", 300, 20),
    ])


def test_una_fila_por_jugador_y_temporada():
    tabla = construir_temporadas(_rankings())
    assert len(tabla) == 2
    uno = tabla.set_index("id_feb").loc["1"]
    assert uno["partidos"] == 15
    assert uno["minutos"] == 300
    assert uno["puntos"] == 120
    assert uno["minutos_partido"] == 20
    assert uno["puntos_40"] == 16          # 40 * 120 / 300
    assert uno["rebotes"] == 30
    assert uno["t3_pct"] == 37.5           # 15 / 40, sumando los dos grupos


def test_nacional_y_tiros_que_faltan():
    tabla = construir_temporadas(_rankings()).set_index("id_feb")
    assert bool(tabla.loc["1", "es_nacional_feb"]) is True
    assert bool(tabla.loc["2", "es_nacional_feb"]) is False
    assert bool(tabla.loc["2", "t3_falta"]) is True
    assert bool(tabla.loc["1", "t3_falta"]) is False
    assert pd.isna(tabla.loc["2", "t3_pct"])


def test_partidos_sin_ranking_de_minutos():
    rankings = pd.DataFrame([_fila("3", "Puntos", 50, 8), _fila("3", "Asistencias", 20, 7)])
    tabla = construir_temporadas(rankings)
    assert tabla.loc[0, "partidos"] == 8
    assert any("sin minutos" in p for p in validar(tabla))


def test_validacion():
    tabla = construir_temporadas(_rankings())
    tabla.loc[0, "minutos_partido"] = 50
    tabla.loc[0, "t3_anotados"] = 99
    problemas = validar(tabla)
    assert any("45 minutos" in p for p in problemas)
    assert any("t3" in p for p in problemas)


def test_estadistica_de_conteo_ausente_es_cero():
    tabla = construir_temporadas(_rankings()).set_index("id_feb")
    assert tabla.loc["2", "asistencias"] == 0      # tiene minutos pero no sale en el ranking
    assert tabla.loc["2", "rebotes"] == 0