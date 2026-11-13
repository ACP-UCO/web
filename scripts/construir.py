#!/usr/bin/env python3
"""Genera la web estática en _site/ a partir de contenido/, plantillas/ y estatico/.

Se generan dos versiones con las mismas páginas: español (en la raíz) e inglés
americano (en en/). Los textos en inglés salen de datos/traducciones.json
(ver scripts/traduccion.py). Con --estricto, la construcción falla si falta
alguna traducción (se usa antes de cada commit para comprobar que las dos
versiones son iguales).

Todos los enlaces internos son relativos para que la web funcione tanto en
/investiga/grupos/acp/ como en el alias /acp/.
"""
import copy
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup, escape

from traduccion import Traductor

RAIZ = Path(__file__).resolve().parent.parent
CONTENIDO = RAIZ / "contenido"
SITE = RAIZ / "_site"

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# Idiomas de la web: carpeta (relativa a _site/) y prefijo para llegar a la raíz
IDIOMAS = {"es": dict(carpeta="", raiz=""), "en": dict(carpeta="en/", raiz="../")}

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


def fecha_larga(f, idioma="es"):
    if isinstance(f, str):
        f = dt.date.fromisoformat(str(f))
    if idioma == "en":
        return f"{MONTHS[f.month - 1]} {f.day}, {f.year}"
    return f"{f.day} de {MESES[f.month - 1]} de {f.year}"


def recurso(ruta):
    """Ruta a un archivo de estatico/ con su huella (?v=...), para que el
    navegador y el servidor descarguen la versión nueva cuando cambia."""
    contenido = (RAIZ / "estatico" / ruta).read_bytes()
    return f"{ruta}?v={hashlib.md5(contenido).hexdigest()[:8]}"


def mes_corto(f, idioma="es"):
    return (MONTHS if idioma == "en" else MESES)[f.month - 1][:3]


def iniciales(nombre):
    partes = [x for x in re.split(r"[\s-]+", nombre) if x[:1].isupper()]
    return "".join(x[0] for x in partes[:2])


def _normal(t):
    """Minúsculas, sin acentos y con guiones como espacios."""
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c)).replace("-", " ")


def es_autor(autor, miembro):
    """¿El autor «Apellidos, Nombre» de una publicación es este miembro del grupo?
    Basta con que coincida el primer apellido y la inicial del nombre."""
    palabras = _normal(miembro).split()
    n_nombre = len(palabras) - 2 if len(palabras) >= 3 else 1
    apellido, inicial = palabras[n_nombre], palabras[0][0]
    apellidos, _, nombre = _normal(autor).partition(",")
    return apellido in apellidos.split() and nombre.strip()[:1] == inicial


def marcar_autores(p, mostrados=5):
    """Prepara la lista de autores de una publicación: los primeros, con los
    miembros del grupo marcados, y los miembros que quedan dentro del «et al.»."""
    vistos = set()
    p["autores_web"] = []
    for a in p["autores"][:mostrados]:
        quien = next((m for m in p["miembros"] if es_autor(a, m)), None)
        if quien:
            vistos.add(quien)
        p["autores_web"].append((a, bool(quien)))
    p["miembros_et_al"] = ([m for m in p["miembros"] if m not in vistos]
                           if p["num_autores"] > mostrados else [])


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
        noticias.append({**cab, "id": ruta.stem, "cuerpo": m.group(2)})
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
        if not logo:
            error("colaboraciones.yml", f"{c['nombre']}: falta 'logo:'.")
        if not (RAIZ / "estatico/img/colaboraciones" / logo).exists():
            error("colaboraciones.yml", f"{c['nombre']}: no encuentro el logo "
                  f"estatico/img/colaboraciones/{logo}")


def traducir_contenido(d, tr):
    """Copia del contenido con los textos pasados por el traductor tr."""
    d = copy.deepcopy(d)
    for campo in ("nombre", "universidad", "departamento", "direccion", "lema",
                  "presentacion"):
        d["sitio"][campo] = tr(d["sitio"].get(campo))

    def lista(xs):
        return [{tr(k): [tr(v) for v in (vs or [])] for k, vs in x.items()}
                if isinstance(x, dict) else tr(x) for x in (xs or [])]
    for l in d["lineas"]:
        l["titulo"], l["resumen"] = tr(l.get("titulo")), tr(l.get("resumen"))
        if l.get("lineas"):
            l["lineas"] = lista(l["lineas"])
    for p in d["actuales"] + d["antiguos"]:
        p["cargo"], p["institucion"] = tr(p.get("cargo")), tr(p.get("institucion"))
    for s in d["proximos"] + d["pasados"]:
        for campo in ("titulo", "resumen", "lugar"):
            s[campo] = tr(s.get(campo))
    for n in d["noticias"]:
        n["titulo"], n["cuerpo"] = tr(n["titulo"]), tr(n["cuerpo"])
    return d


