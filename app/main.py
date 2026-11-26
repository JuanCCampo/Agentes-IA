"""API + dashboard de Veedor IA. Arranca: uvicorn app.main:app --reload"""
import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from . import bus, db, llm
from .agentes import Orquestador
from .config import BASE_DIR, FUENTE, MODELO, USAR_IA

orq = Orquestador()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.conn()
    bus.iniciar(asyncio.get_running_loop())
    orq.iniciar()
    yield
    await orq.detener()


app = FastAPI(title="Veedor IA", version="1.0", lifespan=lifespan)


@app.get("/")
def inicio():
    return FileResponse(BASE_DIR / "frontend" / "index.html")


# ------------------------------------------------------------------ Agentes
@app.get("/api/agentes")
def agentes():
    return [a.info() for a in orq.agentes.values()]


@app.post("/api/agentes/{nombre}/{accion}")
def controlar(nombre: str, accion: str):
    a = orq.agentes.get(nombre)
    if not a:
        raise HTTPException(404, "Agente no existe")
    if accion == "pausar":
        a.pausado = True
    elif accion == "reanudar":
        a.pausado = False
    elif accion == "reiniciar":
        a.pausado = False
        orq.reiniciar(nombre)
    else:
        raise HTTPException(400, "Acción inválida")
    bus.publicar("usuario", "control", f"{accion} → {nombre}")
    return a.info()


# ------------------------------------------------------------------ Datos
@app.get("/api/resumen")
def resumen():
    s = db.q1("""SELECT COUNT(*) total, COALESCE(SUM(estado_analisis='analizado'),0) analizados,
                        COALESCE(SUM(nivel='alto'),0) altos, COALESCE(SUM(nivel='medio'),0) medios,
                        COALESCE(SUM(nivel='bajo'),0) bajos, COALESCE(SUM(valor),0) valor,
                        COALESCE(SUM(CASE WHEN nivel='alto' THEN valor END),0) valor_alto
                 FROM contratos""")
    s["hallazgos"] = db.q1("SELECT COUNT(*) n FROM hallazgos")["n"]
    s["alertas"] = db.q1("SELECT COUNT(*) n FROM alertas")["n"]
    s["ia"] = USAR_IA
    s["modelo"] = MODELO if USAR_IA else None
    s["fuente"] = orq.agentes["recolector"].fuente
    s["entidades"] = db.q("""SELECT entidad, COUNT(*) n, ROUND(AVG(puntaje)) prom, SUM(nivel='alto') altos
                             FROM contratos WHERE puntaje IS NOT NULL GROUP BY entidad
                             ORDER BY prom DESC LIMIT 6""")
    return s


@app.get("/api/contratos")
def contratos(nivel: str | None = None, q: str | None = None, limite: int = 100):
    sql, p = "SELECT * FROM contratos WHERE 1=1", []
    if nivel:
        sql += " AND nivel=?"; p.append(nivel)
    if q:
        sql += " AND (entidad LIKE ? OR proveedor LIKE ? OR objeto LIKE ? OR id LIKE ?)"
        p += [f"%{q}%"] * 4
    sql += " ORDER BY COALESCE(puntaje,-1) DESC, fecha_firma DESC LIMIT ?"
    p.append(min(limite, 500))
    return db.q(sql, p)


@app.get("/api/contratos/{cid}")
def contrato(cid: str):
    c = db.q1("SELECT * FROM contratos WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "No encontrado")
    c["banderas"] = json.loads(c["banderas"] or "[]")
    c["otros_del_proveedor"] = db.q("""SELECT id, entidad, objeto, valor, puntaje, fecha_firma FROM contratos
                                       WHERE doc_proveedor=? AND id<>? ORDER BY fecha_firma DESC LIMIT 10""",
                                    (c["doc_proveedor"], cid))
    return c


@app.get("/api/hallazgos")
def hallazgos():
    filas = db.q("SELECT * FROM hallazgos ORDER BY puntaje DESC, id DESC LIMIT 50")
    for f in filas:
        f["contratos"] = json.loads(f["contratos"])
    return filas


@app.get("/api/alertas")
def alertas(limite: int = 30):
    return db.q("SELECT * FROM alertas ORDER BY id DESC LIMIT ?", (limite,))


@app.get("/api/boletines")
def boletines():
    return db.q("SELECT * FROM boletines ORDER BY id DESC LIMIT 10")


@app.get("/api/eventos")
def eventos(limite: int = 60):
    return db.q("SELECT * FROM eventos ORDER BY id DESC LIMIT ?", (limite,))


@app.get("/api/stream")
async def stream(request: Request):
    """Server-Sent Events: el dashboard ve en vivo lo que hacen los agentes."""
    cola = bus.suscribir()

    async def gen():
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():  # suelta rápido las pestañas cerradas
                try:
                    ev = await asyncio.wait_for(cola.get(), timeout=5)
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            bus.desuscribir(cola)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ Pregúntale al Veedor
class Pregunta(BaseModel):
    pregunta: str


SIS_CHAT = """Eres "Pregúntale al Veedor", el asistente ciudadano de Veedor IA. Respondes
preguntas sobre los contratos públicos que la plataforma vigila, usando SOLO los datos
del contexto. Si la respuesta no está en los datos, dilo. Sé breve (máx. 120 palabras),
cita IDs de contrato cuando ayuden y recuerda que un riesgo alto no es prueba de corrupción."""


@app.post("/api/preguntar")
def preguntar(p: Pregunta):
    if not p.pregunta.strip():
        raise HTTPException(400, "Pregunta vacía")
    contexto = {
        "resumen": {k: v for k, v in resumen().items() if k != "entidades"},
        "entidades": db.q("""SELECT entidad, COUNT(*) n, ROUND(AVG(puntaje)) prom, SUM(valor) valor
                             FROM contratos GROUP BY entidad ORDER BY n DESC LIMIT 15"""),
        "contratos_mayor_riesgo": db.q("""SELECT id, entidad, proveedor, objeto, modalidad, valor, puntaje, resumen
                                          FROM contratos WHERE puntaje IS NOT NULL
                                          ORDER BY puntaje DESC LIMIT 15"""),
        "hallazgos": db.q("SELECT titulo, detalle FROM hallazgos ORDER BY puntaje DESC LIMIT 8"),
        "proveedores_top": db.q("""SELECT proveedor, COUNT(*) n, SUM(valor) valor FROM contratos
                                   GROUP BY doc_proveedor ORDER BY valor DESC LIMIT 10"""),
    }
    try:
        r = llm.pedir_json(SIS_CHAT, "Contexto:\n" + json.dumps(contexto, ensure_ascii=False) +
                           f"\n\nPregunta del ciudadano: {p.pregunta}",
                           llm.objeto({"respuesta": {"type": "string"}}), esfuerzo="low")
        respuesta = r["respuesta"]
    except llm.IANoDisponible as e:
        respuesta = (f"El asistente necesita una ANTHROPIC_API_KEY para responder preguntas libres ({e}). "
                     f"Mientras tanto: hay {contexto['resumen']['total']} contratos vigilados y "
                     f"{contexto['resumen']['altos']} con riesgo alto.")
    bus.publicar("asistente", "pregunta", f"❓ {p.pregunta[:80]}")
    return {"respuesta": respuesta}
