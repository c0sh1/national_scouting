
import pandas as pd

from src.limpieza_feb import construir_temporadas, integrar_totales, limpiar_trayectorias, validar


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


def test_trayectorias_unifican_categorias_y_quitan_femeninas():
    trayectorias = pd.DataFrame({
        "id_feb": ["1", "1", "1", "2", "2"],
        "temporada": ["05/06", "08/09", "24/25", "97/98", "99/00"],
        "categoria": ["LEB", "LEB ORO", "PRIMERA FEB", "Liga Femenina", "LIGA EBA"],
        "club": ["A", "B", "C", "D", "E"],
    })
    limpia, excluidas = limpiar_trayectorias(trayectorias)
    assert limpia["nivel"].tolist() == ["primera_feb", "primera_feb", "primera_feb", "tercera_feb"]
    assert limpia["anio"].tolist() == [2005, 2008, 2024, 1999]
    assert excluidas["categoria"].tolist() == ["Liga Femenina"]


def _totales(minutos_j2=400, temporada_pagina=2020):
    base = {"competicion": "segunda_feb", "temporada": 2020, "fase": "LR", "partidos": 20,
            "tc_anotados": 50, "tc_intentados": 110, "tapones_contra": 3, "mates": 2,
            "faltas_cometidas": 40, "faltas_recibidas": 60}
    return pd.DataFrame([
        # Jugador 2: el ranking no tenía sus triples (pocos intentos); la ficha sí.
        {**base, "id_feb": "2", "i": "77", "temporada_pagina": temporada_pagina,
         "minutos": minutos_j2, "puntos": 300, "t2_anotados": 40, "t2_intentados": 80,
         "t3_anotados": 4, "t3_intentados": 15, "tl_anotados": 20, "tl_intentados": 30},
        # Fila de play-off: no se suma a la liga regular.
        {**base, "id_feb": "2", "i": "77", "temporada_pagina": temporada_pagina, "fase": "PO",
         "minutos": 50, "puntos": 30, "t2_anotados": 5, "t2_intentados": 9,
         "t3_anotados": 1, "t3_intentados": 2, "tl_anotados": 2, "tl_intentados": 2},
    ])


def test_ficha_completa_los_tiros_que_faltaban():
    tabla, resumen = integrar_totales(construir_temporadas(_rankings()), _totales())
    dos = tabla.set_index("id_feb").loc["2"]
    assert (dos["t3_anotados"], dos["t3_intentados"]) == (4, 15)
    assert not bool(dos["t3_falta"])
    assert dos["tl_pct"] == 100 * 20 / 30
    assert dos["faltas_recibidas_40"] == 40 * 60 / 400
    assert dos["tc_pct"] == 100 * 50 / 110
    assert resumen["usadas"] == 1


def test_ficha_que_no_coincide_se_descarta():
    tabla, resumen = integrar_totales(construir_temporadas(_rankings()), _totales(minutos_j2=999))
    dos = tabla.set_index("id_feb").loc["2"]
    assert bool(dos["t3_falta"])                    # se queda el dato (vacío) del ranking
    assert pd.isna(dos["faltas_recibidas"])
    assert resumen["descartadas_por_no_coincidir"] == 1


def test_ficha_de_otra_temporada_no_se_usa():
    tabla, resumen = integrar_totales(construir_temporadas(_rankings()), _totales(temporada_pagina=2024))
    assert resumen["usadas"] == 0


def test_si_no_hay_lr_se_elige_la_fase_que_coincide():
    totales = _totales()
    totales["fase"] = ["1ª", "PO"]               # la liga regular viene con otro código
    tabla, resumen = integrar_totales(construir_temporadas(_rankings()), totales)
    assert resumen["fase_elegida"] == {"1ª": 1}
    assert tabla.set_index("id_feb").loc["2", "t3_intentados"] == 15


def test_suma_de_fases_cuando_la_liga_regular_esta_partida():
    totales = _totales()
    totales["fase"] = ["1ª", "2ª"]
    totales.loc[0, ["minutos", "puntos"]] = [300, 200]
    totales.loc[1, ["minutos", "puntos"]] = [100, 100]   # 300 + 100 = 400 min, 300 puntos
    tabla, resumen = integrar_totales(construir_temporadas(_rankings()), totales)
    assert resumen["fase_elegida"] == {"todas": 1}
    assert tabla.set_index("id_feb").loc["2", "t3_intentados"] == 17     # 15 + 2