"""
SISTEMA EXPERTO DE ORIENTACIÓN VOCACIONAL - USAT
================================================
Servidor web (Flask). Conecta la interfaz (templates/index.html) con el motor
de inferencia (motordeinferencia.py) y la base de conocimiento
(basedeconocimiento.py).

Ejecutar:  py app.py      → se abre http://127.0.0.1:5000
"""
import threading
import webbrowser

from flask import Flask, jsonify, render_template, request

from basedeconocimiento import AREAS, BLOQUES, CARRERAS, ESCALA, ETAPA1, contar_reglas
from motordeinferencia import MotorInferencia, por_que_etapa2, razones

app = Flask(__name__)
app.json.sort_keys = False          # respeta el orden Sí / A veces / No
motor = MotorInferencia()
PUERTO = 5000


def leer_respuestas(desde, hasta):
    """Toma del pedido las respuestas p{desde}..p{hasta} con valor 0, 1 o 2."""
    datos = (request.get_json(silent=True) or {}).get("respuestas", {})
    respuestas = {}
    for i in range(desde, hasta + 1):
        valor = datos.get(f"p{i}")
        if valor in (0, 1, 2, "0", "1", "2"):
            respuestas[f"p{i}"] = int(valor)
    return respuestas


def resultado_final(h, traza):
    """Arma la respuesta que ve el estudiante al final."""
    opciones = []
    for opcion in h.obtener("recomendacion", []):
        opcion = dict(opcion)
        opcion["razones"] = razones(opcion, traza, h)
        opciones.append(opcion)
    return {
        "fase": "final",
        "perfil": h.obtener("perfil", "normal"),
        "facultad": h.obtener("facultad"),
        "opciones": opciones,
        "areas": [{"letra": a, "nombre": AREAS[a]["nombre"], "puntaje": h.obtener(f"puntaje_{a}", 0),
                   "nivel": h.obtener(f"nivel_{a}", "bajo")} for a in AREAS],
        "avisos": h.obtener("avisos", []),
        "como": [{"id": t["id"], "grupo": t["grupo"], "si": t["si"], "entonces": t["entonces"],
                  "fuente": t["fuente"]} for t in traza],
        "reglas_disparadas": len(traza),
    }


# ---------------------------------------------------------------------------
# RUTAS
# ---------------------------------------------------------------------------
@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/api/preguntas")
def api_preguntas():
    """Preguntas de la etapa 1 y escala de respuesta."""
    return jsonify({"etapa1": ETAPA1, "escala": ESCALA})


@app.route("/api/etapa1", methods=["POST"])
def api_etapa1():
    """Recibe p1–p14, infiere la facultad y devuelve las 6 preguntas de la etapa 2."""
    h, traza = motor.inferir(leer_respuestas(1, 14))
    if h.existe("error_entrada"):
        return jsonify({"error": h.obtener("error_entrada")}), 400
    if h.obtener("perfil") == "indefinido":
        return jsonify(resultado_final(h, traza))
    facultad = h.obtener("facultad")
    return jsonify({"fase": "etapa2", "facultad": facultad,
                    "por_que": por_que_etapa2(traza, h) + " Estas preguntas ayudan a elegir la carrera dentro de esa facultad.",
                    "preguntas": BLOQUES[facultad]["preguntas"]})


@app.route("/api/evaluar", methods=["POST"])
def api_evaluar():
    """Recibe p1–p20 y devuelve las sugerencias con su explicación."""
    h, traza = motor.inferir(leer_respuestas(1, 20))
    if h.existe("error_entrada") or h.obtener("esperando_etapa2"):
        return jsonify({"error": "Faltan respuestas. Responde todas las preguntas."}), 400
    return jsonify(resultado_final(h, traza))


@app.route("/api/reglas")
def api_reglas():
    """Resumen de la base de conocimiento, para revisarla desde el navegador."""
    grupos, total = contar_reglas()
    return jsonify({"total": total, "grupos": grupos})


# ---------------------------------------------------------------------------
# INICIO
# ---------------------------------------------------------------------------
def banner():
    grupos, total = contar_reglas()
    linea = "=" * 70
    print(linea)
    print("  SISTEMA EXPERTO - ORIENTACION VOCACIONAL USAT")
    print(linea)
    print(f"  Base de conocimiento: {total} reglas cargadas")
    for grupo, n in grupos.items():
        print(f"    - {grupo}: {n} reglas")
    n_preguntas = len(ETAPA1) + sum(len(b["preguntas"]) for b in BLOQUES.values())
    print(f"  Preguntas: {n_preguntas} en el banco (cada estudiante responde 20)")
    print(f"  Carreras USAT: {len(CARRERAS)}")
    print(linea)
    print(f"  Servidor iniciado en: http://127.0.0.1:{PUERTO}")
    print("  Para detenerlo: Ctrl + C")
    print(linea)


if __name__ == "__main__":
    banner()
    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PUERTO}")).start()
    app.run(host="127.0.0.1", port=PUERTO, debug=False)