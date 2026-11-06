#!/usr/bin/env python3
"""Descarga las publicaciones del grupo desde INSPIRE-HEP (con NASA ADS y ORCID
como complemento) y las guarda en datos/publicaciones.json.

Para cada miembro de contenido/miembros.yml:
  1. Localiza su perfil de INSPIRE (campo "inspire:" o, si no, a partir del ORCID)
     y descarga sus trabajos.
  2. Si tiene "ads: true", añade los trabajos que ADS asocia a su ORCID.
     Necesita una clave de la API de ADS en la variable de entorno ADS_TOKEN
     (o en ~/.ads/dev_key); sin ella se avisa y se sigue sin ADS.
  3. Si no tiene perfil en INSPIRE, o tiene "completar_con_orcid: true", añade
     los trabajos de su ORCID.
El mismo trabajo visto en varias fuentes, o por varios miembros, se fusiona en uno
solo si coincide el DOI, el número de arXiv o el título. De cada campo se toma el
valor de la fuente más completa (INSPIRE, luego ADS, luego ORCID).

Si la red falla, se conserva el archivo anterior y se sale con aviso (no error),
para que la web se pueda seguir construyendo.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "datos" / "publicaciones.json"
PERFILES = RAIZ / "datos" / "perfiles_inspire.json"  # nombre → nº de perfil INSPIRE
INSPIRE = "https://inspirehep.net/api"
ORCID = "https://pub.orcid.org/v3.0"
ADS = "https://api.adsabs.harvard.edu/v1/search/query"
CAMPOS_ADS = ("bibcode,title,author,author_count,pub,volume,page,year,doi,"
              "identifier,doctype,citation_count")
# Tipos de documento de ADS → nombres usados por INSPIRE (lo que no está aquí,
# como resúmenes de congresos, catálogos o software, no se muestra)
TIPOS_ADS = {"article": "article", "eprint": "article", "erratum": "erratum",
             "inproceedings": "conference paper", "phdthesis": "thesis",
             "mastersthesis": "thesis", "book": "book", "inbook": "book chapter"}
PRIORIDAD = {"inspire": 0, "ads": 1, "orcid": 2}
CAMPOS = ",".join([
    "control_number", "titles", "authors.full_name", "author_count",
    "publication_info", "dois", "arxiv_eprints", "preprint_date",
    "earliest_date", "document_type", "citation_count",
])


def pedir(url, cabeceras=None):
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "web-FQM429-UCO (acpu@uco.es)",
        **(cabeceras or {}),
    })
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if intento == 2:
                raise
            time.sleep(2 * (intento + 1))


def perfil_inspire(orcid="", inspire=""):
    """Devuelve (BAI, número de perfil) del autor en INSPIRE, o (None, None).

    "inspire" puede ser el BAI (p. ej. Y.RosasGuevara.1), el número del perfil
    o su URL; si está vacío se busca el perfil por el ORCID."""
    numero = re.search(r"(\d+)/?$", inspire)
    if inspire.startswith("http") or (numero and "." not in inspire):
        if not numero:
            return None, None
        hits = [pedir(f"{INSPIRE}/authors/{numero.group(1)}?fields=ids,control_number")]
    else:
        valor = inspire or orcid
        q = urllib.parse.urlencode({"q": f'ids.value:"{valor}"',
                                    "fields": "ids,control_number"})
        hits = pedir(f"{INSPIRE}/authors?{q}")["hits"]["hits"]
    for h in hits:
        m = h["metadata"]
        for i in m.get("ids", []):
            if i["schema"] == "INSPIRE BAI":
                return i["value"], m["control_number"]
    return None, None


def trabajos_inspire(bai):
    res, pagina = [], 1
    while True:
        q = urllib.parse.urlencode({
            "q": f"a {bai}", "size": 250, "page": pagina,
            "sort": "mostrecent", "fields": CAMPOS,
        })
        d = pedir(f"{INSPIRE}/literature?{q}")
        hits = d["hits"]["hits"]
        res += [normalizar_inspire(h["metadata"]) for h in hits]
        if len(res) >= d["hits"]["total"] or not hits:
            return res
        pagina += 1


def normalizar_inspire(m):
    pub = (m.get("publication_info") or [{}])[0]
    revista = None
    if pub.get("journal_title"):
        revista = " ".join(str(x) for x in [
            pub.get("journal_title"), pub.get("journal_volume"),
        ] if x)
        pag = pub.get("page_start") or pub.get("artid")
        if pag:
            revista += f", {pag}"
    fecha = m.get("preprint_date") or m.get("earliest_date") or ""
    anio = pub.get("year") or (int(fecha[:4]) if fecha[:4].isdigit() else None)
    arxiv = (m.get("arxiv_eprints") or [{}])[0].get("value")
    doi = (m.get("dois") or [{}])[0].get("value")
    autores = [a["full_name"] for a in m.get("authors", [])]
    return {
        "id": f"inspire:{m['control_number']}",
        "inspire": m["control_number"],
        "ads": None,
        "titulo": m["titles"][0]["title"],
        "autores": autores[:10],
        "num_autores": m.get("author_count") or len(autores),
        "revista": revista,
        "anio": anio,
        "doi": doi,
        "arxiv": arxiv,
        "tipo": (m.get("document_type") or ["article"])[0],
        "citas": m.get("citation_count", 0),
    }


def clave_ads():
    clave = os.environ.get("ADS_TOKEN", "").strip()
    fichero = Path.home() / ".ads" / "dev_key"
    if not clave and fichero.exists():
        clave = fichero.read_text().strip()
    return clave


def trabajos_ads(orcid, token):
    res, inicio = [], 0
    while True:
        q = urllib.parse.urlencode({
            "q": f"orcid:{orcid}", "fl": CAMPOS_ADS, "rows": 200,
            "start": inicio, "sort": "date desc",
        })
        d = pedir(f"{ADS}?{q}", {"Authorization": f"Bearer {token}"})["response"]
        res += [normalizar_ads(m) for m in d["docs"]]
        inicio += len(d["docs"])
        if inicio >= d["numFound"] or not d["docs"]:
            return res


def normalizar_ads(m):
    revista = m.get("pub")
    if revista and not revista.lower().startswith("arxiv"):
        revista = " ".join(x for x in [revista, m.get("volume")] if x)
        pag = (m.get("page") or [None])[0]
        if pag:
            revista += f", {pag}"
    else:
        revista = None
    arxiv = next((i[6:] for i in m.get("identifier", [])
                  if i.lower().startswith("arxiv:")), None)
    autores = m.get("author", [])
    anio = m.get("year")
    return {
        "id": f"ads:{m['bibcode']}",
        "inspire": None,
        "ads": m["bibcode"],
        "titulo": (m.get("title") or [""])[0],
        "autores": autores[:10],
        "num_autores": m.get("author_count") or len(autores),
        "revista": revista,
        "anio": int(anio) if anio and anio.isdigit() else None,
        "doi": (m.get("doi") or [None])[0],
        "arxiv": arxiv,
        "tipo": TIPOS_ADS.get(m.get("doctype"), "note"),
        "citas": m.get("citation_count"),
    }


def trabajos_orcid(orcid):
    d = pedir(f"{ORCID}/{orcid}/works")
    res = []
    for g in d.get("group", []):
        s = g["work-summary"][0]
        ids = {e["external-id-type"]: e["external-id-value"]
               for e in (s.get("external-ids") or {}).get("external-id", [])}
        fecha = s.get("publication-date") or {}
        anio = (fecha.get("year") or {}).get("value")
        revista = (s.get("journal-title") or {}).get("value")
        res.append({
            "id": f"orcid:{orcid}:{s['put-code']}",
            "inspire": None,
            "ads": None,
            "titulo": s["title"]["title"]["value"],
            "autores": [],
            "num_autores": 0,
            "revista": revista if revista and "arxiv" not in revista.lower() else None,
            "anio": int(anio) if anio else None,
            "doi": ids.get("doi"),
            "arxiv": ids.get("arxiv"),
            "tipo": (s.get("type") or "").replace("-", " "),
            "citas": None,
        })
    return res


def claves(t):
    """Identificadores con los que se reconoce el mismo trabajo en otra fuente."""
    res = []
    if t.get("doi"):
        res.append("doi:" + t["doi"].lower().strip())
    if t.get("arxiv"):
        res.append("arxiv:" + t["arxiv"].lower().removeprefix("arxiv:"))
    # Título sin LaTeX, etiquetas HTML, acentos ni signos (solo si es largo,
    # para no confundir títulos genéricos)
    titulo = re.sub(r"<[^>]+>|\\[a-zA-Z]+", "", t["titulo"] or "").lower()
    titulo = re.sub(r"[^a-z0-9]+", "", titulo)
    if len(titulo) >= 25:
        res.append("titulo:" + titulo)
    return res


def fusionar(grupo):
    """Une varias versiones del mismo trabajo, campo a campo, empezando por la
    fuente preferida."""
    grupo = sorted(grupo, key=lambda t: PRIORIDAD[t["id"].split(":")[0]])
    res = dict(grupo[0])
    for t in grupo[1:]:
        for k, v in t.items():
            if k == "miembros":
                res[k] = res[k] + [m for m in v if m not in res[k]]
            elif res.get(k) in (None, "", [], 0) and v:
                res[k] = v
    return res


class Catalogo:
    """Conjunto de trabajos sin duplicados."""

    def __init__(self):
        self.trabajos = {}   # nº interno → trabajo
        self.indice = {}     # clave (DOI, arXiv o título) → nº interno
        self.siguiente = 0

    def anadir(self, t, miembro):
        t = {**t, "miembros": [miembro]}
        ks = claves(t)
        iguales = {self.indice[k] for k in ks if k in self.indice}
        grupo = [t] + [self.trabajos.pop(n) for n in iguales]
        nuevo = fusionar(grupo)
        n, self.siguiente = self.siguiente, self.siguiente + 1
        self.trabajos[n] = nuevo
        for k in {k for g in grupo for k in claves(g)}:
            self.indice[k] = n
        return not iguales


def main():
    miembros = yaml.safe_load((RAIZ / "contenido/miembros.yml").read_text()) or []
    opciones = yaml.safe_load((RAIZ / "contenido/publicaciones.yml").read_text()) or {}
    desde = opciones.get("desde_anio") or 0
    excluir = set(opciones.get("excluir") or [])

    catalogo, perfiles = Catalogo(), {}
    token_ads = clave_ads()
    if not token_ads and any(p.get("ads") for p in miembros):
        print("AVISO: falta la clave de NASA ADS (variable ADS_TOKEN); "
              "se sigue sin consultar ADS.", file=sys.stderr)
    try:
        for p in miembros:
            orcid = str(p.get("orcid") or "").strip()
            inspire = str(p.get("inspire") or "").strip()
            if not (orcid or inspire) or p.get("antiguo"):
                continue
            bai, perfil = perfil_inspire(orcid, inspire)
            if perfil:
                perfiles[p["nombre"]] = perfil
            fuentes = []
            if bai:
                fuentes.append(("INSPIRE", trabajos_inspire(bai)))
            if orcid and p.get("ads") and token_ads:
                fuentes.append(("ADS", trabajos_ads(orcid, token_ads)))
            # Sin perfil en INSPIRE, o con perfil incompleto: se completa con ORCID
            if orcid and (not bai or p.get("completar_con_orcid")):
                fuentes.append(("ORCID", trabajos_orcid(orcid)))
            resumen = []
            for nombre, lista in fuentes:
                nuevos = sum(catalogo.anadir(t, p["nombre"]) for t in lista)
                resumen.append(f"{nombre} {len(lista)} ({nuevos} nuevos)")
            print(f"  {p['nombre']}: {' + '.join(resumen)}")
    except Exception as e:
        print(f"AVISO: no se pudieron descargar las publicaciones ({e}). "
              "Se mantiene la lista anterior.", file=sys.stderr)
        return

    lista = [
        t for t in catalogo.trabajos.values()
        if (t["anio"] or 0) >= desde and t["inspire"] not in excluir
        and t["tipo"] not in ("thesis", "note", "proceedings")
        and (opciones.get("incluir_congresos") or t["tipo"] != "conference paper")
        and not (opciones.get("solo_revisadas") and not t["revista"])
    ]
    lista.sort(key=lambda t: (t["anio"] or 0, t["id"]), reverse=True)
    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(json.dumps(lista, ensure_ascii=False, indent=1))
    PERFILES.write_text(json.dumps(perfiles, ensure_ascii=False, indent=1))
    print(f"{len(lista)} publicaciones guardadas en {SALIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
