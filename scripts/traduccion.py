"""Traducción automática de la web al inglés (americano).

Cada texto en español de la web (contenido/ y plantillas/) tiene su traducción
guardada en datos/traducciones.json ({"texto en español": "English text"}).

- Si un texto en español es nuevo o ha cambiado, no tiene traducción: si hay
  clave de Claude (variable ANTHROPIC_API_KEY, o secreto del mismo nombre en
  GitHub Actions) se traduce solo; si no, la página en inglés lo muestra en
  español y la construcción avisa.
- Las traducciones que ya no se usan se borran del archivo, así las dos
  versiones de la web siempre coinciden.
- Una traducción se puede corregir a mano en datos/traducciones.json: se
  respeta mientras no cambie el texto en español.
"""
import json
import os
import sys
from pathlib import Path

MODELO = "claude-opus-5-5"

INSTRUCCIONES = """\
You translate the website of a university research group in theoretical and \
experimental physics (astrophysics, cosmology and particle physics) at the \
University of Córdoba, Spain, from Spanish into American English.

You receive a JSON list of Spanish texts. Some are short interface labels \
(menu items, buttons, headings), others are paragraphs. Rules:
- Use American spelling and the usual terminology of physics research papers.
- Keep Markdown formatting (**bold**, *italics*, [links](url)), line breaks \
and any {placeholders} exactly as they are.
- Keep proper names unchanged: people, conferences, experiments, \
collaborations, acronyms (FQM-429, ACP, LHC, CERN, BAO, CMB...). Spanish \
place names stay in Spanish (Córdoba, Campus de Rabanales, Edificio Albert \
Einstein); "España" becomes "Spain".
- Translate Spanish job titles into their usual English equivalents \
(e.g. "Profesor Titular de Universidad" → "Associate Professor").
- Translate interface labels the way an English-language website would \
word them (e.g. "Inicio" → "Home").
Return one translation per input text, with the same id."""


class Traductor:
    def __init__(self, ruta, idioma):
        self.ruta = ruta
        self.idioma = idioma
        self.memoria = (json.loads(ruta.read_text(encoding="utf-8"))
                        if ruta and ruta.exists() else {})
        self.usadas = set()
        self.faltan = []
        self.avisado = False

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

    def completar(self) -> bool:
        """Traduce con Claude los textos que faltan. Devuelve True si tradujo algo."""
        if not self.faltan:
            return False
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self._avisar("no hay clave ANTHROPIC_API_KEY para traducir")
            return False
        try:
            import anthropic
        except ImportError:
            self._avisar("falta la librería 'anthropic' (pip install -r requirements.txt)")
            return False

        pendientes = list(self.faltan)
        esquema = {
            "type": "object",
            "properties": {"traducciones": {"type": "array", "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "en": {"type": "string"}},
                "required": ["id", "en"], "additionalProperties": False}}},
            "required": ["traducciones"], "additionalProperties": False,
        }
        try:
            r = anthropic.Anthropic().beta.messages.create(
                model=MODELO,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": "medium",
                               "format": {"type": "json_schema", "schema": esquema}},
                system=INSTRUCCIONES,
                messages=[{"role": "user", "content": json.dumps(
                    [{"id": i, "es": t} for i, t in enumerate(pendientes)],
                    ensure_ascii=False, indent=1)}],
            )
        except (anthropic.APIError, ValueError) as e:
            self._avisar(f"la traducción automática ha fallado ({e})")
            return False
        if r.stop_reason != "end_turn":
            self._avisar(f"la traducción automática no terminó ({r.stop_reason})")
            return False
        texto = next(b.text for b in r.content if b.type == "text")
        nuevas = 0
        for item in json.loads(texto)["traducciones"]:
            if 0 <= item["id"] < len(pendientes) and item["en"].strip():
                self.memoria[pendientes[item["id"]]] = item["en"].strip()
                nuevas += 1
        print(f"🌐 {nuevas} textos traducidos al inglés automáticamente")
        self.faltan = [t for t in self.faltan if t not in self.memoria]
        return nuevas > 0

    def guardar(self):
        """Guarda las traducciones en uso (las que ya no se usan se descartan)."""
        if self.faltan and not self.avisado:
            self._avisar("estos textos salen en español en la web en inglés")
        datos = {k: v for k, v in sorted(self.memoria.items()) if k in self.usadas}
        self.ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n",
                             encoding="utf-8")

    def _avisar(self, motivo):
        if not self.faltan:
            return
        self.avisado = True
        print(f"⚠️  {len(self.faltan)} textos sin traducir al inglés: {motivo}.", file=sys.stderr)
        for t in self.faltan[:10]:
            print(f"     · {t[:70]}", file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::warning::{len(self.faltan)} textos sin traducir al inglés: {motivo}.")
