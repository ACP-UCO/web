# Web del grupo FQM-429 · Astrofísica, Cosmología y Partículas (UCO)

https://www.uco.es/investiga/grupos/acp/ · https://www.uco.es/acp/

- **¿Quieres cambiar el contenido?** Lee [`contenido/LEEME.md`](contenido/LEEME.md).
- **¿Cómo se publica?** Automáticamente con GitHub Actions al guardar en `main`
  (ver `.github/workflows/publicar.yml`). La contraseña SFTP está guardada como
  secreto cifrado `SFTP_PASSWORD`; nunca en el código.

## Trabajar en local

```bash
pip install -r requirements.txt
python scripts/publicaciones.py      # descarga publicaciones
python scripts/construir.py          # genera _site/
python -m http.server -d _site 8000  # vista previa: http://localhost:8000
scripts/publicar.sh --prueba         # ver qué se subiría
scripts/publicar.sh                  # subir (pide la contraseña)
```

Contacto: acpu@uco.es
