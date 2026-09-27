"""Refresca el índice de leyes 1985-2026 del catálogo de datos abiertos del
Parlamento. Es la fuente que resuelve número->año sin sondear, y la que trae
las leyes nuevas entre corridas."""
import os, ssl, urllib.request, json, csv, io, re

try:
    import truststore
    _SSL = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
except ImportError:
    _SSL = ssl.create_default_context()

URL = "https://parlamento.gub.uy/transparencia/datos-abiertos/leyes-promulgadas/csv"
HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(HERE, "data", "parlamento_1985_2026.csv")


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "leyes-uy/1.0"})
    with urllib.request.urlopen(req, timeout=120, context=_SSL) as r:
        raw = r.read()
    txt = raw.decode("utf-8", errors="replace")
    rows = list(csv.DictReader(io.StringIO(txt)))
    if len(rows) < 4000:
        raise SystemExit(f"índice sospechosamente corto ({len(rows)} filas); no se sobrescribe")
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    open(DEST, "w", encoding="utf-8").write(txt)

    anchors = {}
    for r in rows:
        n = (r.get("Numero_de_Ley") or "").strip()
        m = re.search(r"/bases/leyes/(\d+)-(\d{4})", r.get("Texto_Actualizado") or "")
        if n.isdigit() and int(n) > 0 and m and m.group(1) == n:
            anchors[int(n)] = int(m.group(2))
    json.dump({str(k): anchors[k] for k in sorted(anchors)},
              open(os.path.join(HERE, "data", "anchors_parlamento.json"), "w"))
    print(f"índice: {len(rows)} filas | {len(anchors)} anclas | ley máxima {max(anchors)}")


if __name__ == "__main__":
    main()
