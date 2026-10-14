"""
MOTOR DE INFERENCIA - Sistema experto de orientación vocacional USAT
====================================================================
Encadenamiento hacia adelante: parte de las respuestas del estudiante (hechos)
y aplica las reglas de basedeconocimiento.py hasta llegar a una sugerencia.

Ciclo del motor:
  1. Buscar las reglas cuyas condiciones se cumplen y que aún no se dispararon.
  2. Resolver el conflicto: elegir la de mayor prioridad; si empatan, la de
     menor ID. Cada regla se dispara una sola vez (refracción).
  3. Ejecutar sus acciones, guardar el paso en la traza y volver al paso 1.
  4. Terminar cuando ninguna regla nueva pueda dispararse.

Contiene:
  - BaseHechos:       memoria de trabajo (respuestas y hechos inferidos).
  - Procedimientos:   funciones que algunas reglas invocan (ordenar, desempatar).
  - MotorInferencia:  el ciclo de encadenamiento hacia adelante.
  - Explicación:      el "¿cómo?" y el "¿por qué?" de cada resultado.
"""
import re

from basedeconocimiento import AREAS, BLOQUES, CARRERAS, REGLAS

ORDEN_AREAS = ["C", "H", "A", "S", "I", "D", "E"]
ETIQUETA = {2: "Sí", 1: "A veces", 0: "No"}


# =============================================================================
# BASE DE HECHOS
# =============================================================================
class BaseHechos:
    """Guarda las respuestas del estudiante y lo que el motor va infiriendo."""

    def __init__(self, respuestas=None):
        self.hechos = {"avisos": []}
        for clave, valor in (respuestas or {}).items():
            if valor is not None and valor != "":
                self.hechos[clave] = int(valor)

    def existe(self, nombre):
        return nombre in self.hechos

    def obtener(self, nombre, defecto=None):
        return self.hechos.get(nombre, defecto)

    def asignar(self, nombre, valor):
        self.hechos[nombre] = valor

    def agregar_aviso(self, texto):
        if texto not in self.hechos["avisos"]:
            self.hechos["avisos"].append(texto)


# =============================================================================
# PROCEDIMIENTOS QUE INVOCAN ALGUNAS REGLAS (acción {"funcion": ...})
# Se usan cuando la conclusión necesita comparar u ordenar varios hechos.
# =============================================================================
def _puntajes(h):
    return {a: h.obtener(f"puntaje_{a}", 0) for a in ORDEN_AREAS}


def elegir_area_1(h):                                   # regla R048
    p = _puntajes(h)
    maximo = max(p.values())
    empatadas = [a for a in ORDEN_AREAS if p[a] == maximo]
    cambios = {"area_1": empatadas[0]}
    if len(empatadas) > 1:
        cambios["empate_areas"] = empatadas
    return cambios


def desempatar_por_aptitud(h):                          # regla R050
    empatadas = h.obtener("empate_areas")
    aptitud = {a: h.obtener(AREAS[a]["aptitud"], 0) for a in empatadas}
    mejor = max(aptitud.values())
    ganadoras = [a for a in empatadas if aptitud[a] == mejor]
    cambios = {"area_1": ganadoras[0]}
    if len(ganadoras) > 1:
        cambios["empate_persiste"] = ganadoras
    return cambios


def elegir_area_2(h):                                   # regla R049
    p = _puntajes(h)
    resto = sorted([a for a in ORDEN_AREAS if a != h.obtener("area_1")], key=lambda a: -p[a])
    return {"area_2": resto[0], "area_3": resto[1]}


def reemplazar_area_D(h):                               # regla R052
    return {"area_1": h.obtener("area_2"), "area_2": h.obtener("area_3"), "aviso_D": True}


def calcular_facultad_alternativa(h):                   # regla R067
    a2, facultad = h.obtener("area_2"), h.obtener("facultad")
    if h.obtener(f"nivel_{a2}") not in ("alto", "medio"):
        return {}
    alternativa = AREAS[a2]["facultad"]
    # A y E pueden llevar a dos facultades: si la primera coincide, se ofrece la otra.
    if alternativa == facultad and a2 == "A":
        alternativa = "Ingeniería"
    if alternativa == facultad and a2 == "E":
        alternativa = "Ciencias Empresariales"
    if alternativa is None or alternativa == facultad:
        return {}
    return {"facultad_alternativa": alternativa}


