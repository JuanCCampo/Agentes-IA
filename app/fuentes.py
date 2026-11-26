"""Fuentes de datos: SECOP II real (datos.gov.co, API Socrata) y un generador demo."""
import hashlib
import random
from datetime import date, datetime, timedelta

import httpx2 as httpx

from .config import SECOP_APP_TOKEN, SECOP_DEPARTAMENTO, SECOP_URL


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _fecha(v) -> str | None:
    return v[:10] if isinstance(v, str) and len(v) >= 10 else None


def normalizar_secop(r: dict) -> dict:
    """Convierte una fila de SECOP II al formato interno."""
    url = r.get("urlproceso")
    if isinstance(url, dict):
        url = url.get("url")
    return {
        "id": r.get("id_contrato") or r.get("referencia_del_contrato"),
        "entidad": r.get("nombre_entidad"),
        "nit_entidad": r.get("nit_entidad"),
        "departamento": r.get("departamento"),
        "ciudad": r.get("ciudad"),
        "objeto": r.get("objeto_del_contrato") or r.get("descripcion_del_proceso"),
        "tipo": r.get("tipo_de_contrato"),
        "modalidad": r.get("modalidad_de_contratacion"),
        "estado": r.get("estado_contrato"),
        "proveedor": r.get("proveedor_adjudicado"),
        "doc_proveedor": r.get("documento_proveedor"),
        "valor": _num(r.get("valor_del_contrato")),
        "fecha_firma": _fecha(r.get("fecha_de_firma")),
        "fecha_inicio": _fecha(r.get("fecha_de_inicio_del_contrato")),
        "fecha_fin": _fecha(r.get("fecha_de_fin_del_contrato")),
        "url": url,
        "fuente": "secop",
    }


