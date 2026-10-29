#!/usr/bin/env bash
# Sube la web generada (_site/) al servidor de la UCO por SFTP.
#
#   scripts/publicar.sh            sube los cambios (pide la contraseña)
#   scripts/publicar.sh --prueba   muestra qué subiría, sin tocar nada
#
# La contraseña NUNCA se guarda: se pide por teclado o se lee de la variable
# de entorno SFTP_PASSWORD (que en GitHub Actions viene de un secreto cifrado).
#
# Seguridad del servidor:
#   - Nunca se borra nada en el servidor (no se usa --delete).
#   - Nunca se suben ni sobrescriben archivos .ht* (.htpasswd, .htaccess).
#   - Solo se conecta si la huella del servidor coincide con scripts/known_hosts.
set -euo pipefail
cd "$(dirname "$0")/.."

SERVIDOR=lucano.uco.es
USUARIO=${SFTP_USER:-infoacpu}
REMOTO=www

if [ ! -f _site/index.html ]; then
  echo "No existe _site/. Ejecuta antes: python scripts/construir.py" >&2; exit 1
fi
if [ -n "$(find _site -name '.ht*' -print -quit)" ]; then
  echo "ABORTADO: _site/ contiene archivos .ht* y podrían sobrescribir .htpasswd." >&2; exit 1
fi
if ! command -v lftp >/dev/null; then
  echo "Falta lftp. Instálalo con: sudo apt install lftp" >&2; exit 1
fi

PRUEBA=""
[ "${1:-}" = "--prueba" ] && PRUEBA="--dry-run"

if [ -z "${SFTP_PASSWORD:-}" ]; then
  read -rsp "Contraseña SFTP de $USUARIO@$SERVIDOR (no se guarda): " SFTP_PASSWORD; echo
fi
export LFTP_PASSWORD="$SFTP_PASSWORD"   # lftp la lee del entorno: no aparece en 'ps'
unset SFTP_PASSWORD

SSH="ssh -a -x -o UserKnownHostsFile=$PWD/scripts/known_hosts -o StrictHostKeyChecking=yes"

lftp <<FIN
set cmd:fail-exit yes
set net:max-retries 2
set net:timeout 30
set sftp:connect-program "$SSH"
open --env-password -u "$USUARIO" sftp://$SERVIDOR
mirror --reverse --verbose $PRUEBA --exclude-glob .ht* --exclude-glob */.ht* _site/ $REMOTO/
bye
FIN
echo "✅ Publicado en https://www.uco.es/investiga/grupos/acp/"
