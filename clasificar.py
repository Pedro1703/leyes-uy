"""Clasifica leyes por materia a partir del título, y marca candidatas a 'absurdas'.

Las reglas van en orden: la primera que matchea gana. Están ordenadas de lo más
específico a lo más genérico, porque muchos títulos mencionan varias cosas.
"""
import csv, io, json, os, re, sqlite3, collections

HERE = os.path.dirname(os.path.abspath(__file__))

# (categoría, regex). Orden = prioridad.
REGLAS = [
    # --- muy específicas primero ---
    ("Permiso militar de entrada/salida",
        r"(SALIDA|INGRESO|ENTRADA)\s+(AL?\s+|DEL?\s+)?PA[IÍ]S|BUQUE\s+ROU|\bROU\s*\d|"
        r"(TROPA|EFECTIVO|PERSONAL|DELEGACI[OÓ]N|AERONAVE|BUQUE|AVI[OÓ]N)[^.]{0,70}"
        r"(AUTORIZACI[OÓ]N|INGRESO|SALIDA)|EJERCICIO\s+(COMBINADO|CONJUNTO|MILITAR)|"
        r"\bUNITAS\b|OPERATIVO\s+(CONJUNTO|COMBINADO)"),
    ("Pensión o recompensa a una persona",
        r"PENSI[OÓ]N\s+GRACIABLE|OTORGAMIENTO\s+DE\s+PENSI[OÓ]N|PENSIONES?\s+GRACIABLES?|"
        r"\bRECOMPENSA\b|PENSI[OÓ]N[^.]{0,30}OTORGAMIENTO"),
    ("Le pone nombre a algo",
        r"\b(DENOM[IÍ]N|DESIGN[AÁ]|DES[IÍ]GNASE|DENOM[IÍ]NASE)|"
        r"(ESCUELA|LICEO|RUTA|PLAZA|PUENTE|CALLE|AVENIDA|CENTRO|"
        r"BIBLIOTECA|HOSPITAL|AEROPUERTO|TRAMO)[^.]{0,60}"
        r"(DENOMINACI[OÓ]N|DESIGNACI[OÓ]N|NOMBRE)"),
    ("Categoría de una localidad",
        r"\b(PUEBLO|VILLA|CIUDAD|CENTRO\s+POBLADO|BALNEARIO)\b.{0,45}"
        r"(DECLARATORIA|CATEGOR[IÍ]A|ELEVACI[OÓ]N)|ELEVACI[OÓ]N\s+(A\s+)?(CATEGOR[IÍ]A|RANGO)"),
    ("Día / semana / mes de…",
        r"\bD[IÍ]A\s+[A-ZÁÉÍÓÚÑ]|\bSEMANA\s+(DE|NACIONAL)|\bMES\s+(DE|NACIONAL)"),
    ("Feriado puntual",         r"FERIADO"),
    ("Declarado de interés",    r"INTER[EÉ]S\s+(NACIONAL|GENERAL|DEPARTAMENTAL|T[UÚ]RISTICO)"),
    ("Monumento, busto, placa", r"MONUMENTO|BUSTO|PLACA RECORDATORIA|MAUSOLEO"),
    ("Fiestas cívicas y símbolos", r"FIESTAS?\s+C[IÍ]VICA|S[IÍ]MBOLOS?\s+PATRIO|HIMNO|ESCUDO\s+NACIONAL|PABELL[OÓ]N"),
    ("Juegos de azar",             r"JUEGOS?\s+DE\s+AZAR|LOTER[IÍ]A|QUINIELA|CASINO|APUESTA"),
    ("Condecoraciones y premios", r"CONDECORACI[OÓ]N|\bPREMIOS?\b|MEDALLA|DISTINCI[OÓ]N\s+HONOR"),
    ("Honras fúnebres",         r"HONRAS\s+F[UÚ]NEBRES|DUELO NACIONAL|TRASLADO\s+(DE\s+)?RESTOS"),
    ("Seguro de paro puntual",  r"(SEGURO|SUBSIDIO)\s+(DE\s+)?(DESEMPLEO|PARO)"),
    ("Ciudadanía / naturalización", r"CIUDADAN[IÍ]A\s+(LEGAL|NATURAL)|NATURALIZACI[OÓ]N"),
    ("Tratados y acuerdos",
        r"(ACUERDOS?|CONVENIOS?|TRATADOS?|PROTOCOLOS?|CONVENCI[OÓ]N)\b.{0,80}"
        r"(APROBACI[OÓ]N|APRU[EÉ]BASE|RATIFIC|ADHESI[OÓ]N|ENMIENDA)|"
        r"(APROBACI[OÓ]N|RATIFIC).{0,80}(ACUERDO|CONVENIO|TRATADO|PROTOCOLO)|"
        r"\bMERCOSUR\b|\bALADI\b|\bONU\b|\bOEA\b|\bOIT\b|ORGANISMO\s+INTERNACIONAL|"
        r"ACUERDOS?\s+INTERNACIONALES?|[A-ZÁÉÍÓÚÑ]{4,}\s*-\s*URUGUAY|URUGUAY\s*-\s*[A-ZÁÉÍÓÚÑ]{4,}"),
    # --- materias ---
    ("Tierras y expropiaciones",
        r"TIERRAS?\s+P[UÚ]BLICAS?|EXPROPIACI[OÓ]N|UTILIDAD\s+P[UÚ]BLICA|ENAJENACI[OÓ]N|"
        r"PADR[OÓ]N|CATASTRO"),
    ("Obras públicas",
        r"OBRAS?\s+P[UÚ]BLICAS?|PAVIMENTACI[OÓ]N|SANEAMIENTO|USINA|ALUMBRADO"),
    ("Presupuesto y rendición",
        r"PRESUPUESTO|RENDICI[OÓ]N\s+(DE\s+)?CUENTAS|BALANCE\s+DE\s+EJECUCI[OÓ]N|"
        r"LIQUIDACI[OÓ]N\s+DE\s+HABERES|EROGACI[OÓ]N"),
    ("Tributos",
        r"\bIVA\b|IMPUESTO|TRIBUT|IMESI|IRPF|IRAE|EXONERAC|GRAVAMEN|\bTASA\s|ADUANA|"
        r"ARANCEL|PATENTE\s+DE"),
    ("Defensa y fuerzas armadas",
        r"EJ[EÉ]RCITO|ARMADA|FUERZA\s+A[EÉ]REA|MILITAR|FF\.?AA|NAVAL|MARINA|SOLDADO|"
        r"GUARDIA\s+NACIONAL|INV[AÁ]LIDOS"),
    ("Jubilaciones y pensiones",
        r"JUBILAC|PASIVID|CAJA\s+(DE\s+)?JUBILAC|RETIRO|\bBPS\b|SEGURIDAD\s+SOCIAL|MONTEP[IÍ]O|PREVISIONAL|\bAFAP\b|JUBILATORI|C[OÓ]MPUTO"),
    ("Funcionarios públicos",
        r"FUNCIONARIO|\bCARGOS?\b|ESCALAF[OÓ]N|VACANTE|\bVENIA\b|REESTRUCTURA\s+ADMINISTRATIVA|"
        r"SUELDO|REMUNERACI[OÓ]N"),
    ("Salud",
        r"SALUD|M[EÉ]DIC|HOSPITAL|ENFERMEDAD|FONASA|MUTUALISTA|VACUNA|SANITARI|"
        r"ASISTENCIA\s+P[UÚ]BLICA|BENEFICENCIA|FARMAC"),
    ("Educación",
        r"EDUCACI[OÓ]N|ENSE[NÑ]ANZA|UNIVERSIDAD|ESCOLAR|DOCENTE|ANEP|UTU|INSTRUCCI[OÓ]N\s+P[UÚ]BLICA"),
    ("Trabajo", r"TRABAJ|SALARIO|LABORAL|SINDICA|CONSEJO\s+DE\s+SALARIOS|JORNADA|GREMI|\bEMPLEO\b"),
    ("Vivienda y urbanismo",
        r"VIVIENDA|URBAN|INMUEBLE|PROPIEDAD\s+HORIZONTAL|ALQUILER|BHU|MEVIR|ARRENDAMIENTO"),
    ("Penal y seguridad",
        r"DELITO|C[OÓ]DIGO\s+PENAL|PENAL|POLIC[IÍ]A|C[AÁ]RCEL|RECLUS|SEGURIDAD\s+P[UÚ]BLICA|"
        r"AMNIST[IÍ]A|INDULTO|EXTRADICI[OÓ]N"),
    ("Agro y ambiente",
        r"AGROPECUARI|GANADER|AGRICULT|FORESTAL|PESCA|AMBIENT|RIEGO|SUELO|LECHER|\bGANADO\b|"
        r"AFTOSA|GARRAPATA|MARCAS\s+Y\s+SE[NÑ]ALES|RURAL"),
    ("Empresas públicas",
        r"\b(ANCAP|UTE|ANTEL|OSE|AFE|ANP|PLUNA|BROU|BSE|BCU|INAC|INIA|ASSE)\b|"
        r"ENTE\s+AUT[OÓ]NOMO|SERVICIO\s+DESCENTRALIZADO"),
    ("Gobiernos departamentales",
        r"INTENDENC|MUNICIP|GOBIERNO\s+DEPARTAMENTAL|JUNTA\s+DEPARTAMENTAL"),
    ("Economía y finanzas",
        r"BANCO|CR[EÉ]DITO|DEUDA|FINANCIER|MONEDA|ENDEUDAMIENTO|FIDEICOMISO|EMPR[EÉ]STITO|"
        r"T[IÍ]TULOS|BOLSA"),
    ("Comercio e industria",
        r"COMERCIO|INDUSTRIA|EXPORTAC|IMPORTAC|MERCADER|ABASTO|\bFERIA\b|PRIVILEGIO|CONCESI[OÓ]N"),
    ("Transporte e infraestructura",
        r"TRANSPORTE|VIAL|CARRETER|PUERTO|AEROPUERTO|FERROCARRIL|PEAJE|TRANV[IÍ]A|"
        r"NAVEGACI[OÓ]N|CAMINO|TR[AÁ]NSITO|VELOCIDAD|BARCOS?\s+MERCANTE|BANDERA\s+NACIONAL"),
    ("Justicia y proceso",
        r"JUZGADO|JUDICIAL|\bJUSTICIA\b|C[OÓ]DIGO|PROCES|MAGISTRAD|FISCAL[IÍ]A|ABOGAC|"
        r"REGISTROS?\s+P[UÚ]BLICOS?|NOTARIAL|PASAPORTE|MIGRACI[OÓ]N|HABILITACI[OÓ]N\s+DE\s+EDAD"),
    ("Derechos y familia",
        r"DERECHOS|MENOR|INFANCIA|ADOLESCEN|FAMILIA|G[EÉ]NERO|DISCAPACI|VIOLENCIA|LIBERTAD\s+DE|"
        r"DISCRIMINAC|MATRIMONIO|ADOPCI[OÓ]N"),
    ("Cultura y deporte",
        r"CULTURA|DEPORT|PATRIMONIO|MUSEO|ARTIST|F[UÚ]TBOL|BIBLIOTECA|TEATRO|LIBRO|M[UÚ]SICA|CARNAVAL"),
    ("Poderes del Estado",
        r"PODER\s+(EJECUTIVO|LEGISLATIVO|JUDICIAL)|ASAMBLEA\s+GENERAL|"
        r"C[AÁ]MARA\s+DE\s+(SENADORES|REPRESENTANTES)|CONSTITUCI[OÓ]N|SESIONES\s+LEGISLATIVAS|"
        r"ELECCIONES|SUFRAGIO|PLEBISCITO|SENADO"),
]


