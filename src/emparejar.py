
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

CARPETA_RAW = Path("data/raw")
CARPETA_PROCESSED = Path("data/processed")

PALABRAS_IGNORADAS = {"de", "del", "la", "las", "los", "y", "da", "das", "do", "dos",
                      "van", "von", "jr", "ii", "iii", "iv"}

PARECIDO_MINIMO = 0.65


def palabras(nombre):
    """Conjunto de palabras normalizadas: minúsculas, sin tildes ni partículas."""
    if not isinstance(nombre, str):
        return frozenset()
    texto = unicodedata.normalize("NFKD", nombre)
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return frozenset(p for p in re.findall(r"[a-z]+", texto) if p not in PALABRAS_IGNORADAS)


def palabras_slug(slug):
    """Palabras del nombre ACB en orden, a partir de la URL ('victor-arteaga')."""
    return [p for p in palabras_ordenadas(slug.replace("-", " ")) if p not in PALABRAS_IGNORADAS]


def palabras_ordenadas(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return re.findall(r"[a-z]+", texto)


def nombre_parecido(nombre_acb, apellido, palabras_feb, minimo=PARECIDO_MINIMO):
    """True si alguna palabra FEB distinta del apellido se parece al nombre ACB."""
    return any(SequenceMatcher(None, nombre_acb, palabra).ratio() >= minimo
               for palabra in palabras_feb - {apellido})


def candidatos(acb, feb):
    """Pares (id_acb, id_feb, método) que cumplen año de nacimiento y nombre."""
    feb_por_anio = {anio: grupo for anio, grupo in feb.groupby("anio_nacimiento")}
    pares = []
    for fila in acb.itertuples():
        grupo = feb_por_anio.get(fila.anio_nacimiento)
        if grupo is None:
            continue
        nombre = palabras_slug(fila.slug)
        if not nombre:
            continue
        completos = [f.id_feb for f in grupo.itertuples() if set(nombre) <= f.palabras]
        if completos:
            pares += [(fila.id_acb, id_feb, "completo") for id_feb in completos]
            continue
        extremos = {nombre[0], nombre[-1]}
        parciales = [f.id_feb for f in grupo.itertuples() if extremos <= f.palabras]
        if parciales:
            pares += [(fila.id_acb, id_feb, "nombre_y_apellido") for id_feb in parciales]
            continue
        if len(nombre) < 2:
            continue
        parecidos = [f.id_feb for f in grupo.itertuples()
                     if nombre[-1] in f.palabras and nombre_parecido(nombre[0], nombre[-1], f.palabras)]
        pares += [(fila.id_acb, id_feb, "nombre_parecido") for id_feb in parecidos]
    return pd.DataFrame(pares, columns=["id_acb", "id_feb", "metodo"])

METODOS = ["completo", "nombre_y_apellido", "nombre_parecido"]


def resolver(pares):
    """Separa los emparejamientos únicos de los dudosos.

    Si un jugador FEB lo reclaman varios jugadores ACB con métodos distintos,
    solo cuentan las reclamaciones del método más fiable: un nombre parecido
    no puede anular un emparejamiento por nombre completo.
    """
    if pares.empty:
        return pares.copy(), pares.copy()
    rango = pares["metodo"].map(METODOS.index)
    pares = pares[rango == rango.groupby(pares["id_feb"]).transform("min")]
    por_acb = pares.groupby("id_acb")["id_feb"].transform("nunique")
    por_feb = pares.groupby("id_feb")["id_acb"].transform("nunique")
    unicos = pares[(por_acb == 1) & (por_feb == 1)]
    dudosos = pares[(por_acb > 1) | (por_feb > 1)]
    return unicos.reset_index(drop=True), dudosos.reset_index(drop=True)


def preparar_feb(fichas, temporadas):
    """Un nombre por jugador FEB (el de su última temporada) y su año de nacimiento."""
    nombres = (temporadas.sort_values("temporada").groupby("id_feb")["jugador"].last())
    feb = fichas[["id_feb", "anio_nacimiento"]].dropna().copy()
    feb["id_feb"] = feb["id_feb"].astype(str)
    feb["anio_nacimiento"] = feb["anio_nacimiento"].astype(int)
    feb["jugador"] = feb["id_feb"].map(nombres)
    feb["palabras"] = feb["jugador"].map(palabras)
    return feb[feb["palabras"].map(len) > 0]


def main():
    acb = pd.read_csv(CARPETA_PROCESSED / "jugadores.csv", dtype={"id_acb": str})
    fichas = pd.read_csv(CARPETA_RAW / "feb_jugadores.csv", dtype={"id_feb": str})
    temporadas_feb = pd.read_csv(CARPETA_PROCESSED / "feb_temporadas.csv", dtype={"id_feb": str})

    sin_anio = acb["anio_nacimiento"].isna().sum()
    acb = acb.dropna(subset=["anio_nacimiento"]).astype({"anio_nacimiento": int})
    feb = preparar_feb(fichas, temporadas_feb)

    unicos, dudosos = resolver(candidatos(acb, feb))
    unicos.to_csv(CARPETA_PROCESSED / "emparejamiento.csv", index=False)
    dudosos = (dudosos.merge(acb[["id_acb", "slug", "anio_nacimiento"]], on="id_acb")
               .merge(feb[["id_feb", "jugador"]], on="id_feb"))
    dudosos.to_csv(CARPETA_PROCESSED / "emparejamiento_dudosos.csv", index=False)

    print(f"Jugadores ACB: {len(acb) + sin_anio} (sin año de nacimiento: {sin_anio})")
    print(f"Jugadores FEB con ficha: {len(feb)}")
    print(f"Emparejados: {len(unicos)}")
    print(unicos["metodo"].value_counts().to_string())
    print(f"Casos dudosos (no emparejados): {dudosos['id_acb'].nunique()} jugadores ACB")

    parecidos = (unicos[unicos["metodo"] == "nombre_parecido"]
                 .merge(acb[["id_acb", "slug"]], on="id_acb")
                 .merge(feb[["id_feb", "jugador", "anio_nacimiento"]], on="id_feb"))
    print(f"\nEmparejados por nombre parecido (revisar): {len(parecidos)}")
    print(parecidos[["slug", "jugador", "anio_nacimiento"]].to_string(index=False))

    temporadas_acb = pd.read_csv(CARPETA_PROCESSED / "temporadas.csv", dtype={"id_acb": str})
    debut = temporadas_acb.groupby("id_acb")["anio"].min().rename("debut_acb")
    resumen = acb.set_index("id_acb").join(debut)
    resumen = resumen[resumen["debut_acb"].between(2006, 2025)]
    resumen["emparejado"] = resumen.index.isin(unicos["id_acb"])
    print("\nDebutantes en ACB 2006-2025 con pareja en la FEB:")
    print(resumen.groupby("licencia")["emparejado"].agg(["size", "mean"]).round(3).to_string())


if __name__ == "__main__":
    main()