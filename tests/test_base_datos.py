
import pandas as pd
import pytest

from src import base_datos
from src.datos import cargar_datos, consultar


def _tablas():
    return {
        "jugadores_acb": pd.DataFrame({
            "id_acb": ["A1", "A2"], "slug": ["victor-arteaga", "john-smith"], "posicion": ["Pívot", "Base"],
            "altura_cm": [208.0, 190.0], "anio_nacimiento": [1992, 1990], "nacionalidad": ["España", "EE.UU."],
            "licencia": ["JFL", "EXT"], "es_espanol": [True, False], "es_jfl": [True, False],
        }),
        "jugadores_feb": pd.DataFrame({
            "id_feb": ["10"], "nombre": ["ARTEAGA GONZALEZ, VICTOR JESUS"], "anio_nacimiento": [1992],
            "altura_cm": [208.0], "puesto": ["Pívot"], "nacionalidad": ["ESPAÑA"],
        }),
        "emparejamiento": pd.DataFrame({"id_acb": ["A1"], "id_feb": ["10"], "metodo": ["completo"]}),
        "trayectorias_feb": pd.DataFrame({
            "id_feb": ["10"], "anio": [2011], "nivel": ["primera_feb"], "categoria": ["LEB ORO"], "club": ["X"],
        }),
    }


def _anchas():
    return {
        "temporadas_acb": pd.DataFrame({"id_acb": ["A1", "A1", "A2"], "anio": [2014, 2015, 2012],
                                        "partidos": [30, 32, 34]}),
        "temporadas_acb_club": pd.DataFrame({"id_acb": ["A1"], "temporada": ["14-15"], "club": ["X"],
                                             "partidos": [30]}),
        "temporadas_feb": pd.DataFrame({"id_feb": ["10"], "competicion": ["primera_feb"],
                                        "temporada": [2012], "puntos": [300]}),
        "dataset_modelo": pd.DataFrame({"id_feb": ["10"], "competicion": ["primera_feb"],
                                        "temporada": [2012], "se_asienta": [1]}),
    }


@pytest.fixture
def base(tmp_path):
    ruta = tmp_path / "prueba.db"
    problemas = base_datos.construir(ruta, _tablas(), _anchas())
    return ruta, problemas


def test_integridad_y_vistas(base):
    ruta, problemas = base
    assert all(cantidad == 0 for cantidad in problemas.values())
    cobertura = cargar_datos("v_cobertura_feb", ruta).set_index("id_acb")
    assert cobertura.loc["A1", "debut"] == 2014
    assert cobertura.loc["A1", "tiene_pareja_feb"] == 1
    assert cobertura.loc["A2", "tiene_pareja_feb"] == 0


def test_consulta_con_parametros(base):
    ruta, _ = base
    jfl = consultar("SELECT id_acb FROM jugadores_acb WHERE licencia = ?", ("JFL",), ruta)
    assert jfl["id_acb"].tolist() == ["A1"]


def test_clave_duplicada_falla(tmp_path):
    anchas = _anchas()
    anchas["temporadas_acb"] = pd.concat([anchas["temporadas_acb"]] * 2)
    with pytest.raises(Exception):
        base_datos.construir(tmp_path / "dup.db", _tablas(), anchas)


def test_errores_claros(base, tmp_path):
    ruta, _ = base
    with pytest.raises(ValueError, match="no existe"):
        cargar_datos("tabla_inventada", ruta)
    with pytest.raises(FileNotFoundError, match="python -m src.base_datos"):
        cargar_datos("jugadores_acb", tmp_path / "no_existe.db")


def test_la_base_es_de_solo_lectura(base):
    ruta, _ = base
    with pytest.raises(Exception):
        consultar("DELETE FROM jugadores_acb", ruta=ruta)