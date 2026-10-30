#!/usr/bin/env python3
"""Genera la web estática en _site/ a partir de contenido/, plantillas/ y estatico/.

Todos los enlaces internos son relativos para que la web funcione tanto en
/investiga/grupos/acp/ como en el alias /acp/.
"""
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup, escape

RAIZ = Path(__file__).resolve().parent.parent
CONTENIDO = RAIZ / "contenido"
SITE = RAIZ / "_site"

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

def error(archivo, msg):
    sys.exit(f"\n❌ Error en {archivo}:\n   {msg}\n")


def leer_yaml(nombre):
    ruta = CONTENIDO / nombre
    try:
        return yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        marca = getattr(e, "problem_mark", None)
        linea = f" (línea {marca.line + 1})" if marca else ""
        error(nombre, f"el formato no es válido{linea}. Revisa los espacios al "
                      "principio de la línea y que no falten los dos puntos.")


def md(texto):
    return Markup(markdown.markdown(texto or "", extensions=["smarty"]))


def fecha_larga(f):
    if isinstance(f, str):
        f = dt.date.fromisoformat(f)
    return f"{f.day} de {MESES[f.month - 1]} de {f.year}"


def recurso(ruta):
    """Ruta a un archivo de estatico/ con su huella (?v=...), para que el
    navegador y el servidor descarguen la versión nueva cuando cambia."""
    contenido = (RAIZ / "estatico" / ruta).read_bytes()
    return f"{ruta}?v={hashlib.md5(contenido).hexdigest()[:8]}"


def mes_corto(f):
    return MESES[f.month - 1][:3]


def iniciales(nombre):
    partes = [x for x in re.split(r"[\s-]+", nombre) if x[:1].isupper()]
    return "".join(x[0] for x in partes[:2])


def saltos(texto):
    return Markup("<br>".join(escape(l) for l in (texto or "").strip().splitlines()))


def latex_ligero(t):
    """Limpia el LaTeX más habitual de los títulos de INSPIRE."""
    t = str(escape(t)).replace("---", "—").replace("--", "–")
    t = re.sub(r"\\(?:rm|mathrm|text|mathcal|bf)\s*\{([^}]*)\}", r"\1", t)
    t = re.sub(r"\\(?:rm|it)\b\s*", "", t)
    reemplazos = {r"\nu": "ν", r"\mu": "μ", r"\tau": "τ", r"\Lambda": "Λ",
                  r"\gamma": "γ", r"\alpha": "α", r"\beta": "β", r"\sim": "∼",
                  r"\to": "→", r"\rightarrow": "→", r"\pm": "±", r"\times": "×",
                  r"\Omega": "Ω", r"\sigma": "σ", r"\ell": "ℓ", "\\": ""}
    for a, b in reemplazos.items():
        t = t.replace(a, b)
    t = re.sub(r"\^\{?([^}\s$]+)\}?", r"<sup>\1</sup>", t)
    t = re.sub(r"_\{?([^}\s$]+)\}?", r"<sub>\1</sub>", t)
    return Markup(t.replace("$", "").replace("{", "").replace("}", ""))


def cargar_noticias():
    noticias = []
    for ruta in sorted((CONTENIDO / "noticias").glob("*.md"), reverse=True):
        texto = ruta.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", texto, re.S)
        if not m:
            error(f"noticias/{ruta.name}", "debe empezar con un bloque entre "
                  "líneas '---' que contenga 'titulo:' y 'fecha:'.")
        cab = yaml.safe_load(m.group(1)) or {}
        for campo in ("titulo", "fecha"):
            if campo not in cab:
                error(f"noticias/{ruta.name}", f"falta el campo '{campo}:'.")
        noticias.append({**cab, "id": ruta.stem, "html": md(m.group(2))})
    noticias.sort(key=lambda n: str(n["fecha"]), reverse=True)
    return noticias


def enlaces_miembro(p, perfil_inspire):
    """Lista de (red, texto, url) con los enlaces que tenga rellenos el miembro."""
    def campo(nombre):
        return str(p.get(nombre) or "").strip()
    x = campo("x") or campo("twitter")
    if x and not x.startswith("http"):
        x = "https://x.com/" + x.lstrip("@")
    rg = campo("researchgate")
    if rg and not rg.startswith("http"):
        rg = "https://www.researchgate.net/profile/" + rg
    inspire = campo("inspire")
    if not inspire.startswith("http"):
        inspire = f"https://inspirehep.net/authors/{perfil_inspire}" if perfil_inspire else ""
    candidatos = [
        ("correo", "Correo electrónico", "mailto:" + campo("correo") if campo("correo") else ""),
        ("orcid", "ORCID", "https://orcid.org/" + campo("orcid") if campo("orcid") else ""),
        ("inspire", "INSPIRE-HEP", inspire),
        ("researchgate", "ResearchGate", rg),
        ("x", "X (Twitter)", x),
    ]
    return [(red, texto, url) for red, texto, url in candidatos if url]


