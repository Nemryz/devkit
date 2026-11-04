# Registro append only de cada ejecucion del toolkit.
from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from devkit.core import paths


def _ahora() -> str:
    return datetime.now(UTC).isoformat()


def registrar_ejecucion(
    herramienta: str,
    argumentos: list[str],
    inicio: float,
    codigo: int,
    memoria_pico: int,
    detalle: str = '',
) -> Path:
    # Escribe una linea JSON por ejecucion y devuelve la ruta del journal.
    ruta = paths.asegurar_directorio(paths.directorio_journal()) / 'ejecuciones.jsonl'
    registro = {
        'fecha': _ahora(),
        'herramienta': herramienta,
        'argumentos': argumentos,
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
        'codigo': codigo,
        'memoria_pico': memoria_pico,
        'detalle': detalle,
        'pid': os.getpid(),
    }
    with ruta.open('a', encoding='utf-8') as archivo:
        archivo.write(json.dumps(registro, ensure_ascii=False) + '\n')
    return ruta


def contar_ejecuciones() -> int:
    # Cuenta las lineas con contenido sin cargar el archivo completo en memoria.
    ruta = paths.ruta_journal()
    if not ruta.exists():
        return 0
    total = 0
    with ruta.open('r', encoding='utf-8', errors='replace') as archivo:
        for linea in archivo:
            if linea.strip():
                total += 1
    return total
