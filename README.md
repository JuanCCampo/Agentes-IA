# 🔎 Veedor IA

**Agentes de IA que vigilan la contratación pública colombiana las 24 horas.**

En Colombia se firman miles de contratos públicos cada semana y todos quedan publicados en
SECOP II, pero ningún ciudadano alcanza a revisarlos. Veedor IA pone a trabajar un equipo
de agentes autónomos que, sin descanso, **recolectan** los contratos nuevos, los **auditan**,
**cruzan** la información entre ellos para encontrar patrones y **redactan** alertas en lenguaje
ciudadano. Todo se ve en tiempo real en un dashboard.

> ⚖️ Un puntaje de riesgo alto **no es una acusación**: es una señal para que la ciudadanía,
> la prensa o una veeduría revisen el contrato.

---

## El equipo de agentes

| Agente | Frecuencia* | Qué hace |
|---|---|---|
| 🛰️ **Recolector** | 60 s | Consulta la API de SECOP II (datos.gov.co) y guarda los contratos nuevos. Si SECOP falla 3 veces seguidas, cambia solo a la fuente demo para que la plataforma no se detenga. |
| 🧮 **Auditor** | 10 s | Analiza cada contrato pendiente en dos capas: **reglas** (contratación directa de alto valor, plazo exprés, valor justo bajo el umbral, objeto vago, proveedor recurrente…) y **Claude**, que confirma o descarta las banderas y explica el riesgo (0-100). |
| 🕵️ **Investigador** | 45 s | Cruza los contratos entre sí: **fraccionamiento** (mismo proveedor y entidad, varios contratos pequeños que juntos superan el umbral) y **concentración** (un proveedor con ≥40 % de lo contratado por una entidad). |
| ✍️ **Redactor** | 30 s | Convierte lo encontrado en **alertas ciudadanas** claras y publica un **boletín** periódico. |
| 🧭 **Supervisor** | 15 s | Vigila la salud del equipo: si un agente se cae o se cuelga, lo reinicia. |

\*Configurable con variables de entorno.

Además, **💬 Pregúntale al Veedor** es un chat donde cualquier persona pregunta en lenguaje natural
(«¿qué entidad tiene más contratos riesgosos?») y Claude responde con los datos recolectados.

## Arquitectura

```
                 ┌──────────── Orquestador (asyncio) ─────────────┐
 SECOP II API ──▶│ 🛰️ Recolector ─▶ SQLite ◀─ 🧮 Auditor ◀─▶ Claude │
 (datos.gov.co)  │                    ▲  ▲                         │
                 │   🕵️ Investigador ─┘  └─ ✍️ Redactor ◀─▶ Claude  │
                 │   🧭 Supervisor (reinicia agentes caídos)        │
                 └───────────────┬─────────────────────────────────┘
                                 │ bus de eventos
                     FastAPI ── REST + SSE (tiempo real) ──▶ Dashboard web
```

- **Backend:** Python 3.11+, FastAPI, SQLite (sin ORM).
- **IA:** API de Claude (SDK oficial `anthropic`) con *structured outputs* (respuestas JSON
  validadas contra un esquema) y *fallback* del lado del servidor si el modelo declina.
- **Tiempo real:** Server-Sent Events: el dashboard muestra cada acción de cada agente al instante.
- **Robustez:** cada agente es un bucle independiente con backoff exponencial ante errores; el
  Supervisor reinicia agentes muertos o colgados. Sin API key, el sistema sigue funcionando
  sólo con reglas.

```
veedor-ia/
├── app/
│   ├── main.py            # API REST, SSE y chat
│   ├── config.py          # configuración (variables de entorno / .env)
│   ├── db.py              # esquema y acceso a SQLite
│   ├── bus.py             # bus de eventos agentes → dashboard
│   ├── llm.py             # envoltorio de Claude
│   ├── fuentes.py         # cliente SECOP II + generador demo
│   └── agentes/
│       ├── __init__.py    # Orquestador
│       ├── base.py        # clase Agente (bucle, latido, backoff)
│       ├── recolector.py  auditor.py  investigador.py  redactor.py  supervisor.py
├── frontend/index.html    # dashboard (HTML + JS, sin build)
└── data/                  # base de datos SQLite (se crea sola)
```

## Cómo correrlo

```bash
python -m venv .venv
source .venv/bin/activate      # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # y pon tu ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

Abre <http://localhost:8000>.

- **Datos reales:** `VEEDOR_FUENTE=secop` (por defecto). Trae contratos de Bolívar; cambia
  `SECOP_DEPARTAMENTO` para otro departamento.
- **Demo para presentar:** `VEEDOR_FUENTE=demo` genera contratos sintéticos que incluyen a propósito
  casos sospechosos (fraccionamiento, obras por contratación directa con plazo exprés…).
  Para una demo más rápida, usa intervalos cortos:

```bash
VEEDOR_FUENTE=demo INT_RECOLECTOR=8 INT_AUDITOR=3 INT_REDACTOR=5 BOLETIN_CADA_MIN=2 uvicorn app.main:app
```

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/agentes` | Estado de cada agente |
| POST | `/api/agentes/{nombre}/{pausar\|reanudar\|reiniciar}` | Controlar un agente |
| GET | `/api/resumen` | KPIs generales |
| GET | `/api/contratos?nivel=&q=` | Contratos con su riesgo |
| GET | `/api/contratos/{id}` | Detalle, banderas y otros contratos del proveedor |
| GET | `/api/hallazgos` | Patrones entre contratos |
| GET | `/api/alertas` · `/api/boletines` · `/api/eventos` | Salidas del Redactor y bitácora |
| GET | `/api/stream` | Eventos en vivo (SSE) |
| POST | `/api/preguntar` | Chat «Pregúntale al Veedor» |

Documentación interactiva en `/docs`.

## Ideas para seguir creciendo

- Agente **Notificador**: enviar alertas por Telegram/WhatsApp/correo a quien siga una entidad.
- Más fuentes: SECOP I, procesos en curso, RUES (fecha de creación de la empresa proveedora: una
  empresa creada semanas antes de ganar un contrato es otra bandera clásica).
- Mapa por municipio y ranking de entidades.
- Desplegar en un servidor (Railway, Render o una VM) para que los agentes corran de verdad 24/7.