def generar(idioma, tr, datos_es, comun):
    """Genera todas las páginas de un idioma. Devuelve la lista de páginas."""
    d = traducir_contenido(datos_es, tr)
    for n in d["noticias"]:
        n["html"] = md(n["cuerpo"])

    env = Environment(loader=FileSystemLoader(RAIZ / "plantillas"),
                      undefined=StrictUndefined, autoescape=True,
                      trim_blocks=True, lstrip_blocks=True)
    env.globals.update(recurso=recurso, t=tr, idioma=idioma)
    env.filters.update(md=md, fecha=lambda f: fecha_larga(f, idioma),
                       mes=lambda f: mes_corto(f, idioma), latex=latex_ligero,
                       iniciales=iniciales, saltos=saltos)

    hoy = comun["hoy"]
    # Sin seminarios en seminarios.yml, la sección se oculta (menú, portada y página)
    base = dict(sitio=d["sitio"], anio=hoy.year, actualizado=fecha_larga(hoy, idioma),
                hay_seminarios=comun["hay_seminarios"], **IDIOMAS[idioma],
                otro_idioma=("en/" if idioma == "es" else "../"))
    paginas = {
        "index.html": dict(lineas=d["lineas"], noticias=d["noticias"][:3],
                           proximos=d["proximos"][:3], recientes=comun["recientes"]),
        "investigacion.html": dict(lineas=d["lineas"],
                                   colaboraciones=comun["colaboraciones"]),
        "miembros.html": dict(actuales=d["actuales"], antiguos=d["antiguos"]),
        "publicaciones.html": dict(por_anio=comun["por_anio"], total=comun["total"]),
        **({"seminarios.html": dict(proximos=d["proximos"], pasados=d["pasados"])}
           if comun["hay_seminarios"] else {}),
        "noticias.html": dict(noticias=d["noticias"]),
        "contacto.html": dict(),
    }
    carpeta = SITE / IDIOMAS[idioma]["carpeta"]
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, datos in paginas.items():
        html = env.get_template(nombre).render(**base, **datos, pagina=nombre)
        (carpeta / nombre).write_text(html, encoding="utf-8")
    return list(paginas)


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
    for p in publicaciones:
        marcar_autores(p)
    por_anio = {}
    for p in publicaciones:
        por_anio.setdefault(p["anio"] or "Sin fecha", []).append(p)

    perfiles_json = RAIZ / "datos/perfiles_inspire.json"
    perfiles = json.loads(perfiles_json.read_text()) if perfiles_json.exists() else {}
    for p in miembros:
        p["enlaces"] = enlaces_miembro(p, perfiles.get(p["nombre"]))
    actuales = [p for p in miembros if not p.get("antiguo")]
    antiguos = [p for p in miembros if p.get("antiguo")]

    noticias = cargar_noticias()
    datos_es = dict(sitio=sitio, lineas=lineas, actuales=actuales, antiguos=antiguos,
                    proximos=proximos, pasados=pasados, noticias=noticias)

    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(RAIZ / "estatico", SITE, ignore=shutil.ignore_patterns(".gitkeep"))

    comun = dict(colaboraciones=colaboraciones, por_anio=por_anio,
                 total=len(publicaciones), recientes=publicaciones[:4], hoy=hoy,
                 hay_seminarios=bool(seminarios))
    trad = Traductor(RAIZ / "datos/traducciones.json", "en")
    for idioma in IDIOMAS:
        tr = trad if idioma == "en" else Traductor(None, "es")
        paginas = generar(idioma, tr, datos_es, comun)
    sin_traducir = trad.guardar()

    # Salvaguarda: nunca publicar archivos .ht* (protegen el .htpasswd del servidor)
    for f in SITE.rglob(".ht*"):
        f.unlink()
    print(f"✅ Web generada en {SITE.relative_to(RAIZ)}/ "
          f"({len(paginas)} páginas en español y {len(paginas)} en inglés)")
    if sin_traducir and "--estricto" in sys.argv:
        sys.exit("❌ Las versiones en español e inglés no coinciden: faltan traducciones.")


if __name__ == "__main__":
    main()
