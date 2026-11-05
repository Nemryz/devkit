# Registro transaccional de acciones con estados PENDING -> COMPLETED.
from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from devkit.core import paths


def _ahora() -> str:
    return datetime.now(UTC).isoformat()


def ruta_journal() -> Path:
    # Ruta unica del journal transaccional y del resumen antiguo.
    return paths.asegurar_directorio(paths.directorio_journal()) / 'ejecuciones.jsonl'


def registrar_hito(
    id_ejecucion: str,
    herramienta: str,
    accion: str,
    estado: str,
    detalle: str = '',
    origen: str = '',
    destino: str = '',
    codigo: int | None = None,
) -> Path:
    # Escribe una linea JSON con el estado de una accion concreta.
    ruta = ruta_journal()
    registro = {
        'fecha': _ahora(),
        'id_ejecucion': id_ejecucion,
        'herramienta': herramienta,
        'accion': accion,
        'estado': estado,
        'detalle': detalle,
        'origen': origen,
        'destino': destino,
        'codigo': codigo,
        'pid': os.getpid(),
    }
    with ruta.open('a', encoding='utf-8') as archivo:
        archivo.write(json.dumps(registro, ensure_ascii=False) + '\n')
    return ruta


def iniciar_ejecucion(herramienta: str, accion: str) -> str:
    # Crea un id unico y escribe el hito PENDING de la ejecucion.
    import uuid

    id_ejecucion = f'{herramienta}-{uuid.uuid4().hex[:8]}'
    registrar_hito(id_ejecucion, herramienta, accion, 'PENDING', 'inicio')
    return id_ejecucion


def cerrar_ejecucion(
    id_ejecucion: str,
    herramienta: str,
    accion: str,
    estado: str,
    codigo: int,
    detalle: str = '',
) -> Path:
    # Cierra con RUNNING, COMPLETED, FAILED o INTERRUPTED.
    return registrar_hito(
        id_ejecucion,
        herramienta,
        accion,
        estado,
        detalle=detalle or estado,
        codigo=codigo,
    )


def registrar_ejecucion(
    herramienta: str,
    argumentos: list[str],
    inicio: float,
    codigo: int,
    memoria_pico: int,
    detalle: str = '',
) -> Path:
    # Mantiene compatibilidad con el journal antiguo de una linea.
    id_ejecucion = iniciar_ejecucion(herramienta, argumentos[0] if argumentos else 'ejecutar')
    estado = 'COMPLETED' if codigo == 0 else 'FAILED' if codigo != 0 else 'ERROR'
    ruta = ruta_journal()
    registro = {
        'fecha': _ahora(),
        'id_ejecucion': id_ejecucion,
        'herramienta': herramienta,
        'argumentos': argumentos,
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
        'codigo': codigo,
        'memoria_pico': memoria_pico,
        'detalle': detalle,
        'estado': estado,
        'pid': os.getpid(),
    }
    with ruta.open('a', encoding='utf-8') as archivo:
        archivo.write(json.dumps(registro, ensure_ascii=False) + '\n')
    return ruta


def contar_ejecuciones() -> int:
    # Mantiene compatibilidad con el contador del doctor.
    ruta = paths.ruta_journal()
    if not ruta.exists():
        return 0
    total = 0
    with ruta.open('r', encoding='utf-8', errors='replace') as archivo:
        for linea in archivo:
            if linea.strip():
                try:
                    datos = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                # Solo cuenta las ejecuciones completadas con id.
                cerrada = {'COMPLETED', 'FAILED', 'INTERRUPTED', 'correcto', 'aviso', 'error'}
                if datos.get('estado') in cerrada or (
                    'herramienta' in datos and datos.get('estado') not in {'PENDING', 'RUNNING'}
                ):
                    total += 1
    return total
