"""Crawl completo de IMPO: leyes 1830-2026 + decretos-ley 1973-1985.

Procesa en orden secuencial: como la numeración es monótona en el tiempo, el
año de la norma N+1 es casi siempre el de N o uno más. Eso baja el costo de
~2,9 sondas por norma (interpolación a ciegas) a ~1,15.

Resumible: relee lo ya guardado en SQLite y sigue donde quedó.
  python3 crawl.py leyes       # 1..14099 en /bases/leyes
  python3 crawl.py decretosley # 14100..15735 en /bases/decretos-ley
  python3 crawl.py modernas    # 15736..20530 desde el índice del Parlamento
"""
import csv, io, json, os, re, sys, time
import impo

HERE = os.path.dirname(os.path.abspath(__file__))

# Presupuesto de tiempo: en GitHub Actions el job muere a las 6 h, así que el
# crawl corta solo antes y deja la base lista para que la próxima corrida siga.
BUDGET = float(os.environ.get("CRAWL_BUDGET_SECONDS", "0")) or None
_START = time.time()


class Agotado(Exception):
    pass


def _check_budget():
    if BUDGET and time.time() - _START > BUDGET:
        raise Agotado()
# Fin del tramo de leyes previo al quiebre institucional y comienzo de los
# decretos-ley. 15736 (13/03/1985) es la primera ley de la democracia restaurada.
DL_START, DL_END = 14100, 15735
MOD_START = 15736


def _log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def seq_candidates(prev_year, lo=1825, hi=2026, back=2, fwd=4):
    """Años a probar para la norma siguiente, dado el año de la anterior."""
    if prev_year is None:
        return []
    out = []
    for y in [prev_year + d for d in range(0, fwd + 1)] + \
             [prev_year - d for d in range(1, back + 1)]:
        if lo <= y <= hi and y not in out:
            out.append(y)
    return out


def crawl_range(bases, lo, hi, year_lo, year_hi):
    """Recorre un rango probando TODAS las bases en cada año candidato.

    Uruguay tuvo dos períodos sin Parlamento en que las normas se numeraron en
    la misma serie pero se publicaron como decretos-ley: 1942-43 (Baldomir) y
    1973-85. No alcanza con mirar /bases/leyes.

    Un fallo de red NO se anota como hueco: sólo se marca ausente una norma
    cuando el servidor respondió y dijo que no existe.
    """
    conn = impo.db()
    A = impo.load_anchors(conn)
    have = {r[0]: r[1] for r in conn.execute(
        "SELECT nro, anio FROM leyes WHERE nro BETWEEN ? AND ?", (lo, hi))}
    missed = {r[0] for r in conn.execute(
        "SELECT nro FROM faltantes WHERE nro BETWEEN ? AND ?", (lo, hi))}
    _log(f"rango {lo}-{hi} | bases {bases} | en base {len(have)} | huecos {len(missed)}")

    prev = None
    t0, n_req, n_hit, n_gap, n_neterr = time.time(), 0, 0, 0, 0

    for n in range(lo, hi + 1):
        try:
            _check_budget()
        except Agotado:
            _log(f"presupuesto agotado en la norma {n}; se retoma en la próxima corrida")
            break
        if n in have:
            prev = have[n]
            continue
        if n in missed:
            continue

        cands = seq_candidates(prev, year_lo, year_hi)
        for y in A.candidates(n, spread=5):
            if year_lo <= y <= year_hi and y not in cands:
                cands.append(y)

        got = None
        red_ok = True          # ¿el servidor contestó en todos los intentos?
        for y in cands:
            for base in bases:
                n_req += 1
                try:
                    d, raw = impo.fetch(n, y, base=base)
                except Exception as e:
                    red_ok = False
                    n_neterr += 1
                    _log(f"  red caída en {n}-{y} ({base}): {e}; pausa 60s")
                    time.sleep(60)
                    continue
                if d:
                    impo.save(conn, n, y, d, raw, tipo=d.get("tipoNorma"))
                    A.add(n, y); prev = y; got = (y, base); n_hit += 1
                    break
            if got:
                break

        if got is None:
            if red_ok:
                conn.execute("INSERT OR REPLACE INTO faltantes VALUES (?,?,?,?)",
                             (n, len(cands), json.dumps(cands), time.time()))
                conn.commit()
                n_gap += 1
            else:
                # no se pudo determinar: se deja sin marcar para reintentar
                _log(f"  {n} sin determinar por red; queda para el próximo pase")

        done_ = n_hit + n_gap
        if done_ and done_ % 100 == 0 and got:
            el = time.time() - t0
            rate = n_req / max(el, 1)
            eta = (hi - n) * (n_req / max(done_, 1)) / max(rate, .001) / 3600
            _log(f"  {n} | {n_hit} ok, {n_gap} huecos, {n_neterr} err.red "
                 f"| {n_req/max(done_,1):.2f} sondas/norma | {rate:.2f} req/s | faltan ~{eta:.1f} h")

    _log(f"FIN {lo}-{hi}: {n_hit} nuevas, {n_gap} huecos, {n_neterr} errores de red")


def crawl_modernas():
    """1985-2026: el Parlamento ya da el año, así que es 1 request por ley."""
    conn = impo.db()
    path = os.path.join(HERE, "data", "parlamento_1985_2026.csv")
    rows = list(csv.DictReader(io.StringIO(open(path, encoding="utf-8").read())))
    pairs = []
    for r in rows:
        m = re.search(r"/bases/leyes/(\d+)-(\d{4})", r["Texto_Actualizado"] or "")
        if m:
            pairs.append((int(m.group(1)), int(m.group(2))))
    have = {r[0] for r in conn.execute("SELECT nro FROM leyes")}
    todo = [(n, y) for n, y in sorted(set(pairs)) if n not in have and n >= MOD_START]
    _log(f"modernas: {len(todo)} por bajar de {len(set(pairs))} en el índice")

    t0 = 0
    for i, (n, y) in enumerate(todo, 1):
        try:
            _check_budget()
        except Agotado:
            _log(f"presupuesto agotado con {len(todo)-i+1} modernas pendientes")
            break
        try:
            d, raw = impo.fetch(n, y)
        except Exception as e:
            _log(f"  error en {n}-{y}: {e}; pausa 30s")
            time.sleep(30)
            continue
        if d:
            impo.save(conn, n, y, d, raw, tipo="Ley")
        else:
            conn.execute("INSERT OR REPLACE INTO faltantes VALUES (?,?,?,?)",
                         (n, 1, json.dumps([y]), time.time()))
            conn.commit()
        if i % 100 == 0:
            _log(f"  {i}/{len(todo)}  (ley {n})")
    _log("modernas: FIN")


def resumen():
    conn = impo.db()
    n = conn.execute("SELECT COUNT(*) FROM leyes").fetchone()[0]
    g = conn.execute("SELECT COUNT(*) FROM faltantes").fetchone()[0]
    mx = conn.execute("SELECT MAX(nro) FROM leyes").fetchone()[0] or 0
    tipos = dict(conn.execute("SELECT tipo, COUNT(*) FROM leyes GROUP BY tipo"))
    _log(f"BASE: {n} normas | {g} ausentes confirmadas | máximo nro {mx} | {tipos}")
    return n


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    # Una sola pasada: en cada año candidato se prueban ambas bases, porque la
    # serie de numeración es continua a través de los períodos de facto.
    if what in ("leyes", "all"):
        crawl_range(("leyes", "decretos-ley"), 1, DL_END, 1825, 1986)
    if what in ("modernas", "all"):
        crawl_modernas()
    resumen()
