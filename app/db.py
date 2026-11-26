"""Capa de persistencia (SQLite, sin ORM para que sea fácil de entender)."""
import json
import sqlite3
import threading
from datetime import datetime, timezone

from .config import DB_PATH

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

ESQUEMA = """
CREATE TABLE IF NOT EXISTS contratos (
    id TEXT PRIMARY KEY,
    entidad TEXT, nit_entidad TEXT, departamento TEXT, ciudad TEXT,
    objeto TEXT, tipo TEXT, modalidad TEXT, estado TEXT,
    proveedor TEXT, doc_proveedor TEXT,
    valor REAL, fecha_firma TEXT, fecha_inicio TEXT, fecha_fin TEXT,
    url TEXT, fuente TEXT,
    estado_analisis TEXT DEFAULT 'pendiente',   -- pendiente | analizado | error
    puntaje INTEGER, nivel TEXT, resumen TEXT, banderas TEXT,
    creado TEXT
);
CREATE INDEX IF NOT EXISTS ix_contratos_estado ON contratos(estado_analisis);
CREATE INDEX IF NOT EXISTS ix_contratos_prov ON contratos(doc_proveedor);

CREATE TABLE IF NOT EXISTS hallazgos (       -- patrones entre varios contratos (Investigador)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clave TEXT UNIQUE, tipo TEXT, titulo TEXT, detalle TEXT,
    contratos TEXT, puntaje INTEGER, creado TEXT
);

CREATE TABLE IF NOT EXISTS alertas (         -- mensajes ciudadanos (Redactor)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origen TEXT, ref TEXT, nivel TEXT, titulo TEXT, mensaje TEXT,
    publicada INTEGER DEFAULT 0, creado TEXT,
    UNIQUE(origen, ref)
);

CREATE TABLE IF NOT EXISTS boletines (
    id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT, contenido TEXT, creado TEXT
);

CREATE TABLE IF NOT EXISTS eventos (         -- bitácora de lo que hace cada agente
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agente TEXT, tipo TEXT, mensaje TEXT, datos TEXT, creado TEXT
);
"""


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(ESQUEMA)
    return _conn


def q(sql: str, params=()) -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, params).fetchall()]


def q1(sql: str, params=()) -> dict | None:
    filas = q(sql, params)
    return filas[0] if filas else None


def ex(sql: str, params=()) -> int:
    """Ejecuta una escritura. Devuelve el id insertado (INSERT) o filas afectadas (UPDATE/DELETE)."""
    with _lock:
        cur = conn().execute(sql, params)
        conn().commit()
        if sql.lstrip().upper().startswith("INSERT"):
            return cur.lastrowid if cur.rowcount > 0 else 0
        return cur.rowcount


def registrar_evento(agente: str, tipo: str, mensaje: str, datos: dict | None = None) -> dict:
    ev = {"agente": agente, "tipo": tipo, "mensaje": mensaje,
          "datos": json.dumps(datos or {}, ensure_ascii=False), "creado": ahora()}
    ev["id"] = ex("INSERT INTO eventos (agente,tipo,mensaje,datos,creado) VALUES (?,?,?,?,?)",
                  (ev["agente"], ev["tipo"], ev["mensaje"], ev["datos"], ev["creado"]))
    return ev
