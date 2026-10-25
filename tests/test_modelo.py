import numpy as np
import pandas as pd

from src.modelo import (VARIABLES, captura_en_top, explicar, grupo_puesto, preparar_variables,
                        puesto_normalizado, separar)


def _tabla():
    return pd.DataFrame({
        "competicion": ["primera_feb", "segunda_feb", "primera_feb"],
        "temporada": [2020, 2021, 2024],
        "minutos": [400.0, 0.0, 800.0],
        "t3_intentados": [40, 10, None],
        "puesto": ["Ala-Pívot", "Base", None],
        "es_nacional_feb": [1, 0, 1],
        "t3_falta": [False, True, False],
        "se_asienta": [1, 0, None],
        "puntos_40": [15.0, 10.0, 20.0],
    })


def test_preparar_variables_columnas_y_derivadas():
    x = preparar_variables(_tabla())
    assert list(x.columns) == VARIABLES
    assert x.loc[0, "triples_intentados_40"] == 4.0          
    assert np.isnan(x.loc[1, "triples_intentados_40"])        
    assert x["primera_feb"].tolist() == [1, 0, 1]
    assert x.loc[0, "interior"] == 1 and x.loc[1, "exterior"] == 1
    assert x.loc[2, ["exterior", "alero", "interior"]].sum() == 0
    assert np.isnan(x.loc[0, "edad"])                         


def test_grupo_puesto():
    assert grupo_puesto("Pívot") == "interior"
    assert grupo_puesto("Escolta") == "exterior"
    assert grupo_puesto("Alero") == "alero"
    assert grupo_puesto(None) is None
    for variante in ["A-Pívot", "Ala-Pïvot", "A_Pívot", "Pivot", "Ala pívor"]:
        assert grupo_puesto(variante) == "interior", variante
    for variante in ["Bas", "Bae", "Esco", "Es", "E"]:
        assert grupo_puesto(variante) == "exterior", variante


def test_separar_solo_entrena_con_objetivo_hasta_2022():
    etiquetadas, candidatas = separar(_tabla())
    assert etiquetadas["temporada"].tolist() == [2020, 2021]
    assert candidatas["temporada"].tolist() == [2024]


def test_captura_en_top_por_temporada():
    tabla = pd.DataFrame({"temporada": [2020] * 3 + [2021] * 3, "se_asienta": [1, 0, 0, 0, 1, 0]})
    resultado = captura_en_top(tabla, [0.9, 0.5, 0.1, 0.8, 0.2, 0.1], k=1)
    assert resultado["recall@1"] == 0.5        
    assert resultado["precision@1"] == 0.5


def test_puesto_normalizado():
    casos = {"Base": "Base", "Bas": "Base", "Bae": "Base", "Escolta": "Escolta", "Esco": "Escolta",
             "Es": "Escolta", "E": "Escolta", "Alero": "Alero", "A-Pívot": "Ala-Pívot",
             "Ala-Pïvot": "Ala-Pívot", "Ala.Pivot": "Ala-Pívot", "A_Pívot": "Ala-Pívot",
             "Ala pívor": "Ala-Pívot", "Pívot": "Pívot", "Pivot": "Pívot", "": None, None: None}
    for ficha, esperado in casos.items():
        assert puesto_normalizado(ficha) == esperado, ficha


def test_explicar_no_usa_variables_sin_dato():
    contribucion = pd.Series({"edad": 0.8, "tapones_favor_40": -0.9, "tl_falta": -0.5, "minutos_partido": -0.2})
    valores = pd.Series({"edad": 21.0, "tapones_favor_40": np.nan, "tl_falta": 0.0, "minutos_partido": 20.0})
    a_favor, en_contra = explicar(contribucion, valores)
    assert a_favor == ["edad (21)"]
    assert en_contra == ["minutos por partido (20.0)"]      