def obtener_secop(limite: int = 50, desde: str | None = None) -> list[dict]:
    """Trae los contratos más recientes del departamento configurado."""
    filtros = [f"departamento='{SECOP_DEPARTAMENTO}'"] if SECOP_DEPARTAMENTO else []
    if desde:
        filtros.append(f"fecha_de_firma >= '{desde}T00:00:00'")
    params = {"$limit": limite, "$order": "fecha_de_firma DESC"}
    if filtros:
        params["$where"] = " AND ".join(filtros)
    headers = {"X-App-Token": SECOP_APP_TOKEN} if SECOP_APP_TOKEN else {}
    resp = httpx.get(SECOP_URL, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return [c for c in (normalizar_secop(r) for r in resp.json()) if c["id"]]


# ---------------------------------------------------------------- Generador demo
ENTIDADES = [
    ("ALCALDÍA DISTRITAL DE CARTAGENA DE INDIAS", "890480184", "Cartagena"),
    ("GOBERNACIÓN DE BOLÍVAR", "890480059", "Cartagena"),
    ("DATT - DEPARTAMENTO ADMINISTRATIVO DE TRÁNSITO", "806013999", "Cartagena"),
    ("ESE HOSPITAL LOCAL CARTAGENA DE INDIAS", "806010305", "Cartagena"),
    ("ALCALDÍA MUNICIPAL DE TURBACO", "890480254", "Turbaco"),
    ("ALCALDÍA MUNICIPAL DE MAGANGUÉ", "890480203", "Magangué"),
    ("DISTRISEGURIDAD", "806016254", "Cartagena"),
]
PROVEEDORES = [
    ("CONSTRUCCIONES DEL CARIBE S.A.S.", "901234567"),
    ("SOLUCIONES INTEGRALES BOLÍVAR S.A.S.", "900876543"),
    ("INVERSIONES LA HEROICA LTDA", "806054321"),
    ("TECNOLOGÍA Y SERVICIOS COSTA S.A.S.", "901112223"),
    ("FUNDACIÓN SOCIAL MANOS UNIDAS", "900998877"),
    ("MARÍA FERNANDA PÉREZ GÓMEZ", "1047456789"),
    ("CARLOS ANDRÉS RUIZ MERCADO", "73189456"),
    ("SUMINISTROS Y DOTACIONES DEL NORTE S.A.S.", "901445566"),
    ("CONSORCIO VÍAS CARTAGENA 2026", "901777888"),
]
OBJETOS = [
    ("Prestación de servicios profesionales como abogado de apoyo a la gestión jurídica", "Prestación de servicios", (4e6, 9e6)),
    ("Prestación de servicios de apoyo a la gestión en actividades operativas", "Prestación de servicios", (2e6, 4e6)),
    ("Mantenimiento y rehabilitación de la malla vial urbana del barrio Olaya Herrera", "Obra", (3e8, 2.5e9)),
    ("Suministro de refrigerios y alimentación para eventos institucionales", "Suministro", (2e7, 1.2e8)),
    ("Adquisición de equipos de cómputo para instituciones educativas oficiales", "Compraventa", (8e7, 6e8)),
    ("Suministro de kits escolares para estudiantes de la zona rural", "Suministro", (5e7, 4e8)),
    ("Logística para la realización de eventos culturales y festividades", "Prestación de servicios", (1e8, 9e8)),
    ("Apoyo a la gestión", "Prestación de servicios", (5e6, 3e7)),
    ("Interventoría técnica, administrativa y financiera de obra de canalización", "Interventoría", (1e8, 5e8)),
]
MODALIDADES = ["Contratación directa", "Contratación régimen especial", "Mínima cuantía",
               "Selección abreviada de menor cuantía", "Licitación pública"]


def generar_demo(n: int = 8) -> list[dict]:
    """Contratos sintéticos parecidos a SECOP. Incluye a propósito patrones sospechosos."""
    hoy = date.today()
    salida = []
    for _ in range(n):
        ent, nit, ciudad = random.choice(ENTIDADES)
        prov, doc = random.choice(PROVEEDORES)
        objeto, tipo, (vmin, vmax) = random.choice(OBJETOS)
        modalidad = random.choices(MODALIDADES, weights=[45, 10, 20, 15, 10])[0]
        valor = round(random.uniform(vmin, vmax), -3)
        firma = hoy - timedelta(days=random.randint(0, 20))
        dur = random.choice([3, 10, 30, 60, 90, 120, 180, 330])
        escenario = random.random()
        if escenario < 0.12:  # fraccionamiento: varios contratos casi iguales, mismo proveedor
            prov, doc = PROVEEDORES[1]
            ent, nit, ciudad = ENTIDADES[0]
            objeto, tipo = OBJETOS[3][0], OBJETOS[3][1]
            modalidad, valor = "Mínima cuantía", round(random.uniform(9.0e7, 9.9e7), -3)
        elif escenario < 0.2:  # obra grande por contratación directa con plazo exprés
            objeto, tipo = OBJETOS[2][0], OBJETOS[2][1]
            modalidad, valor, dur = "Contratación directa", round(random.uniform(1.5e9, 4e9), -3), 5
        raw = f"{ent}{prov}{objeto}{valor}{datetime.now().timestamp()}{random.random()}"
        cid = "CO1.PCCNTR." + str(int(hashlib.md5(raw.encode()).hexdigest()[:7], 16))
        salida.append({
            "id": cid, "entidad": ent, "nit_entidad": nit, "departamento": "Bolívar",
            "ciudad": ciudad, "objeto": objeto, "tipo": tipo, "modalidad": modalidad,
            "estado": random.choice(["En ejecución", "Firmado", "Activo"]),
            "proveedor": prov, "doc_proveedor": doc, "valor": valor,
            "fecha_firma": firma.isoformat(), "fecha_inicio": firma.isoformat(),
            "fecha_fin": (firma + timedelta(days=dur)).isoformat(),
            "url": None, "fuente": "demo",
        })
    return salida