def ordenar_carreras(h):                                # regla R114
    carreras = BLOQUES[h.obtener("facultad")]["carreras"]
    puntajes = {c: h.obtener(f"puntaje_{c}", 0) for c in carreras}
    ranking = sorted(carreras, key=lambda c: -puntajes[c])
    cambios = {
        "ranking": [{"carrera": c, "puntaje": puntajes[c]} for c in ranking],
        "carrera_1": ranking[0],
        "carrera_2": ranking[1],
        "puntaje_max_carrera": puntajes[ranking[0]],
        "empate_carreras": puntajes[ranking[0]] > 0 and puntajes[ranking[0]] == puntajes[ranking[1]],
    }
    a1 = h.obtener("area_1")
    if h.existe(f"confianza_{a1}"):
        cambios["confianza_area_1"] = h.obtener(f"confianza_{a1}")
    return cambios


def armar_recomendacion(h):                             # regla R118
    opciones, ranking = [], h.obtener("ranking")
    if h.obtener("sin_carrera"):
        opciones.append({"tipo": "facultad", "clave": h.obtener("facultad"),
                         "nombre": "Facultad de " + h.obtener("facultad"), "facultad": ""})
    else:
        for item in ranking[:2]:
            if item["puntaje"] > 0:
                c = CARRERAS[item["carrera"]]
                opciones.append({"tipo": "carrera", "clave": item["carrera"], "nombre": c["nombre"],
                                 "facultad": c["facultad"]})
    alternativa = h.obtener("facultad_alternativa")
    if alternativa:
        opciones.append({"tipo": "facultad", "clave": alternativa, "nombre": "Facultad de " + alternativa,
                         "facultad": "Opción por tu segunda área"})
    if len(opciones) < 3 and len(ranking) > 2 and ranking[2]["puntaje"] > 0 and not h.obtener("sin_carrera"):
        c = CARRERAS[ranking[2]["carrera"]]
        opciones.append({"tipo": "carrera", "clave": ranking[2]["carrera"], "nombre": c["nombre"],
                         "facultad": c["facultad"]})
    return {"recomendacion": opciones[:3]}


PROCEDIMIENTOS = {f.__name__: f for f in [elegir_area_1, desempatar_por_aptitud, elegir_area_2,
                                          reemplazar_area_D, calcular_facultad_alternativa,
                                          ordenar_carreras, armar_recomendacion]}


# =============================================================================
# MOTOR DE INFERENCIA (encadenamiento hacia adelante)
# =============================================================================
class MotorInferencia:
    MAX_CICLOS = 500

    def __init__(self, reglas=REGLAS):
        self.reglas = reglas

    def _valor(self, h, expresion):
        """'p19+p20' suma varios hechos; devuelve None si falta alguno."""
        if "+" in expresion:
            partes = expresion.split("+")
            if not all(h.existe(p) for p in partes):
                return None
            return sum(h.obtener(p) for p in partes)
        return h.obtener(expresion)

    def _cumple(self, h, condicion):
        if isinstance(condicion, dict):        # {"contar": [...], "valor": x, "minimo": n}
            n = sum(1 for v in condicion["contar"] if h.obtener(v) == condicion["valor"])
            return n >= condicion["minimo"]
        variable, op, esperado = condicion
        valor = self._valor(h, variable)
        if op == "defined":
            return valor is not None
        if op == "undefined":
            return valor is None
        if op == "!=":
            return valor != esperado
        if valor is None:
            return False
        if op == "==":
            return valor == esperado
        if op == "in":
            return valor in esperado
        if op == ">=":
            return valor >= esperado
        if op == "<=":
            return valor <= esperado
        raise ValueError(f"Operador desconocido: {op}")

    def _ejecutar(self, h, regla):
        cambios = {}
        for accion in regla["acciones"]:
            if "set" in accion:
                cambios.update(accion["set"])
            elif "sum" in accion:
                s = accion["sum"]
                cambios[s["destino"]] = sum(h.obtener(v, 0) for v in s["variables"])
            elif "add" in accion:
                for var, delta in accion["add"].items():
                    cambios[var] = max(0, h.obtener(var, 0) + delta)
            elif "aviso" in accion:
                h.agregar_aviso(accion["aviso"])
            elif "funcion" in accion:
                cambios.update(PROCEDIMIENTOS[accion["funcion"]](h))
        for clave, valor in cambios.items():
            h.asignar(clave, valor)
        return cambios

    def inferir(self, respuestas):
        """Ejecuta el encadenamiento hacia adelante. Devuelve (hechos, traza)."""
        h = BaseHechos(respuestas)
        disparadas, traza = set(), []
        for _ in range(self.MAX_CICLOS):
            agenda = [r for r in self.reglas
                      if r["id"] not in disparadas and all(self._cumple(h, c) for c in r["condiciones"])]
            if not agenda:
                break
            regla = min(agenda, key=lambda r: (-r["prioridad"], r["id"]))   # resolución de conflictos
            cambios = self._ejecutar(h, regla)
            disparadas.add(regla["id"])
            traza.append({"id": regla["id"], "grupo": regla["grupo"], "si": regla["si"],
                          "entonces": regla["entonces"], "fuente": regla["fuente"], "cambios": cambios})
        return h, traza


