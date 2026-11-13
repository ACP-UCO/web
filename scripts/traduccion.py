"""Traducciones de la web al inglés (americano).

Cada texto en español de la web (contenido/ y plantillas/) tiene su traducción
guardada en datos/traducciones.json ({"texto en español": "English text"}).

- Si un texto en español es nuevo o ha cambiado, no tiene traducción: la página
  en inglés lo muestra en español y la construcción avisa con la lista de
  textos pendientes. Se traducen en local (con Claude) antes de subir.
- Las traducciones que ya no se usan se borran del archivo, así las dos
  versiones de la web siempre coinciden.
- Una traducción se puede corregir en datos/traducciones.json: se respeta
  mientras no cambie el texto en español.
"""
import json
import os
import sys


class Traductor:
    def __init__(self, ruta, idioma):
        self.ruta = ruta
        self.idioma = idioma
        self.memoria = (json.loads(ruta.read_text(encoding="utf-8"))
                        if ruta and ruta.exists() else {})
        self.usadas = set()
        self.faltan = []

    def __call__(self, texto, **datos):
        """Traduce un texto. Con datos, rellena después los {huecos}."""
        if texto is None or not str(texto).strip():
            return texto
        es = str(texto).strip()
        if self.idioma == "es":
            res = es
        else:
            self.usadas.add(es)
            res = self.memoria.get(es)
            if res is None:
                if es not in self.faltan:
                    self.faltan.append(es)
                res = es
        return res.format(**datos) if datos else res

    def guardar(self):
        """Guarda las traducciones en uso (las que ya no se usan se descartan)
        y avisa de las que faltan. Devuelve el número de textos sin traducir."""
        datos = {k: v for k, v in sorted(self.memoria.items()) if k in self.usadas}
        self.ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n",
                             encoding="utf-8")
        if self.faltan:
            print(f"\n⚠️  {len(self.faltan)} textos sin traducir al inglés (salen en "
                  "español en la versión inglesa). Añádelos a datos/traducciones.json:",
                  file=sys.stderr)
            print(json.dumps({t: "" for t in self.faltan}, ensure_ascii=False, indent=1),
                  file=sys.stderr)
            if os.environ.get("GITHUB_ACTIONS"):
                print(f"::warning::{len(self.faltan)} textos sin traducir al inglés. "
                      "Ejecuta python scripts/construir.py en local y tradúcelos.")
        return len(self.faltan)
