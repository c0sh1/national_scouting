
import unicodedata
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

RAIZ = Path(__file__).resolve().parent.parent
RUTA_MODELO = RAIZ / "models" / "modelo.joblib"
RUTA_PREDICCIONES = RAIZ / "data" / "processed" / "predicciones.csv"

ULTIMA_TEMPORADA_ENTRENAMIENTO = 2022   

VARIABLES_NUMERICAS = [
    "edad", "altura_cm", "partidos", "minutos", "minutos_partido",
    "puntos_40", "rebotes_40", "reb_of_40", "reb_def_40", "asistencias_40",
    "recuperaciones_40", "perdidas_40", "tapones_favor_40", "tapones_contra_40",
    "faltas_cometidas_40", "faltas_recibidas_40", "valoracion_40",
    "t2_pct", "t3_pct", "tl_pct", "triples_intentados_40",
    "minutos_partido_cambio", "puntos_40_cambio", "rebotes_40_cambio",
    "asistencias_40_cambio", "valoracion_40_cambio", "temporadas_previas_feb",
]
VARIABLES_BINARIAS = [
    "primera_feb", "es_nacional_feb", "t2_falta", "t3_falta", "tl_falta",
    "exterior", "alero", "interior",
]
VARIABLES = VARIABLES_NUMERICAS + VARIABLES_BINARIAS

# Nombres legibles para la aplicación y las explicaciones.
NOMBRES = {
    "edad": "edad", "altura_cm": "altura", "partidos": "partidos jugados",
    "minutos": "minutos en la temporada", "minutos_partido": "minutos por partido",
    "puntos_40": "puntos por 40 min", "rebotes_40": "rebotes por 40 min",
    "reb_of_40": "rebotes ofensivos por 40 min", "reb_def_40": "rebotes defensivos por 40 min",
    "asistencias_40": "asistencias por 40 min", "recuperaciones_40": "recuperaciones por 40 min",
    "perdidas_40": "pérdidas por 40 min", "tapones_favor_40": "tapones por 40 min",
    "tapones_contra_40": "tapones recibidos por 40 min",
    "faltas_cometidas_40": "faltas cometidas por 40 min",
    "faltas_recibidas_40": "faltas recibidas por 40 min", "valoracion_40": "valoración por 40 min",
    "t2_pct": "% tiros de 2", "t3_pct": "% triples", "tl_pct": "% tiros libres",
    "triples_intentados_40": "triples intentados por 40 min",
    "minutos_partido_cambio": "cambio de minutos por partido",
    "puntos_40_cambio": "cambio de puntos por 40", "rebotes_40_cambio": "cambio de rebotes por 40",
    "asistencias_40_cambio": "cambio de asistencias por 40",
    "valoracion_40_cambio": "cambio de valoración por 40",
    "temporadas_previas_feb": "temporadas previas en la FEB", "primera_feb": "juega en Primera FEB",
    "es_nacional_feb": "pasaporte español (FEB)", "t2_falta": "sin dato de tiros de 2",
    "t3_falta": "sin dato de triples", "tl_falta": "sin dato de tiros libres",
    "exterior": "exterior (base o escolta)", "alero": "alero", "interior": "interior",
}


PUESTOS = ["Base", "Escolta", "Alero", "Ala-Pívot", "Pívot"]
GRUPO_DE_PUESTO = {"Base": "exterior", "Escolta": "exterior", "Alero": "alero",
                   "Ala-Pívot": "interior", "Pívot": "interior"}