# =============================================================================
# EXPLICACIÓN
# =============================================================================
def por_que_etapa2(traza, h):
    """'¿Por qué?' se hacen las preguntas de la etapa 2."""
    a1, a2 = h.obtener("area_1"), h.obtener("area_2")
    regla = next((t for t in traza if t["grupo"].startswith("G7") and "facultad" in t["cambios"]), None)
    texto = (f"Tu área más alta fue {AREAS[a1]['nombre'].lower()} ({h.obtener('puntaje_' + a1)} de 4) "
             f"y la segunda, {AREAS[a2]['nombre'].lower()} ({h.obtener('puntaje_' + a2)} de 4). "
             f"Por eso te ubicamos en {h.obtener('facultad')}")
    if regla:
        texto += f" (regla {regla['id']})"
    return texto + "."


def razones(opcion, traza, h):
    """Razones de una opción recomendada, citando las reglas que la respaldan."""
    if opcion["tipo"] == "facultad":
        a2 = h.obtener("area_2")
        if h.obtener("facultad_alternativa") == opcion["clave"]:
            r = next((t for t in traza if "facultad_alternativa" in t["cambios"]), None)
            return [f"Tu segunda área, {AREAS[a2]['nombre'].lower()}, tuvo nivel {h.obtener('nivel_' + a2)}"
                    + (f" (regla {r['id']})." if r else ".")]
        return ["Tu área principal apunta a esta facultad, pero ninguna de sus carreras destacó en la etapa 2."]
    lista = [por_que_etapa2(traza, h)]
    preguntas = {p["id"]: p["texto"] for p in BLOQUES[h.obtener("facultad")]["preguntas"]}
    for t in traza:
        if "puntaje_" + opcion["clave"] not in t["cambios"] or not t["grupo"].startswith("G9"):
            continue
        ps = sorted(set(re.findall(r"p\d+", t["si"])), key=lambda x: int(x[1:]))
        citas = " y ".join(f"«{ETIQUETA.get(h.obtener(p), '—')}» a «{preguntas[p]}»" for p in ps if p in preguntas)
        if "favorecida" in t["si"]:
            lista.append(f"Recibió un punto extra porque tus dos áreas principales favorecen esta carrera (regla {t['id']}).")
        elif "−" in t["entonces"]:
            lista.append(f"Restó un punto por tu respuesta {citas} (regla {t['id']}).")
        else:
            sujeto = "tus respuestas" if len(ps) > 1 else "tu respuesta"
            lista.append(f"Sumó a favor {sujeto} {citas} (regla {t['id']}).")
    return lista


