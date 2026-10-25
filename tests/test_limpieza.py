import math

import pandas as pd

from src.limpieza import (
    a_numero, agregar_por_temporada, limpiar_jugadores, limpiar_temporadas,
    normalizar_nombre, validar_temporadas,
)


def test_a_numero_formatos_espanoles():
    assert a_numero("11,7") == 11.7
    assert a_numero("55,6 %") == 55.6
    assert a_numero("1,81 m") == 1.81
    assert a_numero("0.8") == 0.8
    assert a_numero("1.234,5") == 1234.5
    assert a_numero("23:06") == 23.1
    assert math.isnan(a_numero(""))
    assert math.isnan(a_numero(None))


def test_normalizar_nombre_empareja_fuentes():
    assert normalizar_nombre("PÉREZ GARCÍA, JUAN") == normalizar_nombre("juan-perez-garcia")


def _temporadas():
    return pd.DataFrame({
        "id_acb": ["1", "1", "1"],
        "temporada": ["23-24", "23-24", "24-25"],
        "club": ["A", "B", "B"],
        "partidos": ["10", "30", "20"],
        "minutos": ["10:00", "20:00", "25:30"],
        "puntos": ["4,0", "8,0", "10,0"],
        "t3_intentados": ["1,0", "3,0", "4,0"],
        "t3_pct": ["50,0 %", "30,0 %", "40,0 %"],
        "recuperaciones": ["0.5", "1.0", "1.5"],
        "victorias": ["4", "20", "12"],
        "derrotas": ["6", "10", "8"],
    })


def test_totales_desde_medias():
    limpias = limpiar_temporadas(_temporadas())
    assert limpias.loc[0, "puntos_total"] == 40
    assert limpias.loc[0, "minutos_total"] == 100
    assert limpias.loc[1, "recuperaciones"] == 1.0


def test_agregado_pondera_por_partidos():
    agregado = agregar_por_temporada(limpiar_temporadas(_temporadas()))
    fila = agregado[agregado["anio"] == 2023].iloc[0]
    assert fila["partidos"] == 40
    assert fila["puntos"] == 7.0                      
    assert fila["minutos"] == 17.5                    
    assert fila["t3_pct"] == (50 * 10 + 30 * 90) / 100  
    assert fila["puntos_40"] == 40 * 280 / 700
    assert fila["club"] == "A / B"


def test_validacion_detecta_imposibles():
    df = limpiar_temporadas(_temporadas())
    df["t3_anotados"] = [0.5, 4.0, 1.0]
    df.loc[1, "t3_pct"] = 120
    df.loc[2, "minutos"] = 55
    df.loc[2, "victorias"] = 5
    df["mas_menos"] = 0
    problemas = validar_temporadas(df)
    assert any("más anotados" in p for p in problemas)
    assert any("t3_pct" in p for p in problemas)
    assert any("50 minutos" in p for p in problemas)
    assert any("victorias" in p for p in problemas)
    assert any("mas_menos" in p for p in problemas)


def test_limpiar_jugadores():
    df = pd.DataFrame({
        "id_acb": ["1", "2", "2"],
        "altura": ["1,91 m", "2,05 m", "2,05 m"],
        "fecha_nacimiento": ["05/03/2003", "bad", "bad"],
        "nacionalidad": ["España", "Estados Unidos", "Estados Unidos"],
        "licencia": ["jfl", "EXT", "EXT"],
    })
    limpio = limpiar_jugadores(df)
    assert len(limpio) == 2
    assert list(limpio["altura_cm"]) == [191, 205]
    assert list(limpio["es_espanol"]) == [True, False]
    assert list(limpio["es_jfl"]) == [True, False]
    assert limpio.loc[0, "anio_nacimiento"] == 2003
    assert pd.isna(limpio.loc[1, "anio_nacimiento"])
    assert "fecha_nacimiento" not in limpio.columns