# Señales de rareza: no definen la categoría, suman puntaje de "absurdo".
SENALES = [
    (4, "nombre propio completo en el título", r"\b[A-ZÁÉÍÓÚÑ]{3,}\s*,\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+"),
    (3, "día nacional de algo muy específico", r"D[IÍ]A\s+NACIONAL\s+DEL?\s+\w{6,}"),
    (3, "declara de interés nacional un evento", r"INTER[EÉ]S\s+NACIONAL"),
    (3, "feriado para una sola localidad", r"FERIADO[^.]{0,80}(LOCALIDAD|CIUDAD|VILLA|PUEBLO|DEPARTAMENTO)"),
    (3, "título larguísimo", None),           # se calcula aparte
    (2, "le pone nombre a un tramo de ruta", r"TRAMO[^.]{0,60}RUTA|RUTA[^.]{0,60}DENOMIN"),
    (2, "oficio o profesión muy específica", r"\b(APICULTOR|LECHERO|FITOMEJORAM|QUESERO|ESQUILADOR|"
                                             r"CANILLITA|ZAFRAL|ARTESANO|TAMBERO|CARNICERO)\w*"),
    (2, "conmemora un aniversario", r"ANIVERSARIO|CENTENARIO|BICENTENARIO|CONMEMORAC"),
    (2, "honras fúnebres", r"HONRAS\s+F[UÚ]NEBRES"),
    (2, "una sola empresa nombrada", r"\bS\.?A\.?\b|\bS\.?R\.?L\.?\b|LTDA"),
    (1, "pensión graciable", r"PENSI[OÓ]N\s+GRACIABLE"),
    (1, "monumento o busto", r"MONUMENTO|BUSTO"),
]