# =============================================================================
# VALIDACIÓN CON CASOS DE PRUEBA (sección 4 del informe)
# =============================================================================
def validar(casos):
    """
    casos: lista de dicts con las respuestas p1..p20, "facultad_esperada" y
    "carrera_esperada" (clave de CARRERAS, o "indefinido").
    Devuelve las métricas: exactitud de facultad, de carrera, acierto entre las
    tres sugerencias y cobertura.
    """
    motor = MotorInferencia()
    n, ok_fac, ok_car, ok_top3, con_respuesta = len(casos), 0, 0, 0, 0
    for c in casos:
        h, _ = motor.inferir({f"p{i}": c.get(f"p{i}") for i in range(1, 21)})
        facultad = "indefinido" if h.obtener("perfil") == "indefinido" else h.obtener("facultad")
        opciones = [o["clave"] for o in h.obtener("recomendacion", []) if o["tipo"] == "carrera"]
        esperada = c["carrera_esperada"]
        acierta = (opciones[:1] == [esperada]) or (esperada == "indefinido" and facultad == "indefinido")
        ok_fac += facultad == c["facultad_esperada"]
        ok_car += acierta
        ok_top3 += acierta or esperada in opciones
        con_respuesta += bool(opciones) or facultad == "indefinido"
    return {"casos": n,
            "exactitud_facultad": round(100 * ok_fac / n, 1),
            "exactitud_carrera": round(100 * ok_car / n, 1),
            "acierto_top3": round(100 * ok_top3 / n, 1),
            "cobertura": round(100 * con_respuesta / n, 1)}
# =============================================================================
# VERIFICACIÓN DE LA BASE DE CONOCIMIENTO (sección 4.3 del informe)
# =============================================================================
def verificar(n_simulaciones=5000):
    """Revisa redundancias, conflictos, circularidad y reglas sin salida."""
    import random
    ids = [r["id"] for r in REGLAS]
    print("IDs duplicados:", sorted({i for i in ids if ids.count(i) > 1}) or "ninguno")
    print("Reglas sin fuente:", [r["id"] for r in REGLAS if not r["fuente"].strip()] or "ninguna")

    redundantes, conflictos = [], []
    for i, a in enumerate(REGLAS):
        for b in REGLAS[i + 1:]:
            if a["condiciones"] == b["condiciones"]:
                if a["acciones"] == b["acciones"]:
                    redundantes.append((a["id"], b["id"]))
                else:
                    sa = {k: v for x in a["acciones"] if "set" in x for k, v in x["set"].items()}
                    sb = {k: v for x in b["acciones"] if "set" in x for k, v in x["set"].items()}
                    if any(k in sb and sa[k] != sb[k] for k in sa):
                        conflictos.append((a["id"], b["id"]))
    print("Reglas redundantes:", redundantes or "ninguna")
    print("Reglas en conflicto:", conflictos or "ninguna")

    SALIDAS_PROCEDIMIENTOS = {"elegir_area_1": {"area_1", "empate_areas"}, "elegir_area_2": {"area_2", "area_3"},
                              "desempatar_por_aptitud": {"area_1", "empate_persiste"},
                              "reemplazar_area_D": {"area_1", "area_2", "aviso_D"}}

    def usadas(r):
        v = set()
        for c in r["condiciones"]:
            v |= set(c["contar"]) if isinstance(c, dict) else set(c[0].split("+"))
        return v

    def producidas(r):
        v = set()
        for a in r["acciones"]:
            if "set" in a:
                v |= set(a["set"])
            elif "sum" in a:
                v.add(a["sum"]["destino"])
            elif "add" in a:
                v |= set(a["add"])
            elif "funcion" in a:
                v |= SALIDAS_PROCEDIMIENTOS.get(a["funcion"], set())
        return v
    print("Reglas que modifican su propia condición:",
          [r["id"] for r in REGLAS if usadas(r) & producidas(r)] or "ninguna",
          "(no generan ciclos: cada regla se dispara una sola vez)")

    random.seed(42)
    motor, disparadas, maximo = MotorInferencia(), set(), 0
    for _ in range(n_simulaciones):
        resp = {f"p{i}": random.choice([0, 1, 2]) for i in range(1, 21)}
        for entrada in (resp, {k: v for k, v in resp.items() if int(k[1:]) <= 14}, {}):
            _, traza = motor.inferir(entrada)
            disparadas |= {t["id"] for t in traza}
            maximo = max(maximo, len(traza))
    print(f"Simulación con {n_simulaciones} perfiles aleatorios:")
    print(f"  Reglas disparadas al menos una vez: {len(disparadas)} de {len(REGLAS)}")
    print("  Reglas sin salida (nunca se dispararon):", [i for i in ids if i not in disparadas] or "ninguna")
    print(f"  Máximo de reglas disparadas en un caso: {maximo} (el motor siempre terminó)")
    # =============================================================================
