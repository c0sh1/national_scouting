
import pandas as pd

from src.dataset import anadir_evolucion, construir, definir_objetivo
from src.emparejar import candidatos, palabras, palabras_slug, preparar_feb, resolver


def test_palabras_quitan_tildes_y_particulas():
    assert palabras("ARTEAGA GONZÁLEZ, VÍCTOR JESÚS") == {"arteaga", "gonzalez", "victor", "jesus"}
    assert palabras("SMITH JR, PATRICK") == {"smith", "patrick"}
    assert palabras_slug("juan-de-la-fuente") == ["juan", "fuente"]


def _feb():
    fichas = pd.DataFrame({
        "id_feb": ["10", "11", "12", "13", "14"],
        "anio_nacimiento": [1992, 1992, 1990, 1995, 1995],
    })
    temporadas = pd.DataFrame({
        "id_feb": ["10", "11", "12", "13", "14"],
        "temporada": [2012] * 5,
        "jugador": ["ARTEAGA GONZALEZ, VICTOR JESUS",   # el bueno
                    "ARTEAGA LOPEZ, PEDRO",             # mismo apellido, otro nombre
                    "ARTEAGA GONZALEZ, VICTOR",         # mismo nombre, otro año
                    "GONZALEZ PEREZ, JOSE",             # homónimo 1
                    "GONZALEZ RUIZ, JOSE MARIA"],       # homónimo 2
    })
    return preparar_feb(fichas, temporadas)


def test_emparejamiento_por_nombre_y_anio():
    acb = pd.DataFrame({
        "id_acb": ["A1", "A2"],
        "slug": ["victor-arteaga", "jose-gonzalez"],
        "anio_nacimiento": [1992, 1995],
    })
    unicos, dudosos = resolver(candidatos(acb, _feb()))
    assert unicos[["id_acb", "id_feb", "metodo"]].values.tolist() == [["A1", "10", "completo"]]
    assert set(dudosos["id_feb"]) == {"13", "14"}      # dos José González de 1995: no se decide


def test_segundo_nombre_que_la_feb_no_tiene():
    acb = pd.DataFrame({"id_acb": ["A3"], "slug": ["pedro-luis-arteaga"], "anio_nacimiento": [1992]})
    unicos, _ = resolver(candidatos(acb, _feb()))
    assert unicos[["id_feb", "metodo"]].values.tolist() == [["11", "nombre_y_apellido"]]


def test_nombre_de_pila_escrito_distinto():
    fichas = pd.DataFrame({"id_feb": ["20", "21", "22"], "anio_nacimiento": [1987, 1997, 1997]})
    temporadas = pd.DataFrame({
        "id_feb": ["20", "21", "22"],
        "temporada": [2012] * 3,
        "jugador": ["PINO CAPDEVILA, SERGIO",       # Sergi en la ACB
                    "GALARZA PEDROSO, JON",         # Ion en la ACB
                    "GALARZA LOPEZ, MARKEL"],       # mismo apellido y año, otro nombre
    })
    acb = pd.DataFrame({"id_acb": ["A5", "A6"], "slug": ["sergi-pino", "ion-galarza"],
                        "anio_nacimiento": [1987, 1997]})
    unicos, dudosos = resolver(candidatos(acb, preparar_feb(fichas, temporadas)))
    assert sorted(unicos[["id_acb", "id_feb", "metodo"]].values.tolist()) == [
        ["A5", "20", "nombre_parecido"], ["A6", "21", "nombre_parecido"]]
    assert dudosos.empty


def test_nombre_parecido_no_anula_un_emparejamiento_completo():
    # Jon Galarza empareja por nombre completo; Ion Galarza (otro jugador ACB
    # del mismo año) solo por nombre parecido. Gana el completo, sin dudosos.
    fichas = pd.DataFrame({"id_feb": ["21"], "anio_nacimiento": [1997]})
    temporadas = pd.DataFrame({"id_feb": ["21"], "temporada": [2012],
                               "jugador": ["GALARZA PEDROSO, JON"]})
    acb = pd.DataFrame({"id_acb": ["A7", "A8"], "slug": ["jon-galarza", "ion-galarza"],
                        "anio_nacimiento": [1997, 1997]})
    unicos, dudosos = resolver(candidatos(acb, preparar_feb(fichas, temporadas)))
    assert unicos[["id_acb", "id_feb", "metodo"]].values.tolist() == [["A7", "21", "completo"]]
    assert dudosos.empty


