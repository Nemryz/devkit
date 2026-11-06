# Registro de capacidades de las herramientas de DevKit para descubrimiento por agentes.
from __future__ import annotations

from typing import Any

VERSION_CONTRATO = 1

# Clasificacion de todos los comandos de nivel superior del CLI.
# capability: funcionalidad invocable por un agente.
# discovery: descubrimiento e introspeccion.
# administration: gestion del propio DevKit (reservado).
CLASIFICACION: dict[str, str] = {
    'backup': 'capability',
    'trim': 'capability',
    'dedupe': 'capability',
    'organize': 'capability',
    'idea': 'capability',
    'index': 'capability',
    'ocr': 'capability',
    'nice': 'capability',
    'buscar': 'capability',
    'doctor': 'capability',
    'health': 'capability',
    'capabilities': 'discovery',
    'describe': 'discovery',
    'schema': 'discovery',
}


CAPACIDADES: list[dict[str, Any]] = [
    {
        'name': 'backup',
        'clase': 'capability',
        'version': '1.0',
        'contrato_version': VERSION_CONTRATO,
        'requires_workspace': False,
        'requires_authorization': False,
        'supports_dry_run': False,
        'supports_manifest': True,
        'supports_recovery': False,
        'interactive': False,
        'read_permissions': ['filesystem:read'],
        'write_permissions': ['filesystem:write', 'backup:create'],
        'actions': {
            'crear': {'params': {'origen': 'list[Path]', 'destino': 'Path?', 'etiqueta': 'str', 'clave': 'Path?', 'sin_cifrado': 'bool'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'indice': 'str', 'total': 'int'}},
            'verificar': {'params': {'carpeta': 'Path', 'clave': 'Path?'}, 'outputs': {'estado': 'str', 'codigo': 'int'}},
            'restaurar': {'params': {'carpeta': 'Path', 'destino': 'Path', 'clave': 'Path?', 'forzar': 'bool'}, 'outputs': {'estado': 'str', 'codigo': 'int'}},
            'listar': {'params': {'destino': 'Path?'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'total': 'int'}},
        },
        'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'indice': 'str', 'total': 'int'},
        'accion': 'respaldo cifrado con AES-256 y verificacion de restauracion',
    },
    {
        'name': 'trim',
        'clase': 'capability',
        'version': '1.0',
        'contrato_version': VERSION_CONTRATO,
        'requires_workspace': True,
        'requires_authorization': True,
        'supports_dry_run': True,
        'supports_manifest': True,
        'supports_recovery': True,
        'interactive': False,
        'read_permissions': ['filesystem:read'],
        'write_permissions': ['filesystem:write', 'trash:move'],
        'actions': {
            'escanear': {'params': {'raiz': 'Path', 'incluir_venv': 'bool', 'edad_dias': 'int'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total': 'int', 'plan_persistente': 'str'}},
            'aplicar': {'params': {'raiz': 'Path', 'incluir_venv': 'bool', 'edad_dias': 'int', 'forzar': 'bool', 'plan': 'Path?', 'dry_run': 'bool'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total_movidos': 'int', 'total_bytes': 'int', 'movidos': 'list', 'fallidos': 'list', 'plan_persistente': 'str'}},
        },
        'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total_movidos': 'int', 'total_bytes': 'int', 'movidos': 'list', 'fallidos': 'list', 'plan_persistente': 'str'},
        'accion': 'limpieza de caches y artefactos con plan previo y papelera de Windows',
    },
    {
        'name': 'dedupe',
        'clase': 'capability',
        'version': '1.0',
        'contrato_version': VERSION_CONTRATO,
        'requires_workspace': True,
        'requires_authorization': True,
        'supports_dry_run': True,
        'supports_manifest': True,
        'supports_recovery': True,
        'interactive': False,
        'read_permissions': ['filesystem:read'],
        'write_permissions': ['filesystem:write', 'trash:move'],
        'actions': {
            'escanear': {'params': {'raiz': 'Path', 'edad_dias': 'int', 'no_ignorar_onedrive': 'bool'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total': 'int', 'plan_persistente': 'str'}},
            'aplicar': {'params': {'raiz': 'Path', 'edad_dias': 'int', 'no_ignorar_onedrive': 'bool', 'forzar': 'bool', 'plan': 'Path?', 'dry_run': 'bool'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total_movidos': 'int', 'total_bytes': 'int', 'movidos': 'list', 'fallidos': 'list', 'plan_persistente': 'str'}},
        },
        'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total_movidos': 'int', 'total_bytes': 'int', 'movidos': 'list', 'fallidos': 'list', 'plan_persistente': 'str'},
        'accion': 'deteccion de duplicados exactos con BLAKE3, plan previo y papelera de Windows',
    },
    {
        'name': 'organize',
        'clase': 'capability',
        'version': '1.0',
        'contrato_version': VERSION_CONTRATO,
        'requires_workspace': True,
        'requires_authorization': True,
        'supports_dry_run': True,
        'supports_manifest': True,
        'supports_recovery': True,
        'interactive': True,
        'read_permissions': ['filesystem:read'],
        'write_permissions': ['filesystem:write'],
        'actions': {
            'plan': {'params': {'raiz': 'Path', 'destino': 'Path?', 'no_ignorar_onedrive': 'bool'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'destino': 'str', 'total': 'int', 'plan_persistente': 'str'}},
            'aplicar': {'params': {'raiz': 'Path', 'destino': 'Path?', 'todos': 'bool', 'por_archivo': 'bool', 'no_ignorar_onedrive': 'bool', 'plan': 'Path?', 'dry_run': 'bool'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'destino': 'str', 'total_movidos': 'int', 'total_bytes': 'int', 'movidos': 'list', 'fallidos': 'list', 'plan_persistente': 'str'}},
        },
        'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'destino': 'str', 'total_movidos': 'int', 'total_bytes': 'int', 'movidos': 'list', 'fallidos': 'list', 'plan_persistente': 'str'},
        'accion': 'clasificacion por extension, firma binaria y año con plan previo',
    },
    {
        'name': 'idea',
        'clase': 'capability',
        'version': '1.0',
        'contrato_version': VERSION_CONTRATO,
        'requires_workspace': True,
        'requires_authorization': True,
        'supports_dry_run': False,
        'supports_manifest': False,
        'supports_recovery': False,
        'interactive': False,
        'read_permissions': ['filesystem:read'],
        'write_permissions': ['filesystem:write'],
        'actions': {
            'crear': {'params': {'raiz': 'Path', 'titulo': 'str', 'cuerpo': 'str', 'etiqueta': 'list[str]', 'estado': 'str'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total': 'int'}},
            'revisar': {'params': {'raiz': 'Path'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str'}},
            'listar': {'params': {'raiz': 'Path', 'estado': 'str?'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total': 'int'}},
        },
        'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total': 'int'},
        'accion': 'notas Markdown con frontmatter validado y revision de enlaces',
    },
    {
        'name': 'index',
        'clase': 'capability',
        'version': '1.0',
        'contrato_version': VERSION_CONTRATO,
        'requires_workspace': True,
        'requires_authorization': True,
        'supports_dry_run': False,
        'supports_manifest': False,
        'supports_recovery': False,
        'interactive': False,
        'read_permissions': ['filesystem:read'],
        'write_permissions': ['filesystem:write'],
        'actions': {
            'construir': {'params': {'raiz': 'Path'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'indice': 'str', 'total': 'int'}},
            'buscar': {'params': {'termino': 'str', 'raiz': 'Path?', 'estado': 'str?', 'limite': 'int'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'resultados': 'list', 'total': 'int'}},
            'actualizar': {'params': {'raiz': 'Path'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total': 'int'}},
            'exportar': {'params': {'salida': 'Path', 'raiz': 'Path?'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total': 'int'}},
        },
        'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'indice': 'str', 'total': 'int', 'resultados': 'list'},
        'accion': 'indice SQLite con FTS5 sobre notas Markdown',
    },
    {
        'name': 'ocr',
        'clase': 'capability',
        'version': '1.0',
        'contrato_version': VERSION_CONTRATO,
        'requires_workspace': True,
        'requires_authorization': False,
        'supports_dry_run': False,
        'supports_manifest': False,
        'supports_recovery': False,
        'interactive': False,
        'read_permissions': ['filesystem:read'],
        'write_permissions': ['filesystem:write'],
        'actions': {
            'escanear': {'params': {'raiz': 'Path', 'idioma': 'str', 'no_ignorar_onedrive': 'bool'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total': 'int'}},
            'exportar': {'params': {'raiz': 'Path', 'destino': 'Path?', 'idioma': 'str'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total': 'int'}},
        },
        'outputs': {'estado': 'str', 'codigo': 'int', 'raiz': 'str', 'total': 'int'},
        'accion': 'OCR en solo lectura con Tesseract y PyMuPDF',
    },
    {
        'name': 'nice',
        'clase': 'capability',
        'version': '1.0',
        'contrato_version': VERSION_CONTRATO,
        'requires_workspace': False,
        'requires_authorization': False,
        'supports_dry_run': False,
        'supports_manifest': False,
        'supports_recovery': False,
        'interactive': False,
        'read_permissions': ['process:execute'],
        'write_permissions': [],
        'actions': {
            'ejecutar': {'params': {'comando': 'list[str]', 'prioridad': 'str', 'tiempo': 'float', 'memoria_mb': 'int?'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'memoria_pico': 'int', 'duracion_ms': 'float'}},
        },
        'outputs': {'estado': 'str', 'codigo': 'int', 'memoria_pico': 'int', 'duracion_ms': 'float'},
        'accion': 'ejecuta hijos con prioridad baja y registro de memoria',
    },
    {
        'name': 'doctor',
        'clase': 'capability',
        'version': '1.0',
        'contrato_version': VERSION_CONTRATO,
        'requires_workspace': False,
        'requires_authorization': False,
        'supports_dry_run': False,
        'supports_manifest': False,
        'supports_recovery': False,
        'interactive': False,
        'read_permissions': ['system:read'],
        'write_permissions': [],
        'actions': {
            'ejecutar': {'params': {}, 'outputs': {'estado': 'str', 'codigo': 'int', 'comprobaciones': 'list'}},
        },
        'outputs': {'estado': 'str', 'codigo': 'int', 'comprobaciones': 'list'},
        'accion': 'diagnostico del equipo y del entorno',
    },
    {
        'name': 'health',
        'clase': 'capability',
        'version': '1.0',
        'contrato_version': VERSION_CONTRATO,
        'requires_workspace': False,
        'requires_authorization': False,
        'supports_dry_run': False,
        'supports_manifest': False,
        'supports_recovery': False,
        'interactive': False,
        'read_permissions': ['system:read'],
        'write_permissions': [],
        'actions': {
            'ejecutar': {'params': {'formato': 'str'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'bloques': 'list'}},
        },
        'outputs': {'estado': 'str', 'codigo': 'int', 'bloques': 'list'},
        'accion': 'informe de salud del sistema',
    },
    {
        'name': 'buscar',
        'clase': 'capability',
        'version': '1.0',
        'contrato_version': VERSION_CONTRATO,
        'requires_workspace': True,
        'requires_authorization': False,
        'supports_dry_run': False,
        'supports_manifest': False,
        'supports_recovery': False,
        'interactive': False,
        'read_permissions': ['filesystem:read'],
        'write_permissions': [],
        'actions': {
            'ejecutar': {'params': {'termino': 'str', 'raiz': 'Path?', 'limite': 'int', 'formato': 'str'}, 'outputs': {'estado': 'str', 'codigo': 'int', 'termino': 'str', 'raiz': 'str', 'texto': 'dict?', 'archivos': 'dict?', 'duplicados': 'dict?'}},
        },
        'outputs': {'estado': 'str', 'codigo': 'int', 'termino': 'str', 'raiz': 'str', 'texto': 'dict?', 'archivos': 'dict?', 'duplicados': 'dict?'},
        'accion': 'busqueda e identificacion unificada de solo lectura',
    },
]


def listar_capacidades() -> list[dict[str, Any]]:
    # Devuelve una copia superficial del registro para que el CLI no lo mute.
    return [dict(capacidad) for capacidad in CAPACIDADES]


def obtener_capacidad(nombre: str) -> dict[str, Any] | None:
    # Busca una herramienta por nombre en el registro.
    for capacidad in CAPACIDADES:
        if capacidad['name'] == nombre:
            return dict(capacidad)
    return None


def listar_clasificacion() -> dict[str, str]:
    # Devuelve una copia del mapa de clasificacion.
    return dict(CLASIFICACION)


def obtener_clase(nombre: str) -> str | None:
    # Devuelve la clase de un comando o None si no esta clasificado.
    return CLASIFICACION.get(nombre)
