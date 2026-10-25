"""Aplicación de ojeo: jóvenes de la FEB con más probabilidad de asentarse en la ACB."""

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from src.datos import RUTA_DB, cargar_datos
from src.modelo import (NOMBRES, RUTA_MODELO, RUTA_PREDICCIONES, cargar_modelo, contribuciones,
                        explicar, grupo_puesto, preparar_variables, puesto_normalizado, separar)

st.set_page_config(page_title="Scouting FEB → ACB", page_icon="🏀", layout="wide")

st.markdown("""
<style>
@import url("https://fonts.googleapis.com/css2?family=Oswald:wght@500;700&display=swap");
h1, h2, h3, [data-testid="stMetricLabel"] p {
    font-family: "Oswald", sans-serif !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
h1 { color: #F26B1D !important; border-bottom: 3px solid #F26B1D; padding-bottom: 0.3rem; }
[data-testid="stMetricValue"] { color: #F26B1D; font-family: "Oswald", sans-serif; }
[data-testid="stMetric"] {
    background: #1D232B; border-left: 4px solid #F26B1D; border-radius: 6px; padding: 0.6rem 0.9rem;
}
.stTabs [data-baseweb="tab"] p { font-family: "Oswald", sans-serif; text-transform: uppercase; font-size: 1rem; }
</style>
""", unsafe_allow_html=True)

ANIO_NACIMIENTO_MAXIMO = date.today().year - 19

COMPETICIONES = {"primera_feb": "Primera FEB", "segunda_feb": "Segunda FEB", "liga_u": "Liga U"}


@st.cache_resource
def modelo():
    return cargar_modelo()


@st.cache_data
def predicciones():
    tabla = pd.read_csv(RUTA_PREDICCIONES, dtype={"id_feb": str})
    tabla["anio_nacimiento"] = tabla["temporada"] - tabla["edad"]
    tabla["puesto"] = tabla["puesto"].map(puesto_normalizado).fillna("")
    return tabla[tabla["anio_nacimiento"] <= ANIO_NACIMIENTO_MAXIMO]


@st.cache_data
def historico():
    """Filas con desenlace conocido (2005-2022): base de los comparables."""
    etiquetadas, _ = separar(cargar_datos("dataset_modelo"))
    return etiquetadas


@st.cache_data
def temporadas_feb():
    tabla = cargar_datos("temporadas_feb")
    fichas = cargar_datos("jugadores_feb")[["id_feb", "anio_nacimiento", "altura_cm", "puesto"]]
    tabla = tabla.merge(fichas, on="id_feb", how="left")
    tabla["edad"] = tabla["temporada"] - tabla["anio_nacimiento"]
    tabla["puesto"] = tabla["puesto"].map(puesto_normalizado).fillna("")
    return tabla[tabla["anio_nacimiento"] <= ANIO_NACIMIENTO_MAXIMO]


RASGOS_COMPARABLES = ["edad", "minutos_partido", "puntos_40", "rebotes_40", "asistencias_40",
                      "valoracion_40"]


def comparables(jugador, n=10):
    """Las n temporadas FEB de 2005-2022 con el perfil más parecido al del jugador
    (edad, minutos y producción por 40, estandarizados), con su desenlace en la ACB.
    Los rasgos que el jugador no tenga no cuentan en la distancia."""
    base = historico()
    matriz = base[RASGOS_COMPARABLES].astype(float)
    media, desviacion = matriz.mean(), matriz.std().replace(0, 1)
    perfil = pd.to_numeric(pd.Series(jugador).reindex(RASGOS_COMPARABLES), errors="coerce")
    usados = perfil.dropna().index
    distancia = ((((matriz[usados] - media[usados]) / desviacion[usados])
                  - ((perfil[usados] - media[usados]) / desviacion[usados])) ** 2).sum(axis=1)
    return base.assign(distancia=distancia).nsmallest(n, "distancia")


def mostrar_comparables(jugador):
    cercanos = comparables(jugador)
    st.dataframe(cercanos.assign(competicion=cercanos["competicion"].map(COMPETICIONES),
                                 se_asento=cercanos["se_asienta"].map({1: "Sí", 0: "No"}))[
        ["jugador", "temporada", "competicion"] + RASGOS_COMPARABLES + ["se_asento"]].round(1).pipe(legible),
        hide_index=True, width="stretch")
    st.write(f"De estos {len(cercanos)} comparables, **{int(cercanos['se_asienta'].sum())}** "
             "se asentaron en la ACB.")
    return cercanos