def comprobar_miembros(miembros):
    for i, p in enumerate(miembros, 1):
        if not p.get("nombre"):
            error("miembros.yml", f"el miembro nº {i} no tiene 'nombre:'.")
        foto = p.get("foto")
        if foto and not (RAIZ / "estatico/img/miembros" / foto).exists():
            error("miembros.yml", f"{p['nombre']}: no encuentro la foto "
                  f"estatico/img/miembros/{foto}")


def comprobar_colaboraciones(colaboraciones):
    for i, c in enumerate(colaboraciones, 1):
        if not c.get("nombre"):
            error("colaboraciones.yml", f"la colaboración nº {i} no tiene 'nombre:'.")
        if not c.get("web"):
            error("colaboraciones.yml", f"{c['nombre']}: falta 'web:' (la dirección "
                  "a la que lleva el logo).")
        logo = c.get("logo")
        if logo and not (RAIZ / "estatico/img/colaboraciones" / logo).exists():
            error("colaboraciones.yml", f"{c['nombre']}: no encuentro el logo "
                  f"estatico/img/colaboraciones/{logo}")


def main():
    sitio = leer_yaml("sitio.yml")
    miembros = leer_yaml("miembros.yml") or []
    comprobar_miembros(miembros)
    lineas = leer_yaml("investigacion.yml") or []
    colaboraciones = leer_yaml("colaboraciones.yml") or []
    comprobar_colaboraciones(colaboraciones)
    seminarios = leer_yaml("seminarios.yml") or []
    for s in seminarios:
        s["fecha"] = dt.date.fromisoformat(str(s["fecha"]))
    hoy = dt.date.today()
    proximos = sorted([s for s in seminarios if s["fecha"] >= hoy], key=lambda s: s["fecha"])
    pasados = sorted([s for s in seminarios if s["fecha"] < hoy], key=lambda s: s["fecha"], reverse=True)

    pub_json = RAIZ / "datos/publicaciones.json"
    publicaciones = json.loads(pub_json.read_text()) if pub_json.exists() else []
    por_anio = {}
    for p in publicaciones:
        por_anio.setdefault(p["anio"] or "Sin fecha", []).append(p)

    perfiles_json = RAIZ / "datos/perfiles_inspire.json"
    perfiles = json.loads(perfiles_json.read_text()) if perfiles_json.exists() else {}
    for p in miembros:
        p["enlaces"] = enlaces_miembro(p, perfiles.get(p["nombre"]))
    actuales = [p for p in miembros if not p.get("antiguo")]
    antiguos = [p for p in miembros if p.get("antiguo")]

    env = Environment(loader=FileSystemLoader(RAIZ / "plantillas"),
                      undefined=StrictUndefined, autoescape=True,
                      trim_blocks=True, lstrip_blocks=True)
    env.globals["recurso"] = recurso
    env.filters.update(md=md, fecha=fecha_larga, latex=latex_ligero, mes=mes_corto,
                       iniciales=iniciales, saltos=saltos)

    comun = dict(sitio=sitio, anio=hoy.year, actualizado=fecha_larga(hoy))
    paginas = {
        "index.html": dict(lineas=lineas, noticias=cargar_noticias()[:3],
                           proximos=proximos[:3], recientes=publicaciones[:4]),
        "investigacion.html": dict(lineas=lineas, colaboraciones=colaboraciones),
        "miembros.html": dict(actuales=actuales, antiguos=antiguos),
        "publicaciones.html": dict(por_anio=por_anio, total=len(publicaciones)),
        "seminarios.html": dict(proximos=proximos, pasados=pasados),
        "noticias.html": dict(noticias=cargar_noticias()),
        "contacto.html": dict(),
    }

    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(RAIZ / "estatico", SITE, ignore=shutil.ignore_patterns(".gitkeep"))
    for nombre, datos in paginas.items():
        html = env.get_template(nombre).render(**comun, **datos, raiz="",
                                               pagina=nombre)
        (SITE / nombre).write_text(html, encoding="utf-8")

    # Salvaguarda: nunca publicar archivos .ht* (protegen el .htpasswd del servidor)
    for f in SITE.rglob(".ht*"):
        f.unlink()
    print(f"✅ Web generada en {SITE.relative_to(RAIZ)}/ ({len(paginas)} páginas)")


if __name__ == "__main__":
    main()
