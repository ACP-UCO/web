#!/usr/bin/env python3
"""Descarga las publicaciones del grupo desde INSPIRE-HEP (y ORCID como respaldo)
y las guarda en datos/publicaciones.json.

Para cada miembro de contenido/miembros.yml:
  1. Localiza su perfil de INSPIRE (campo "inspire:" o, si no, a partir del ORCID)
     y descarga sus trabajos.
  2. Si no tiene perfil en INSPIRE, o tiene "completar_con_orcid: true", añade
     los trabajos de su ORCID que no estén ya en INSPIRE.
Los trabajos compartidos por varios miembros se fusionan (por DOI, arXiv o título).

Si la red falla, se conserva el archivo anterior y se sale con aviso (no error),
para que la web se pueda seguir construyendo.
"""
import json
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


def trabajos_orcid(orcid):
    d = pedir(f"{ORCID}/{orcid}/works")
    res = []
    for g in d.get("group", []):
        s = g["work-summary"][0]
        ids = {e["external-id-type"]: e["external-id-value"]
               for e in (s.get("external-ids") or {}).get("external-id", [])}
        fecha = s.get("publication-date") or {}
        anio = (fecha.get("year") or {}).get("value")
        res.append({
            "id": f"orcid:{orcid}:{s['put-code']}",
            "inspire": None,
            "titulo": s["title"]["title"]["value"],
            "autores": [],
            "num_autores": 0,
            "revista": (s.get("journal-title") or {}).get("value"),
            "anio": int(anio) if anio else None,
            "doi": ids.get("doi"),
            "arxiv": ids.get("arxiv"),
            "tipo": (s.get("type") or "").replace("-", " "),
            "citas": None,
        })
    return res


def clave(t):
    if t.get("doi"):
        return "doi:" + t["doi"].lower()
    if t.get("arxiv"):
        return "arxiv:" + t["arxiv"].lower().removeprefix("arxiv:")
    return "titulo:" + re.sub(r"\W+", "", t["titulo"].lower())


def main():
    miembros = yaml.safe_load((RAIZ / "contenido/miembros.yml").read_text()) or []
    opciones = yaml.safe_load((RAIZ / "contenido/publicaciones.yml").read_text()) or {}
    desde = opciones.get("desde_anio") or 0
    excluir = set(opciones.get("excluir") or [])

    todos, perfiles = {}, {}
    try:
        for p in miembros:
            orcid = str(p.get("orcid") or "").strip()
            inspire = str(p.get("inspire") or "").strip()
            if not (orcid or inspire) or p.get("antiguo"):
                continue
            bai, perfil = perfil_inspire(orcid, inspire)
            if perfil:
                perfiles[p["nombre"]] = perfil
            lista, fuentes = [], []
            if bai:
                lista += trabajos_inspire(bai)
                fuentes.append("INSPIRE")
            # Sin perfil en INSPIRE, o con perfil incompleto: se completa con ORCID
            if orcid and (not bai or p.get("completar_con_orcid")):
                vistos = {clave(t) for t in lista}
                lista += [t for t in trabajos_orcid(orcid) if clave(t) not in vistos]
                fuentes.append("ORCID")
            print(f"  {p['nombre']}: {len(lista)} trabajos ({' + '.join(fuentes)})")
            for t in lista:
                t = todos.setdefault(clave(t), {**t, "miembros": []})
                if p["nombre"] not in t["miembros"]:
                    t["miembros"].append(p["nombre"])
    except Exception as e:
        print(f"AVISO: no se pudieron descargar las publicaciones ({e}). "
              "Se mantiene la lista anterior.", file=sys.stderr)
        return

    lista = [
        t for t in todos.values()
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