EJES_RADAR = {"puntos_40": "Puntos/40", "rebotes_40": "Rebotes/40", "asistencias_40": "Asistencias/40",
              "recuperaciones_40": "Robos/40", "tapones_favor_40": "Tapones/40", "t2_pct": "% tiros de 2",
              "t3_pct": "% triples", "minutos_partido": "Min/partido"}
AZUL, NARANJA = "#2a78d6", "#eb6834"


@st.cache_data
def referencia_radar():
    """Temporadas FEB con al menos 100 minutos: la base de los percentiles."""
    tabla = cargar_datos("temporadas_feb").merge(
        cargar_datos("jugadores_feb")[["id_feb", "puesto"]], on="id_feb", how="left")
    tabla["posicion"] = tabla["puesto"].map(grupo_puesto)
    return tabla[tabla["minutos"] >= 100]


def grupo_de_comparacion(fila):
    """Con quién se compara al jugador: su posición y su liga, o toda la liga si
    la ficha no tiene posición."""
    posicion = grupo_puesto(fila.get("puesto"))
    liga = COMPETICIONES[fila["competicion"]]
    plural = {"exterior": "exteriores", "alero": "aleros", "interior": "interiores"}
    return posicion, (f"{plural[posicion]} de {liga}" if posicion
                      else f"todos los jugadores de {liga} (sin posición en la ficha)")


def percentiles(fila):
    """Percentil (0-100) de cada eje frente a los jugadores de su posición y liga."""
    base = referencia_radar()
    base = base[base["competicion"] == fila["competicion"]]
    posicion, _ = grupo_de_comparacion(fila)
    if posicion:
        base = base[base["posicion"] == posicion]
    resultado = {}
    for columna in EJES_RADAR:
        valores, valor = base[columna].dropna(), fila.get(columna)
        resultado[columna] = (100 * ((valores < valor).mean() + 0.5 * (valores == valor).mean())
                              if pd.notna(valor) else np.nan)
    return pd.Series(resultado)


def grafico_radar(perfiles):
    """perfiles: lista de (etiqueta, percentiles, color). Un eje sin dato se dibuja en 0."""
    angulos = np.linspace(0, 2 * np.pi, len(EJES_RADAR), endpoint=False).tolist()
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw={"polar": True})
    for etiqueta, valores, color in perfiles:
        puntos = valores.fillna(0).tolist()
        ax.plot(angulos + angulos[:1], puntos + puntos[:1], color=color, linewidth=2, label=etiqueta)
        ax.fill(angulos + angulos[:1], puntos + puntos[:1], color=color, alpha=0.15)
    ax.set_xticks(angulos, list(EJES_RADAR.values()), fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75], ["25", "50", "75"], fontsize=7, color="#8a8a86")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), frameon=False, fontsize=9)
    ax.set_title("Percentil frente a su posición y su liga (100 = el mejor)", fontsize=10, pad=18)
    return fig


POSICIONES = {"exterior": "Exterior (base / escolta)", "alero": "Alero", "interior": "Interior (ala-pívot / pívot)",
              "sin dato": "Sin posición en la ficha"}


def filtro_posicion(columna, clave):
    """Selector de posición. La ficha FEB escribe el puesto de muchas formas
    ("Ala-Pívot", "A-Pívot", "Pivot"...) y falta en muchos jugadores, así que
    se agrupa en exterior / alero / interior / sin dato."""
    return columna.multiselect("Posición", list(POSICIONES), default=list(POSICIONES),
                               format_func=POSICIONES.get, key=clave)


def grupo(serie):
    return serie.map(grupo_puesto).fillna("sin dato")


ETIQUETAS = {
    "jugador": "Jugador", "equipo": "Equipo", "competicion": "Competición", "temporada": "Temporada",
    "edad": "Edad", "puesto": "Puesto", "partidos": "Partidos", "minutos_partido": "Min/partido",
    "puntos_40": "Puntos/40", "rebotes_40": "Rebotes/40", "asistencias_40": "Asistencias/40",
    "valoracion_40": "Valoración/40", "se_asento": "¿Se asentó en la ACB?",
}


