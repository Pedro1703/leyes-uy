# leyes-uy

Corpus completo de la legislación uruguaya —1830 a hoy— bajado de IMPO y del
catálogo de datos abiertos del Parlamento, clasificado por materia y publicado
como un mapa interactivo.

Una de cada cinco leyes sancionadas desde 1985 sirve para ponerle nombre a una
escuela, una ruta o una plaza. El velero escuela *Capitán Miranda* necesitó 32
leyes distintas para salir del país.

## Cómo se consigue el corpus

**1985–2026** sale del [catálogo de datos abiertos del Parlamento][parl], que
publica número, fecha, título y —clave— la URL de IMPO con el año ya resuelto.

**1830–1985** no tiene índice. IMPO exige `número-año` en la URL y no acepta el
número solo, así que hay que descubrir el año de cada norma. Como la numeración
es monótona en el tiempo, se interpola entre anclas conocidas y se sondea.
Procesando en orden secuencial —el año de la norma N+1 es casi siempre el de N
o uno más— cuesta **1,05 sondas por norma**.

El texto completo sale de [IMPO][impo], que expone cualquier norma en JSON
agregando `?json=true` a su dirección.

## Tres trampas del origen de datos

Las tres costaron una corrida entera del crawl. Están documentadas porque
cualquiera que reuse esta fuente se las va a encontrar.

**Un año equivocado devuelve HTTP 200 con HTML, no 404.** La validación tiene
que ser por cuerpo: se comprueba que la respuesta empiece con `{` y que el
`nroNorma` devuelto coincida con el pedido.

**Algunos JSON traen caracteres de control sin escapar** dentro del texto de los
artículos, y `json.loads` estricto los rechaza. Hay que usar `strict=False`; si
no, esas normas parecen inexistentes.

**La numeración es una serie continua que atraviesa dos períodos sin
Parlamento**, en los que las normas se publicaron como decretos-ley y viven en
otra base de IMPO:

| período | qué pasó | base |
|---|---|---|
| 1942–1943 | Baldomir disuelve el Parlamento | `/bases/decretos-ley` |
| 1973–1985 | dictadura | `/bases/decretos-ley` |

No alcanza con mirar `/bases/leyes`: cada año candidato se prueba contra ambas.
El decreto-ley 10.124 de 1942 es, apropiadamente, «CONSEJO DE ESTADO. CREACIÓN».

Y una regla general de este corpus: **los títulos son listas de palabras clave
separadas por punto** («AVIACIÓN CIVIL INTERNACIONAL. CONVENIO. PROTOCOLO.
ENMIENDA. APROBACIÓN.»), así que restringir la proximidad con `[^.]` en una
expresión regular impide cruzar el separador natural del texto.

## Piezas

| archivo | qué hace |
|---|---|
| `impo.py` | cliente de IMPO: resolución de año, validación, rate-limit, SQLite |
| `crawl.py` | recorre los tres tramos; resumible y con presupuesto de tiempo |
| `fetch_index.py` | refresca el índice del Parlamento y las anclas |
| `clasificar.py` | 38 categorías por reglas sobre el título |
| `build_page.py` + `pagina.tpl.html` | generan el mapa interactivo |

## Uso

```bash
python3 fetch_index.py                 # índice 1985+
IMPO_DELAY=1.0 python3 crawl.py all    # corpus completo (resumible)
python3 clasificar.py                  # distribución por categoría
python3 build_page.py                  # -> dist/mapa.html
```

`IMPO_DELAY` son los segundos entre requests. El `robots.txt` de IMPO pide
`Crawl-Delay: 10`, pensado para crawlers de buscador; el valor por defecto acá
es 1 segundo con una sola conexión. Subilo si querés cumplimiento estricto.

La base no se commitea: viaja comprimida como asset de la release `datos`, para
no inflar el historial de git con un binario por corrida.

## Automatización

`.github/workflows/crawl.yml` corre cada 6 horas: baja la base de la release,
crawlea con un presupuesto de 5 horas, reconstruye los datos derivados y la
página, y vuelve a subir la base. Como el crawl es resumible, cada corrida
avanza desde donde quedó la anterior. Cuando el corpus está completo las
corridas siguientes cuestan casi nada y sirven para incorporar las leyes nuevas.

## Fuentes

- [IMPO · Datos Abiertos][impo] — normativa nacional desde 1830 en JSON
- [Parlamento · Leyes promulgadas][parl] — índice 1985 en adelante

[impo]: https://www.impo.com.uy/datosabiertos/
[parl]: https://catalogodatos.gub.uy/dataset/parlamento-del-uruguay-leyes-promulgadas-del-poder-ejecutivo
