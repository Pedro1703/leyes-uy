"""Cliente de IMPO: resuelve número->año y baja el JSON de cada ley.

IMPO sólo acepta URLs /bases/leyes/{nro}-{anio}. No hay listado por año ni
búsqueda por número solo, y un año equivocado devuelve HTTP 200 con HTML en
lugar de 404 — así que la validación es por cuerpo, no por status.

La numeración es monótona en el tiempo, con jitter de ±1 año en los cambios
de año. Eso permite interpolar el año entre anclas conocidas y sondear.
"""
import json, os, re, sqlite3, ssl, sys, time, urllib.request, urllib.error, bisect

# En esta máquina hay un proxy TLS con CA propia: el bundle de certifi que usa
# urllib por defecto lo rechaza. truststore delega en el almacén del sistema,
# que es el que ya valida bien (curl funciona).
try:
    import truststore
    _SSL = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
except ImportError:
    _SSL = ssl.create_default_context()

BASE = "https://www.impo.com.uy/bases/leyes"
UA = "leyes-uy/1.0 (proyecto de datos abiertos; contacto pedrocopelmayer@gmail.com)"
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "leyes.db")

# Segundos entre requests. IMPO pide Crawl-Delay: 10 en robots.txt, pensado
# para crawlers de buscador. Usamos una conexión única y un ritmo moderado.
# Subilo a 10 si querés cumplimiento estricto.
DELAY = float(os.environ.get("IMPO_DELAY", "1.2"))

_last = [0.0]


def _throttle():
    dt = time.time() - _last[0]
    if dt < DELAY:
        time.sleep(DELAY - dt)
    _last[0] = time.time()


def fetch(nro, anio, timeout=30, retries=3, base="leyes"):
    """Devuelve (dict, raw_bytes) si la norma existe con ese año, si no (None, None)."""
    url = f"https://www.impo.com.uy/bases/{base}/{nro}-{anio}?json=true"
    for attempt in range(retries):
        _throttle()
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/json,text/html;q=0.8",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
                raw = r.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))
            continue

        head = raw.lstrip()[:1]
        if head != b"{":
            return None, None  # HTML => ese año no es
        try:
            # Algunos JSON de IMPO traen caracteres de control sin escapar dentro
            # del texto de los artículos. strict=False los tolera; sin esto el
            # parseo falla y la norma se marca como inexistente.
            d = json.loads(raw.decode("iso-8859-1"), strict=False)
        except json.JSONDecodeError:
            return None, None
        # el número devuelto tiene que coincidir con el pedido
        if str(d.get("nroNorma", "")).strip() != str(nro):
            return None, None
        return d, raw
    return None, None


# ---------------------------------------------------------------- anclas
class Anchors:
    """Mapa número->año monótono, con interpolación y candidatos ordenados."""

    def __init__(self, pairs):
        self.m = dict(pairs)
        self._rebuild()

    def _rebuild(self):
        self.ks = sorted(self.m)
        self.vs = [self.m[k] for k in self.ks]

    def add(self, nro, anio):
        if nro not in self.m:
            self.m[nro] = anio
            i = bisect.bisect_left(self.ks, nro)
            self.ks.insert(i, nro)
            self.vs.insert(i, anio)

    def estimate(self, nro):
        i = bisect.bisect_left(self.ks, nro)
        if i == 0:
            return self.vs[0]
        if i >= len(self.ks):
            return self.vs[-1]
        lo_k, hi_k = self.ks[i - 1], self.ks[i]
        lo_v, hi_v = self.vs[i - 1], self.vs[i]
        if hi_k == lo_k:
            return lo_v
        frac = (nro - lo_k) / (hi_k - lo_k)
        return int(round(lo_v + frac * (hi_v - lo_v)))

    def bounds(self, nro):
        """(año_min, año_max) posibles dada la monotonía de las anclas vecinas."""
        i = bisect.bisect_left(self.ks, nro)
        lo = self.vs[i - 1] if i > 0 else 1825
        hi = self.vs[i] if i < len(self.ks) else 2026
        return lo, hi

    def candidates(self, nro, spread=6):
        """Años a probar, del más probable al menos."""
        est = self.estimate(nro)
        lo, hi = self.bounds(nro)
        lo, hi = lo - 1, hi + 1  # jitter de fin de año
        out, seen = [], set()
        for d in range(spread + 1):
            for y in ((est,) if d == 0 else (est - d, est + d)):
                if lo <= y <= hi and y not in seen:
                    seen.add(y)
                    out.append(y)
        return out


# ---------------------------------------------------------------- storage
SCHEMA = """
CREATE TABLE IF NOT EXISTS leyes (
  nro INTEGER PRIMARY KEY,
  anio INTEGER,
  tipo TEXT,
  nombre TEXT,
  fecha_promulgacion TEXT,
  fecha_publicacion TEXT,
  leyenda TEXT,
  referencias TEXT,
  n_articulos INTEGER,
  raw TEXT
);
CREATE TABLE IF NOT EXISTS faltantes (
  nro INTEGER PRIMARY KEY,
  intentos INTEGER,
  probados TEXT,
  ts REAL
);
CREATE INDEX IF NOT EXISTS ix_anio ON leyes(anio);
"""


def db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=60)
    c.executescript(SCHEMA)
    return c


def save(conn, nro, anio, d, raw, tipo=None):
    arts = d.get("articulos") or []
    conn.execute(
        "INSERT OR REPLACE INTO leyes VALUES (?,?,?,?,?,?,?,?,?,?)",
        (nro, anio, tipo or d.get("tipoNorma") or "Ley",
         (d.get("nombreNorma") or "").strip(),
         d.get("fechaPromulgacion"), d.get("fechaPublicacion"),
         (d.get("leyenda") or "").strip(), d.get("referenciasNorma"),
         len(arts), raw.decode("iso-8859-1")),
    )
    conn.commit()


def load_anchors(conn):
    pairs = {}
    with open(os.path.join(os.path.dirname(DB), "anchors_parlamento.json")) as f:
        for k, v in json.load(f).items():
            if int(k) > 0:
                pairs[int(k)] = int(v)
    # anclas históricas verificadas a mano
    pairs.update({1: 1830, 100: 1837, 1000: 1874, 5000: 1914,
                  10000: 1941, 14000: 1971})
    for nro, anio in conn.execute("SELECT nro, anio FROM leyes"):
        pairs[nro] = anio
    return Anchors(pairs)


def resolve(conn, anchors, nro, spread=6, verbose=True):
    """Encuentra el año de una ley. Devuelve (anio, n_sondas) o (None, n)."""
    probed = []
    for y in anchors.candidates(nro, spread):
        probed.append(y)
        d, raw = fetch(nro, y)
        if d:
            save(conn, nro, y, d, raw)
            anchors.add(nro, y)
            if verbose:
                print(f"  ley {nro:>6} -> {y}  ({len(probed)} sonda{'s' if len(probed)>1 else ''})"
                      f"  {(d.get('nombreNorma') or '')[:58]}", flush=True)
            return y, len(probed)
    conn.execute("INSERT OR REPLACE INTO faltantes VALUES (?,?,?,?)",
                 (nro, len(probed), json.dumps(probed), time.time()))
    conn.commit()
    if verbose:
        print(f"  ley {nro:>6} -> NO ENCONTRADA tras {len(probed)} sondas", flush=True)
    return None, len(probed)


def done(conn):
    return {r[0] for r in conn.execute("SELECT nro FROM leyes")}