def legible(tabla):
    """Columnas con nombres para el usuario, no los internos."""
    return tabla.rename(columns=ETIQUETAS)


def porcentaje(serie):
    return (100 * serie).round(1)


def mostrar_explicacion(a_favor, en_contra):
    col1, col2 = st.columns(2)
    col1.markdown("**Lo que más suma**\n" + "".join(f"\n- {m}" for m in a_favor) if a_favor
                  else "**Lo que más suma**\n\n- nada destacable")
    col2.markdown("**Lo que más resta**\n" + "".join(f"\n- {m}" for m in en_contra) if en_contra
                  else "**Lo que más resta**\n\n- nada destacable")


# ---------------------------------------------------------------------------
st.title("🏀 Scouting FEB → ACB")
st.caption("Jugadores de Primera y Segunda FEB con más probabilidad de asentarse en la ACB "
           "(15 partidos con 15 minutos por partido en alguna de las 3 temporadas siguientes).")

faltan = [(ruta, como) for ruta, como in [
    (RUTA_DB, "python -m src.base_datos"),
    (RUTA_MODELO, "ejecutar notebooks/03_modelo.ipynb de arriba abajo"),
    (RUTA_PREDICCIONES, "ejecutar notebooks/03_modelo.ipynb de arriba abajo"),
] if not ruta.exists()]
if faltan:
    st.error("Faltan archivos que la aplicación necesita:\n\n"
             + "\n".join(f"- `{ruta.relative_to(RAIZ)}` → {como}" for ruta, como in faltan))
    st.stop()

datos_modelo = modelo()
pestanas = st.tabs(["Candidatos", "Ficha y comparables", "Evaluar un jugador", "Liga U", "Sobre el modelo"])

# --- Candidatos -------------------------------------------------------------
with pestanas[0]:
    tabla = predicciones()
    c1, c2, c3, c4, c5 = st.columns(5)
    temporada = c1.selectbox("Temporada FEB", sorted(tabla["temporada"].unique(), reverse=True))
    competicion = c2.multiselect("Competición", ["primera_feb", "segunda_feb"],
                                 default=["primera_feb", "segunda_feb"], format_func=COMPETICIONES.get)
    edad_maxima = c3.slider("Edad máxima", 18, 35, 24)
    posiciones = filtro_posicion(c4, "posicion_candidatos")
    solo_espanoles = c5.checkbox("Solo pasaporte español", value=False,
                                 help="Filtro de la FEB por pasaporte. No equivale a jugador de formación "
                                      "local (JFL): deja fuera a canteranos extranjeros.")
    vista = tabla[(tabla["temporada"] == temporada) & tabla["competicion"].isin(competicion)
                  & (tabla["edad"] <= edad_maxima) & grupo(tabla["puesto"]).isin(posiciones)]
    if solo_espanoles:
        vista = vista[vista["es_nacional_feb"] == 1]
    vista = vista.sort_values("probabilidad", ascending=False)
    st.write(f"{len(vista)} jugadores")
    st.dataframe(
        vista.assign(competicion=vista["competicion"].map(COMPETICIONES),
                     probabilidad=porcentaje(vista["probabilidad"]))[
            ["jugador", "equipo", "competicion", "edad", "puesto", "minutos_partido", "puntos_40",
             "valoracion_40", "probabilidad", "a_favor"]],
        hide_index=True, width="stretch",
        column_config={"probabilidad": st.column_config.ProgressColumn("Probabilidad (%)", min_value=0,
                                                                        max_value=100, format="%.1f"),
                       "minutos_partido": st.column_config.NumberColumn("Min/partido", format="%.1f"),
                       "puntos_40": st.column_config.NumberColumn("Puntos/40", format="%.1f"),
                       "valoracion_40": st.column_config.NumberColumn("Valoración/40", format="%.1f"),
                       "a_favor": "Lo que más suma", "jugador": "Jugador", "equipo": "Equipo",
                       "competicion": "Competición", "edad": "Edad", "puesto": "Puesto"})
    st.caption("La probabilidad ordena a los jugadores; no es una garantía. El modelo solo ve "
               "estadísticas de la FEB, no lesiones, contratos ni necesidades del club.")

