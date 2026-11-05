# Registro de capacidades de las herramientas de DevKit para descubrimiento por agentes.
from __future__ import annotations

from typing import Any

VERSION_CONTRATO = 1

CAPACIDADES: list[dict[str, Any]] = [
    {
        "name": "backup",
        "version": "1.0",
        "requires_workspace": False,
        "requires_authorization": True,
        "supports_dry_run": False,
        "supports_manifest": True,
        "supports_recovery": False,
        "read_permissions": ["filesystem:read"],
        "write_permissions": ["filesystem:write", "backup:create"],
        "inputs": {
            "crear": {"origen": "list[Path]", "destino": "Path?", "etiqueta": "str", "clave": "Path?", "sin_cifrado": "bool"},
            "verificar": {"carpeta": "Path", "clave": "Path?"},
            "restaurar": {"carpeta": "Path", "destino": "Path", "clave": "Path?", "forzar": "bool"},
            "listar": {"destino": "Path?"},
        },
        "outputs": {"estado": "str", "codigo": "int", "raiz": "str", "indice": "str", "total": "int"},
        "accion": "backup cifrado con AES-256 y verificacion de restauracion",
    },
    {
        "name": "trim",
        "version": "1.0",
        "requires_workspace": True,
        "requires_authorization": True,
        "supports_dry_run": True,
        "supports_manifest": True,
        "supports_recovery": True,
        "read_permissions": ["filesystem:read"],
        "write_permissions": ["filesystem:write", "trash:move"],
        "inputs": {
            "escanear": {"raiz": "Path", "incluir_venv": "bool", "edad_dias": "int"},
            "aplicar": {"raiz": "Path", "incluir_venv": "bool", "edad_dias": "int", "forzar": "bool", "plan": "Path?"},
        },
        "outputs": {"estado": "str", "codigo": "int", "raiz": "str", "total_movidos": "int", "total_bytes": "int", "movidos": "list", "fallidos": "list", "plan_persistente": "str"},
        "accion": "limpieza de caches y artefactos con plan previo y papelera de Windows",
    },
    {
        "name": "dedupe",
        "version": "1.0",
        "requires_workspace": True,
        "requires_authorization": True,
        "supports_dry_run": True,
        "supports_manifest": True,
        "supports_recovery": True,
        "read_permissions": ["filesystem:read"],
        "write_permissions": ["filesystem:write", "trash:move"],
        "inputs": {
            "escanear": {"raiz": "Path", "edad_dias": "int", "no_ignorar_onedrive": "bool"},
            "aplicar": {"raiz": "Path", "edad_dias": "int", "no_ignorar_onedrive": "bool", "forzar": "bool", "plan": "Path?"},
        },
        "outputs": {"estado": "str", "codigo": "int", "raiz": "str", "total_movidos": "int", "total_bytes": "int", "movidos": "list", "fallidos": "list", "plan_persistente": "str"},
        "accion": "deteccion de duplicados exactos con BLAKE3, plan previo y papelera de Windows",
    },
    {
        "name": "organize",
        "version": "1.0",
        "requires_workspace": True,
        "requires_authorization": True,
        "supports_dry_run": True,
        "supports_manifest": True,
        "supports_recovery": True,
        "read_permissions": ["filesystem:read"],
        "write_permissions": ["filesystem:write"],
        "inputs": {
            "plan": {"raiz": "Path", "destino": "Path?", "no_ignorar_onedrive": "bool"},
            "aplicar": {"raiz": "Path", "destino": "Path?", "todos": "bool", "por_archivo": "bool", "no_ignorar_onedrive": "bool", "plan": "Path?"},
        },
        "outputs": {"estado": "str", "codigo": "int", "raiz": "str", "destino": "str", "total_movidos": "int", "total_bytes": "int", "movidos": "list", "fallidos": "list", "plan_persistente": "str"},
        "accion": "clasificacion por extension, firma binaria y año con plan previo",
    },
    {
        "name": "idea",
        "version": "1.0",
        "requires_workspace": True,
        "requires_authorization": True,
        "supports_dry_run": False,
        "supports_manifest": False,
        "supports_recovery": False,
        "read_permissions": ["filesystem:read"],
        "write_permissions": ["filesystem:write"],
        "inputs": {
            "crear": {"raiz": "Path", "titulo": "str", "cuerpo": "str", "etiqueta": "list[str]", "estado": "str"},
            "revisar": {"raiz": "Path"},
            "listar": {"raiz": "Path", "estado": "str?"},
        },
        "outputs": {"estado": "str", "codigo": "int", "raiz": "str", "total": "int"},
        "accion": "notas Markdown con frontmatter validado y revision de enlaces",
    },
    {
        "name": "index",
        "version": "1.0",
        "requires_workspace": True,
        "requires_authorization": True,
        "supports_dry_run": False,
        "supports_manifest": False,
        "supports_recovery": False,
        "read_permissions": ["filesystem:read"],
        "write_permissions": ["filesystem:write"],
        "inputs": {
            "construir": {"raiz": "Path"},
            "buscar": {"termino": "str", "raiz": "Path?", "estado": "str?", "limite": "int"},
            "actualizar": {"raiz": "Path"},
            "exportar": {"salida": "Path", "raiz": "Path?"},
        },
        "outputs": {"estado": "str", "codigo": "int", "raiz": "str", "indice": "str", "total": "int", "resultados": "list"},
        "accion": "indice SQLite con FTS5 sobre notas Markdown",
    },
    {
        "name": "ocr",
        "version": "1.0",
        "requires_workspace": True,
        "requires_authorization": False,
        "supports_dry_run": False,
        "supports_manifest": False,
        "supports_recovery": False,
        "read_permissions": ["filesystem:read"],
        "write_permissions": ["filesystem:write"],
        "inputs": {
            "escanear": {"raiz": "Path", "idioma": "str", "no_ignorar_onedrive": "bool"},
            "exportar": {"raiz": "Path", "destino": "Path?", "idioma": "str"},
        },
        "outputs": {"estado": "str", "codigo": "int", "raiz": "str", "total": "int"},
        "accion": "OCR en solo lectura con Tesseract y PyMuPDF",
    },
    {
        "name": "nice",
        "version": "1.0",
        "requires_workspace": False,
        "requires_authorization": False,
        "supports_dry_run": False,
        "supports_manifest": False,
        "supports_recovery": False,
        "read_permissions": ["process:execute"],
        "write_permissions": [],
        "inputs": {
            "ejecutar": {"comando": "list[str]", "prioridad": "str", "tiempo": "float", "memoria_mb": "int?"},
        },
        "outputs": {"estado": "str", "codigo": "int", "memoria_pico": "int", "duracion_ms": "float"},
        "accion": "ejecuta hijos con prioridad baja y registro de memoria",
    },
    {
        "name": "doctor",
        "version": "1.0",
        "requires_workspace": False,
        "requires_authorization": False,
        "supports_dry_run": False,
        "supports_manifest": False,
        "supports_recovery": False,
        "read_permissions": ["system:read"],
        "write_permissions": [],
        "inputs": {},
        "outputs": {"estado": "str", "codigo": "int", "comprobaciones": "list"},
        "accion": "diagnostico del equipo y del entorno",
    },
    {
        "name": "health",
        "version": "1.0",
        "requires_workspace": False,
        "requires_authorization": False,
        "supports_dry_run": False,
        "supports_manifest": False,
        "supports_recovery": False,
        "read_permissions": ["system:read"],
        "write_permissions": [],
        "inputs": {"formato": "str"},
        "outputs": {"estado": "str", "codigo": "int", "bloques": "list"},
        "accion": "informe de salud del sistema",
    },
    {
        "name": "backup",
        "version": "1.0",
        "requires_workspace": False,
        "requires_authorization": True,
        "supports_dry_run": False,
        "supports_manifest": True,
        "supports_recovery": False,
        "read_permissions": ["filesystem:read"],
        "write_permissions": ["filesystem:write", "backup:create"],
        "inputs": {
            "crear": {"origen": "list[Path]", "destino": "Path?", "etiqueta": "str", "clave": "Path?", "sin_cifrado": "bool"},
            "verificar": {"carpeta": "Path", "clave": "Path?"},
            "restaurar": {"carpeta": "Path", "destino": "Path", "clave": "Path?", "forzar": "bool"},
            "listar": {"destino": "Path?"},
        },
        "outputs": {"estado": "str", "codigo": "int", "raiz": "str", "indice": "str", "total": "int"},
        "accion": "respaldo cifrado con AES-256 y verificacion de restauracion",
    },
]


def listar_capacidades() -> list[dict[str, Any]]:
    # Devuelve una copia superficial del registro para que el CLI no lo mute.
    return [dict(capacidad) for capacidad in CAPACIDADES]


def obtener_capacidad(nombre: str) -> dict[str, Any] | None:
    # Busca una herramienta por nombre en el registro.
    for capacidad in CAPACIDADES:
        if capacidad["name"] == nombre:
            return dict(capacidad)
    return None