def test_nombre_parecido_no_sustituye_a_metodos_mejores():
    # Pedro Luis Arteaga ya empareja por nombre y apellido: no se buscan parecidos.
    acb = pd.DataFrame({"id_acb": ["A3"], "slug": ["pedro-luis-arteaga"], "anio_nacimiento": [1992]})
    assert set(candidatos(acb, _feb())["metodo"]) == {"nombre_y_apellido"}


def _temporadas_acb():
    return pd.DataFrame({
        "id_acb": ["A1", "A1", "A2"],
        "anio": [2014, 2015, 2010],
        "partidos": [30, 5, 30],
        "minutos": [20.0, 25.0, 22.0],
    })


def test_objetivo_horizonte_y_umbrales():
    filas = pd.DataFrame({
        "id_acb": ["A1", "A1", "A1", None, "A2"],
        "temporada": [2012, 2010, 2020, 2012, 2012],
    })
    resultado = definir_objetivo(filas, _temporadas_acb(), ultima_temporada_acb=2021)
    # 2012: se asienta en 2014 (dentro de 3 temporadas). 2010: 2014 queda fuera.
    assert resultado["se_asienta"].tolist()[:2] == [1, 0]
    # 2020: el horizonte acaba en 2023 y solo hay datos hasta 2021: sin objetivo.
    assert pd.isna(resultado.loc[2, "se_asienta"])
    assert resultado.loc[3, "se_asienta"] == 0            # nunca llegó a la ACB
    assert bool(resultado.loc[4, "ya_asentado_antes"])    # asentado en 2010, vuelve a la FEB


def test_sin_horizonte_completo_no_hay_objetivo_aunque_ya_se_asentara():
    # Fila de 2013, datos ACB hasta 2014: se asentó en 2014, pero el horizonte
    # (hasta 2016) no ha terminado. Si se marcara 1, en las temporadas
    # recientes solo habría positivos.
    filas = pd.DataFrame({"id_acb": ["A1"], "temporada": [2013]})
    resultado = definir_objetivo(filas, _temporadas_acb(), ultima_temporada_acb=2014)
    assert pd.isna(resultado.loc[0, "se_asienta"])


def test_evolucion_usa_la_fila_con_mas_minutos():
    tabla = pd.DataFrame({
        "id_feb": ["1", "1", "1"],
        "competicion": ["segunda_feb", "liga_u", "primera_feb"],
        "temporada": [2020, 2021, 2021],
        "minutos": [300, 100, 500],
        "minutos_partido": [10.0, 5.0, 20.0],
        "puntos_40": [10.0, 30.0, 14.0],
        "rebotes_40": [5.0, 5.0, 5.0],
        "asistencias_40": [2.0, 2.0, 2.0],
        "valoracion_40": [8.0, 8.0, 9.0],
    })
    resultado = anadir_evolucion(tabla).set_index("competicion")
    assert resultado.loc["primera_feb", "puntos_40_cambio"] == 4.0
    assert resultado.loc["primera_feb", "temporadas_previas_feb"] == 1
    assert pd.isna(resultado.loc["segunda_feb", "puntos_40_cambio"])


def test_construir_no_deja_columnas_de_la_acb():
    feb = pd.DataFrame({
        "id_feb": ["10"], "competicion": ["primera_feb"], "temporada": [2012],
        "jugador": ["X"], "minutos": [500.0], "minutos_partido": [20.0], "puntos_40": [15.0],
        "rebotes_40": [6.0], "asistencias_40": [2.0], "valoracion_40": [12.0],
    })
    fichas = pd.DataFrame({"id_feb": ["10"], "anio_nacimiento": [1992]})
    emparejamiento = pd.DataFrame({"id_acb": ["A1"], "id_feb": ["10"], "metodo": ["completo"]})
    tabla = construir(feb, fichas, _temporadas_acb(), emparejamiento, ultima_temporada_acb=2021)
    assert "id_acb" not in tabla.columns
    assert tabla.loc[0, "edad"] == 20
    assert tabla.loc[0, "se_asienta"] == 1