# --- Ficha y comparables ----------------------------------------------------
with pestanas[1]:
    tabla = predicciones()
    c1, c2 = st.columns(2)
    temporada_ficha = c1.selectbox("Temporada FEB", sorted(tabla["temporada"].unique(), reverse=True),
                                   key="temporada_ficha")
    posicion_ficha = c2.selectbox("Posición", ["todas"] + list(POSICIONES),
                                  format_func=lambda v: "Todas" if v == "todas" else POSICIONES[v])
    ultima = tabla[(tabla["temporada"] == temporada_ficha) & (tabla["edad"] <= 25)]
    ultima = ultima.sort_values("probabilidad", ascending=False)
    if posicion_ficha != "todas":
        ultima = ultima[grupo(ultima["puesto"]) == posicion_ficha]
    if ultima.empty:
        st.warning("Ningún jugador de 25 años o menos con esa posición en esta temporada; se muestran todos.")
        ultima = tabla[(tabla["temporada"] == temporada_ficha) & (tabla["edad"] <= 25)]
    opciones = ultima["id_feb"] + "|" + ultima["competicion"]
    elegido = st.selectbox("Jugador (25 años o menos)", opciones,
                           format_func=lambda o: ultima.loc[opciones == o, "jugador"].iloc[0]
                           + f" · {COMPETICIONES[o.split('|')[1]]}")
    fila = ultima[opciones == elegido].iloc[0]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Probabilidad", f"{fila['probabilidad']:.0%}")
    c2.metric("Puesto", fila["puesto"] or "sin dato")
    c3.metric("Edad", int(fila["edad"]))
    c4.metric("Minutos por partido", f"{fila['minutos_partido']:.1f}")
    c5.metric("Valoración por 40", f"{fila['valoracion_40']:.1f}")
    mostrar_explicacion(str(fila["a_favor"]).split(", ") if isinstance(fila["a_favor"], str) else [],
                        str(fila["en_contra"]).split(", ") if isinstance(fila["en_contra"], str) else [])

    st.subheader("Evolución en la FEB")
    trayectoria = temporadas_feb()
    trayectoria = trayectoria[trayectoria["id_feb"] == fila["id_feb"]].sort_values("temporada")
    st.dataframe(trayectoria.assign(competicion=trayectoria["competicion"].map(COMPETICIONES))[
        ["temporada", "competicion", "equipo", "edad", "partidos", "minutos_partido", "puntos_40",
         "rebotes_40", "asistencias_40", "valoracion_40"]].round(1).pipe(legible), hide_index=True,
        width="stretch")

    st.subheader("Comparables: jugadores parecidos a su edad y qué fue de ellos")
    st.caption("Temporadas FEB de 2005-2022 con el perfil más parecido (edad, minutos y producción "
               "por 40 minutos). Incluye a los que llegaron a asentarse en la ACB y a los que no.")
    cercanos = mostrar_comparables(fila)

    st.subheader("Gráfico")
    st.caption("Comparación de los percentiles del jugador con los de otros jugadores similares.")
    base = referencia_radar()
    propia = base[(base["id_feb"] == fila["id_feb"]) & (base["competicion"] == fila["competicion"])
                  & (base["temporada"] == fila["temporada"])].iloc[0]
    contra = st.selectbox("Comparar con", [None] + list(cercanos.index),
                          format_func=lambda i: "Nadie" if i is None else
                          f"{cercanos.loc[i, 'jugador']} ({cercanos.loc[i, 'temporada']}, "
                          f"{COMPETICIONES[cercanos.loc[i, 'competicion']]})")
    perfiles = [(f"{fila['jugador']} ({fila['temporada']})", percentiles(propia), AZUL)]
    if contra is not None:
        otro = cercanos.loc[contra]
        perfiles.append((f"{otro['jugador']} ({otro['temporada']}) · se asentó: "
                         f"{'sí' if otro['se_asienta'] == 1 else 'no'}", percentiles(otro), NARANJA))
    st.write(" · ".join(f"**{etiqueta.split(' (')[0]}** se compara con {grupo_de_comparacion(f)[1]}"
                        for (etiqueta, _, _), f in zip(perfiles, [propia] + ([otro] if contra is not None else []))))
    izquierda, derecha = st.columns([3, 2])
    izquierda.pyplot(grafico_radar(perfiles), width="stretch")
    detalle = pd.DataFrame({etiqueta.split(" (")[0]: valores.round(0) for etiqueta, valores, _ in perfiles})
    detalle.index = list(EJES_RADAR.values())
    derecha.write("**Percentiles**")
    derecha.dataframe(detalle, width="stretch")

