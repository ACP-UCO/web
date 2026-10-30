# Cómo editar la web (sin saber programar)

Todo el contenido está en esta carpeta `contenido/`. Se edita desde la propia web
de GitHub: abre el archivo, pulsa el lápiz ✏️ («Edit this file»), haz el cambio y
pulsa **Commit changes**. En unos 2 minutos la web se actualiza sola.

| Quiero…                         | Archivo                                   |
|---------------------------------|-------------------------------------------|
| Añadir o cambiar un miembro     | `miembros.yml`                            |
| Anunciar un seminario           | `seminarios.yml`                          |
| Publicar una noticia            | crear un archivo nuevo en `noticias/`     |
| Cambiar las líneas de investigación | `investigacion.yml`                   |
| Añadir una colaboración (logo y enlace) | `colaboraciones.yml` (el logo se sube a `estatico/img/colaboraciones/`) |
| Cambiar textos generales, correo, dirección | `sitio.yml`                   |
| Ocultar una publicación         | `publicaciones.yml`                       |

## Reglas de oro

1. **Respeta los espacios del principio de cada línea.** Lo más seguro es copiar
   un bloque que ya exista y cambiar solo el texto.
2. Lo que va detrás de `#` es un comentario: no se ve en la web.
3. Las fechas se escriben `AAAA-MM-DD` (por ejemplo `2026-11-20`).
4. Si te equivocas, la web **no** se rompe: la publicación se detiene y GitHub
   te envía un correo con el error en español. Corrígelo y vuelve a guardar.

## Publicar una noticia

Pulsa **Add file → Create new file** dentro de `contenido/noticias/` y llámalo
`AAAA-MM-DD-titulo-corto.md` (por ejemplo `2026-11-03-premio-tesis.md`):

```
---
titulo: Premio extraordinario de doctorado
fecha: 2026-11-03
---

Texto de la noticia. Se pueden poner **negritas**, *cursivas* y
[enlaces](https://www.uco.es).
```

## Fotos de los miembros

Sube la foto (cuadrada, JPG, unos 300×300 píxeles) a `estatico/img/miembros/` y
escribe el nombre del archivo en el campo `foto:` del miembro.

## Publicaciones

No hay que hacer nada: se descargan solas de INSPIRE-HEP (o de ORCID) cada lunes
y cada vez que se cambia algo, a partir del campo `orcid:` de cada miembro.