OTRA = "Otras"


def clasificar(titulo):
    t = (titulo or "").upper()
    for cat, rx in REGLAS:
        if re.search(rx, t):
            return cat
    return OTRA


def puntaje_absurdo(titulo):
    t = (titulo or "").upper()
    score, razones = 0, []
    for peso, etiqueta, rx in SENALES:
        if rx is None:
            continue
        if re.search(rx, t):
            score += peso
            razones.append(etiqueta)
    if len(titulo or "") > 160:
        score += 3
        razones.append("título larguísimo")
    return score, razones


def cargar():
    """Une el índice del Parlamento con lo que ya bajó el crawl."""
    recs = {}
    path = os.path.join(HERE, "data", "parlamento_1985_2026.csv")
    for r in csv.DictReader(io.StringIO(open(path, encoding="utf-8").read())):
        n = r["Numero_de_Ley"].strip()
        if not n.isdigit() or int(n) == 0:
            continue
        recs[int(n)] = {
            "nro": int(n), "anio": int(r["Fecha"][:4]), "fecha": r["Fecha"],
            "titulo": " ".join((r["Titulo"] or "").split()),
            "tipo": "Ley", "fuente": "parlamento",
        }
    db = os.path.join(HERE, "data", "leyes.db")
    if os.path.exists(db):
        c = sqlite3.connect(db)
        try:
            q = "SELECT nro, anio, tipo, nombre, fecha_promulgacion, n_articulos FROM leyes"
            for nro, anio, tipo, nombre, fp, na in c.execute(q):
                prev = recs.get(nro, {})
                recs[nro] = {
                    "nro": nro, "anio": anio, "fecha": prev.get("fecha") or fp or "",
                    "titulo": prev.get("titulo") or " ".join((nombre or "").split()),
                    "tipo": tipo or "Ley", "fuente": "impo", "n_articulos": na,
                }
        except sqlite3.OperationalError:
            pass
    return [recs[k] for k in sorted(recs)]


def main():
    recs = cargar()
    for r in recs:
        r["categoria"] = clasificar(r["titulo"])
        r["absurdo"], r["razones"] = puntaje_absurdo(r["titulo"])

    cnt = collections.Counter(r["categoria"] for r in recs)
    print(f"{len(recs)} normas | {len(cnt)} categorías\n")
    print(f"{'CATEGORÍA':34} {'N':>6} {'%':>6}")
    for cat, n in cnt.most_common():
        print(f"{cat:34} {n:6} {100*n/len(recs):5.1f}%")

    out = os.path.join(HERE, "data", "clasificado.json")
    json.dump(recs, open(out, "w"), ensure_ascii=False)
    print(f"\n-> {out}")

    top = sorted(recs, key=lambda r: (-r["absurdo"], -len(r["titulo"])))[:25]
    print("\n=== top candidatas ===")
    for r in top:
        print(f"  [{r['absurdo']:>2}] {r['anio']} L.{r['nro']}  {r['titulo'][:88]}")


if __name__ == "__main__":
    main()