# --- Evaluar un jugador -----------------------------------------------------
with pestanas[2]:
    st.write("Introduce las estadísticas de una temporada en la FEB, o sube un CSV con varios jugadores.")
    with st.form("formulario"):
        c1, c2, c3, c4 = st.columns(4)
        competicion = c1.selectbox("Competición", ["primera_feb", "segunda_feb"], format_func=COMPETICIONES.get)
        edad = c2.number_input("Edad", 16, 40, 21)
        altura = c3.number_input("Altura (cm)", 160, 230, 198)
        puesto = c4.selectbox("Puesto", ["Base", "Escolta", "Alero", "Ala-Pívot", "Pívot"])
        c1, c2, c3, c4 = st.columns(4)
        partidos = c1.number_input("Partidos", 1, 50, 28)
        minutos_partido = c2.number_input("Minutos por partido", 1.0, 40.0, 20.0)
        puntos_40 = c3.number_input("Puntos por 40", 0.0, 50.0, 15.0)
        valoracion_40 = c4.number_input("Valoración por 40", -10.0, 60.0, 14.0)
        c1, c2, c3, c4 = st.columns(4)
        rebotes_40 = c1.number_input("Rebotes por 40", 0.0, 30.0, 7.0)
        asistencias_40 = c2.number_input("Asistencias por 40", 0.0, 20.0, 3.0)
        t3_pct = c3.number_input("% triples", 0.0, 100.0, 33.0)
        es_nacional = c4.checkbox("Pasaporte español", value=True)
        enviado = st.form_submit_button("Calcular")

    if enviado:
        jugador = pd.DataFrame([{
            "competicion": competicion, "edad": edad, "altura_cm": altura, "puesto": puesto,
            "partidos": partidos, "minutos_partido": minutos_partido, "minutos": partidos * minutos_partido,
            "puntos_40": puntos_40, "rebotes_40": rebotes_40, "asistencias_40": asistencias_40,
            "valoracion_40": valoracion_40, "t3_pct": t3_pct, "es_nacional_feb": int(es_nacional),
        }])
        if jugador["minutos"].iloc[0] < 100:
            st.warning("Con menos de 100 minutos en la temporada las estadísticas no son fiables "
                       "y el modelo no se entrenó con esos casos.")
        x = preparar_variables(jugador)
        p = datos_modelo["modelo"].predict_proba(x)[0, 1]
        st.metric("Probabilidad de asentarse en la ACB", f"{p:.0%}")
        a_favor, en_contra = explicar(contribuciones(datos_modelo["modelo"], x).iloc[0], x.iloc[0])
        mostrar_explicacion(a_favor, en_contra)
        st.caption("Las variables que no se introducen (evolución respecto al año anterior, "
                   "tapones, faltas…) quedan como desconocidas.")
        st.subheader("Comparables históricos")
        mostrar_comparables(jugador.iloc[0])

    st.divider()
    st.write("**Varios jugadores a la vez (CSV)**. Columnas: `jugador`, `competicion` "
             "(primera_feb o segunda_feb), `edad`, `altura_cm`, `puesto`, `partidos`, `minutos_partido`, "
             "`puntos_40`, `rebotes_40`, `asistencias_40`, `valoracion_40`, `t3_pct`, `es_nacional_feb` (0/1). "
             "Las que falten se tratan como desconocidas.")
    plantilla = pd.DataFrame([{"jugador": "Ejemplo", "competicion": "primera_feb", "edad": 21, "altura_cm": 198,
                               "puesto": "Alero", "partidos": 28, "minutos_partido": 20.0, "puntos_40": 15.0,
                               "rebotes_40": 7.0, "asistencias_40": 3.0, "valoracion_40": 14.0,
                               "t3_pct": 33.0, "es_nacional_feb": 1}])
    st.download_button("Descargar plantilla CSV", plantilla.to_csv(index=False), "plantilla_jugadores.csv",
                       "text/csv")
    archivo = st.file_uploader("Subir CSV", type="csv")
    if archivo is not None:
        subidos = pd.read_csv(archivo)
        if "competicion" not in subidos:
            st.error("Falta la columna `competicion`.")
        else:
            if "minutos" not in subidos and {"partidos", "minutos_partido"} <= set(subidos.columns):
                subidos["minutos"] = subidos["partidos"] * subidos["minutos_partido"]
            x = preparar_variables(subidos)
            subidos["probabilidad"] = porcentaje(pd.Series(datos_modelo["modelo"].predict_proba(x)[:, 1],
                                                           index=subidos.index))
            contrib = contribuciones(datos_modelo["modelo"], x)
            subidos["lo_que_mas_suma"] = [", ".join(explicar(contrib.loc[i], x.loc[i])[0]) for i in subidos.index]
            st.dataframe(subidos.sort_values("probabilidad", ascending=False), hide_index=True,
                         width="stretch")

            st.subheader("Comparar un jugador del CSV")
            nombres = subidos["jugador"].astype(str) if "jugador" in subidos else subidos.index.astype(str)
            elegido = st.selectbox("Jugador", subidos.index, format_func=lambda i: nombres[i])
            fila_subida = subidos.loc[elegido]
            perfil = pd.DataFrame({
                "Jugador subido": pd.to_numeric(fila_subida.reindex(RASGOS_COMPARABLES), errors="coerce"),
                "Media de los que se asentaron": historico().loc[historico()["se_asienta"] == 1,
                                                                 RASGOS_COMPARABLES].mean(),
                "Media de los que no": historico().loc[historico()["se_asienta"] == 0,
                                                       RASGOS_COMPARABLES].mean(),
            }).rename(index=NOMBRES).round(1)
            st.dataframe(perfil, width="stretch")
            mostrar_comparables(fila_subida)

