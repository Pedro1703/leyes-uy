"""Genera la página del mapa de leyes. Regenerable: al terminar el crawl,
volver a correrlo y republicar.

    python3 build_page.py && # publicar dist/mapa.html
"""
import collections, html, json, os, re, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
import clasificar

# Selección editorial. El puntaje automático sirve para filtrar; la elección
# final es a mano, porque lo gracioso no es una regex.
DESTACADAS = [
    (6450,  "Una de las 804 pensiones graciables que el Parlamento sancionó sólo en 1918. Ese año hubo 1.225 leyes y el 87,5 % fueron pensiones: llegaron en tandas correlativas de hasta 91 leyes seguidas, casi todas a viudas. Era el sistema previsional antes de que existiera un sistema previsional."),
    (10124, "Decreto Ley 10.124: «CONSEJO DE ESTADO. CREACIÓN». Es la norma que creó el cuerpo que reemplazó al Parlamento cuando Baldomir lo disolvió en 1942. El corpus documenta su propia interrupción."),
    (16037, "El velero escuela Capitán Miranda necesitó 32 leyes distintas para salir del país, una por viaje desde 1987. El Parlamento uruguayo sanciona una ley cada vez que un buque de la Armada zarpa: hay 312 permisos de este tipo."),
    (20186, "El feriado sólo rige para la tripulación de helicóptero. Es un día libre nacional para un gremio que cabe en un ascensor."),
    (20452, "Declara un «feriado laborable». Es decir: un feriado en el que se trabaja."),
    (20170, "El butiá tiene su día nacional. El 13 de marzo."),
    (19132, "El Día del Bebé cae el primer viernes de octubre. Los bebés no fueron consultados."),
    (19509, "El Día del Futuro es el último lunes de setiembre. El futuro, entonces, es puntual y cae en lunes."),
    (20042, "Un tramo de la Ruta 52 se llama «Experto Lechero Luis Bertotto Nollemberger». El cargo va incluido en el nombre."),
    (17310, "Una ley para decidir qué frases se esculpen en el mausoleo de Artigas. El Parlamento legislando sobre tipografía monumental."),
    (18370, "El Año Polar 2007-2008 fue declarado de interés nacional. Uruguay tiene base antártica, pero aun así."),
    (18268, "La erradicación de la garrapata es, por ley, de interés nacional."),
    (20529, "«Encuentro con el Patriarca», declarado de interés nacional en 2026."),
    (17452, "El año 2002 fue, oficialmente, el Año de la Educación Vial."),
    (20450, "Día Nacional del Fitomejoramiento. Cada 5 de marzo."),
    (20488, "Día Nacional del Apicultor, 13 de junio. Aprobada en 2026."),
    (20342, "Los funcionarios del Tribunal de Cuentas tienen su propio día."),
    (20270, "Día Nacional del Médico Legista, 21 de marzo."),
    (20192, "Día Nacional del Leonismo. Del club de leones."),
    (20109, "Día del Esquilador: segundo domingo de febrero de cada año."),
    (16764, "Día del Payador, sancionado en 1996."),
    (20055, "«Día de Ariel», 15 de julio. Por el ensayo de Rodó, pero el título entrecomillado no lo aclara."),
    (15870, "Una ley dedicada al mantenimiento de la cruz que conmemora la visita de Juan Pablo II."),
    (16130, "Prohíbe pegar carteles en monumentos y edificios públicos. Hizo falta una ley."),
    (18571, "El fútbol infantil es de interés nacional por ley de 2009."),
    (17421, "El primer Campeonato Sudamericano de Clubes Campeones del Interior fue declarado de interés nacional."),
    (20322, "Para el ejercicio UNITAS de 2024 hizo falta una ley que autorizara la salida de una aeronave Beechcraft B-200T. Con número de modelo incluido en el texto legal."),
    (20225, "El venado de campo fue declarado especie protegida en 2023."),
    (15963, "Coloca un busto de Isaac Ferreira Correa en el hospital de Castillos, Rocha."),
]


def build():
    recs = clasificar.cargar()
    for r in recs:
        r["cat"] = clasificar.clasificar(r["titulo"])
        r["abs"], _ = clasificar.puntaje_absurdo(r["titulo"])

    recs = [r for r in recs if r["titulo"]]
    cnt = collections.Counter(r["cat"] for r in recs)
    cats = [{"n": c, "v": v} for c, v in cnt.most_common()]

    idx = {r["nro"]: r for r in recs}
    destac = []
    for nro, nota in DESTACADAS:
        r = idx.get(nro)
        if r:
            destac.append({"nro": nro, "anio": r["anio"], "t": r["titulo"],
                           "cat": r["cat"], "nota": nota})

    anios = collections.Counter(r["anio"] for r in recs if r["anio"])
    PEN = "Pensión o recompensa a una persona"
    pen_anio = collections.Counter(r["anio"] for r in recs
                                   if r["anio"] and r["cat"] == PEN)
    leyes = [[r["nro"], r["anio"], r["cat"], r["titulo"]] for r in
             sorted(recs, key=lambda r: -r["nro"])]

    tipos = collections.Counter(r.get("tipo", "Ley") for r in recs)
    payload = {
        "total": len(recs),
        "cats": cats,
        "destacadas": destac,
        "anios": sorted(anios.items()),
        "pensiones": sorted(pen_anio.items()),
        "leyes": leyes,
        "tipos": dict(tipos),
        "rango": [min(r["anio"] for r in recs if r["anio"]),
                  max(r["anio"] for r in recs if r["anio"])],
    }

    tpl = open(os.path.join(HERE, "pagina.tpl.html"), encoding="utf-8").read()
    out = tpl.replace("/*__DATA__*/", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    dest = os.path.join(HERE, "dist", "mapa.html")
    open(dest, "w", encoding="utf-8").write(out)
    kb = os.path.getsize(dest) / 1024
    print(f"{len(recs)} normas | {len(cats)} categorías | {len(destac)} destacadas")
    print(f"-> {dest}  ({kb:.0f} KB)")


if __name__ == "__main__":
    build()