# EJECUCIÓN DIRECTA:  py motordeinferencia.py
# Lee casos_prueba.csv, ejecuta cada caso y muestra los resultados de la sección 4.4.
# =============================================================================
if __name__ == "__main__":
    import csv

    with open("casos_prueba.csv", encoding="utf-8-sig") as f:
        texto = f.read()
    separador = ";" if texto.splitlines()[0].count(";") > texto.splitlines()[0].count(",") else ","
    casos = list(csv.DictReader(texto.splitlines(), delimiter=separador))

    motor = MotorInferencia()
    filas, matriz, reglas_total, consistentes = [], {}, 0, 0
    for c in casos:
        resp = {}
        for i in range(1, 21):
            valor = (c.get(f"p{i}") or "").strip()
            if valor != "":
                resp[f"p{i}"] = int(valor)
        h, traza = motor.inferir(resp)
        h2, _ = motor.inferir(resp)                      # segunda ejecución: consistencia
        consistentes += h.obtener("recomendacion") == h2.obtener("recomendacion")
        facultad = "indefinido" if h.obtener("perfil") == "indefinido" else h.obtener("facultad")
        opciones = [o["clave"] for o in h.obtener("recomendacion", []) if o["tipo"] == "carrera"]
        esperada, fac_esp = c["carrera_esperada"].strip(), c["facultad_esperada"].strip()
        primera = opciones[0] if opciones else "ninguna"
        ok1 = primera == esperada or (esperada == "indefinido" and facultad == "indefinido")
        ok3 = ok1 or esperada in opciones
        matriz[(fac_esp, facultad)] = matriz.get((fac_esp, facultad), 0) + 1
        reglas_total += len(traza)
        filas.append({"id": c["id"], "facultad_esperada": fac_esp, "facultad_sistema": facultad,
                      "carrera_esperada": esperada, "sugerencias_sistema": " | ".join(opciones) or "ninguna",
                      "coincide_1ra": "Sí" if ok1 else "No", "entre_las_3": "Sí" if ok3 else "No",
                      "reglas_disparadas": len(traza), "avisos": " | ".join(h.obtener("avisos", []))})

    print(f"{'ID':<5} {'Esperada':<24} {'1.a sugerencia':<24} {'1.a':<4} {'Top3':<5} Reglas")
    for f in filas:
        primera = f["sugerencias_sistema"].split(" | ")[0]
        print(f"{f['id']:<5} {f['carrera_esperada']:<24} {primera:<24} {f['coincide_1ra']:<4} {f['entre_las_3']:<5} {f['reglas_disparadas']}")

    n = len(filas)
    print("\nMÉTRICAS")
    for nombre, valor in validar(casos).items():
        print(f"  {nombre}: {valor}")
    print(f"  consistencia: {round(100 * consistentes / n, 1)}")
    print(f"  reglas_disparadas_promedio: {round(reglas_total / n, 1)}")

    etiquetas = ["Ingeniería", "Humanidades y Derecho", "Medicina", "Ciencias Empresariales", "indefinido"]
    print("\nMATRIZ DE CONFUSIÓN (filas = esperada, columnas = sistema)")
    print(" " * 24 + "".join(f"{e[:12]:>14}" for e in etiquetas))
    for a in etiquetas:
        print(f"{a:<24}" + "".join(f"{matriz.get((a, b), 0):>14}" for b in etiquetas))

    with open("resultados.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()), delimiter=separador)
        w.writeheader()
        w.writerows(filas)
    print("\nDetalle guardado en resultados.csv (ábrelo con Excel)")