# --- Liga U -----------------------------------------------------------------
with pestanas[3]:
    st.write("La Liga U solo tiene una temporada descargada: no se sabe todavía qué jugadores llegarán "
             "a la ACB, así que el modelo no se entrenó con ella. Se muestra un ranking descriptivo.")
    liga_u = temporadas_feb()
    liga_u = liga_u[(liga_u["competicion"] == "liga_u") & (liga_u["minutos"] >= 100)]
    c1, c2 = st.columns(2)
    posiciones_u = filtro_posicion(c2, "posicion_liga_u")
    liga_u = liga_u[grupo(liga_u["puesto"]).isin(posiciones_u)]
    orden = c1.selectbox("Ordenar por", ["valoracion_40", "puntos_40", "rebotes_40", "asistencias_40",
                                         "minutos_partido"], format_func=lambda v: NOMBRES.get(v, v))
    st.dataframe(liga_u.sort_values(orden, ascending=False)[
        ["jugador", "equipo", "edad", "puesto", "partidos", "minutos_partido", "puntos_40", "rebotes_40",
         "asistencias_40", "valoracion_40"]].round(1).pipe(legible), hide_index=True, width="stretch")

# --- Sobre el modelo --------------------------------------------------------
with pestanas[4]:
    st.write(f"**Modelo:** {datos_modelo['nombre']}, entrenado con temporadas FEB 2005-2022.")
    metricas = pd.DataFrame(datos_modelo["metricas"]).T.round(3)
    st.dataframe(metricas, width="stretch")
    st.markdown("""
- **Objetivo:** al menos 15 partidos con 15 minutos por partido en la ACB en alguna de las 3 temporadas siguientes.
- **Validación por temporadas:** se entrena con el pasado y se evalúa con temporadas posteriores.
- **PR-AUC:** mide si los que se asientan quedan arriba de la lista. Al azar valdría la proporción de positivos: 0,033 en validación y prueba.
- **Limitaciones:** el filtro nacional de la FEB mide el pasaporte, no la formación (JFL);
  la Tercera FEB (EBA) no está incluida; el modelo no ve lesiones, contratos ni contexto del club.
- **Datos:** estadísticas públicas de acb.com y baloncestoenvivo.feb.es, uso académico.
  No se muestran perfiles de menores de edad.
""")