def puesto_normalizado(puesto):
    if not isinstance(puesto, str) or not puesto.strip():
        return None
    texto = unicodedata.normalize("NFKD", puesto.strip().lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    if texto.startswith(("ala", "a-", "a_", "a.")):
        return "Ala-Pívot"
    if "piv" in texto:
        return "Pívot"
    if texto.startswith("ale"):
        return "Alero"
    if texto.startswith("ba"):
        return "Base"
    if texto.startswith("e"):
        return "Escolta"
    return None


def grupo_puesto(puesto):
    return GRUPO_DE_PUESTO.get(puesto_normalizado(puesto))


def preparar_variables(tabla):
    x = pd.DataFrame(index=tabla.index)
    for columna in VARIABLES_NUMERICAS:
        if columna == "triples_intentados_40":
            continue
        x[columna] = pd.to_numeric(tabla.get(columna), errors="coerce")
    minutos = x["minutos"].where(x["minutos"] > 0)
    x["triples_intentados_40"] = pd.to_numeric(tabla.get("t3_intentados"), errors="coerce") * 40 / minutos
    x["primera_feb"] = (tabla["competicion"] == "primera_feb").astype(int)
    for columna in ["es_nacional_feb", "t2_falta", "t3_falta", "tl_falta"]:
        x[columna] = tabla.get(columna, pd.Series(0, index=tabla.index)).fillna(0).astype(int)
    grupo = tabla.get("puesto", pd.Series(index=tabla.index, dtype=object)).map(grupo_puesto)
    for nombre in ["exterior", "alero", "interior"]:
        x[nombre] = (grupo == nombre).astype(int)
    return x[VARIABLES].astype(float)


def separar(tabla):
    etiquetadas = tabla[tabla["se_asienta"].notna()
                        & (tabla["temporada"] <= ULTIMA_TEMPORADA_ENTRENAMIENTO)].copy()
    etiquetadas["se_asienta"] = etiquetadas["se_asienta"].astype(int)
    candidatas = tabla[tabla["se_asienta"].isna()].copy()
    return etiquetadas, candidatas


def captura_en_top(tabla, puntuacion, k=20):
    datos = tabla[["temporada", "se_asienta"]].assign(p=np.asarray(puntuacion))
    datos["puesto"] = datos.groupby("temporada")["p"].rank(ascending=False, method="first")
    lista = datos[datos["puesto"] <= k]
    return {
        f"recall@{k}": lista["se_asienta"].sum() / max(datos["se_asienta"].sum(), 1),
        f"precision@{k}": lista["se_asienta"].mean(),
    }


def evaluar(tabla, puntuacion, k=20):
    y = tabla["se_asienta"]
    return {
        "PR-AUC": average_precision_score(y, puntuacion),
        "ROC-AUC": roc_auc_score(y, puntuacion),
        **captura_en_top(tabla, puntuacion, k),
    }


def guardar_modelo(modelo, nombre, metricas, ruta=RUTA_MODELO):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"modelo": modelo, "nombre": nombre, "variables": VARIABLES,
                 "metricas": metricas}, ruta)


def cargar_modelo(ruta=RUTA_MODELO):
    return joblib.load(ruta)


def _estimador_final(modelo):
    return modelo.steps[-1][1] if hasattr(modelo, "steps") else modelo


def contribuciones(modelo, x):
    final = _estimador_final(modelo)
    if hasattr(final, "coef_"):
        transformado = modelo[:-1].transform(x) if hasattr(modelo, "steps") else x.values
        valores = transformado * final.coef_[0]
    else:
        import warnings

        import shap
        datos = modelo[:-1].transform(x) if hasattr(modelo, "steps") else x
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            valores = shap.TreeExplainer(final).shap_values(datos)
        if isinstance(valores, list):         
            valores = valores[1]
        valores = np.asarray(valores)
        if valores.ndim == 3:
            valores = valores[:, :, 1]
    return pd.DataFrame(valores, index=x.index, columns=x.columns)


def describir(variable, valor):
    nombre = NOMBRES.get(variable, variable)
    if variable in VARIABLES_BINARIAS:
        return nombre if valor == 1 else f"no: {nombre}"
    if valor is None or pd.isna(valor):
        return f"{nombre} (sin dato)"
    return f"{nombre} ({valor:.0f})" if variable in ("edad", "altura_cm", "partidos",
                                                      "temporadas_previas_feb") else f"{nombre} ({valor:.1f})"


def explicar(contribucion, valores=None, n=3):
    orden = contribucion.sort_values()
    texto = (lambda v: describir(v, valores[v])) if valores is not None else (lambda v: NOMBRES.get(v, v))
    a_favor = [texto(v) for v, c in orden[::-1].items() if c > 0][:n]
    en_contra = [texto(v) for v, c in orden.items() if c < 0][:n]
    return a_favor, en_contra