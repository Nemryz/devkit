# Registro transaccional de acciones con estados PENDING -> COMPLETED.
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from devkit.core import paths

ESTADOS_ABIERTOS = {'PENDING', 'RUNNING'}


def _ahora() -> str:
    return datetime.now(UTC).isoformat()


def ruta_journal() -> Path:
    # Ruta unica del journal transaccional y del resumen antiguo.
    return paths.asegurar_directorio(paths.directorio_journal()) / 'ejecuciones.jsonl'


def espacio_heredado(espacio_trabajo: str = '') -> str:
    # Toda operacion hereda su espacio de trabajo del entorno si nadie lo aporta.
    if espacio_trabajo:
        return espacio_trabajo
    activo = paths.workspace_activo()
    return str(activo) if activo else ''


def _agregar(ruta: Path, registro: dict) -> None:
    # Una sola escritura en modo append para no partir lineas entre procesos concurrentes.
    linea = (json.dumps(registro, ensure_ascii=False) + '\n').encode('utf-8')
    with ruta.open('ab') as archivo:
        archivo.write(linea)


def registrar_hito(
    id_ejecucion: str,
    herramienta: str,
    accion: str,
    estado: str,
    detalle: str = '',
    origen: str = '',
    destino: str = '',
    codigo: int | None = None,
    espacio_trabajo: str = '',
    id_plan: str = '',
) -> Path:
    # Escribe una linea JSON con el estado de una accion concreta.
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
        'espacio_trabajo': espacio_heredado(espacio_trabajo),
        'id_plan': id_plan,
        'pid': os.getpid(),
    }
    _agregar(ruta_journal(), registro)
    return ruta_journal()


def iniciar_ejecucion(
    herramienta: str,
    accion: str,
    espacio_trabajo: str = '',
    id_plan: str = '',
) -> str:
    # Crea un id unico y escribe el hito PENDING de la ejecucion.
    id_ejecucion = f'{herramienta}-{uuid.uuid4().hex[:8]}'
    registrar_hito(
        id_ejecucion,
        herramienta,
        accion,
        'PENDING',
        'inicio',
        espacio_trabajo=espacio_trabajo,
        id_plan=id_plan,
    )
    return id_ejecucion


def cerrar_ejecucion(
    id_ejecucion: str,
    herramienta: str,
    accion: str,
    estado: str,
    codigo: int,
    detalle: str = '',
    espacio_trabajo: str = '',
    id_plan: str = '',
) -> Path:
    # Cierra con RUNNING, COMPLETED, FAILED o INTERRUPTED.
    return registrar_hito(
        id_ejecucion,
        herramienta,
        accion,
        estado,
        detalle=detalle or estado,
        codigo=codigo,
        espacio_trabajo=espacio_trabajo,
        id_plan=id_plan,
    )


def registrar_ejecucion(
    herramienta: str,
    argumentos: list[str],
    inicio: float,
    codigo: int,
    memoria_pico: int,
    detalle: str = '',
    espacio_trabajo: str = '',
    id_plan: str = '',
) -> Path:
    # Mantiene compatibilidad con el journal antiguo de una linea.
    id_ejecucion = iniciar_ejecucion(herramienta, argumentos[0] if argumentos else 'ejecutar')
    estado = 'COMPLETED' if codigo == 0 else 'FAILED'
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
        'espacio_trabajo': espacio_heredado(espacio_trabajo),
        'id_plan': id_plan,
        'pid': os.getpid(),
    }
    _agregar(ruta_journal(), registro)
    return ruta_journal()


def _ultimos_registros(ruta: Path) -> dict[str, dict]:
    # Recorre el journal y conserva el ultimo registro valido de cada ejecucion.
    ultimos: dict[str, dict] = {}
    if not ruta.exists():
        return ultimos
    with ruta.open('r', encoding='utf-8', errors='replace') as archivo:
        for linea in archivo:
            if not linea.strip():
                continue
            try:
                datos = json.loads(linea)
            except json.JSONDecodeError:
                continue
            ident = datos.get('id_ejecucion')
            if ident and datos.get('estado'):
                ultimos[ident] = datos
    return ultimos


def ejecuciones_abiertas() -> list[dict]:
    # Devuelve los registros cuya ultima linea sigue abierta y sin cerrar.
    ultimos = _ultimos_registros(paths.ruta_journal())
    return [datos for datos in ultimos.values() if datos.get('estado') in ESTADOS_ABIERTOS]


def recuperar_interrumpidas() -> list[str]:
    # Marca INTERRUPTED cada ejecucion abierta para que no queden estados ambiguos.
    abiertas = ejecuciones_abiertas()
    recuperadas = []
    for datos in abiertas:
        registrar_hito(
            datos.get('id_ejecucion', ''),
            datos.get('herramienta', 'desconocida'),
            datos.get('accion', ''),
            'INTERRUPTED',
            'recuperada al comprobar el journal',
            espacio_trabajo=str(datos.get('espacio_trabajo', '')),
        )
        recuperadas.append(datos.get('id_ejecucion', ''))
    return recuperadas


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
                    'herramienta' in datos and datos.get('estado') not in ESTADOS_ABIERTOS
                ):
                    total += 1
    return total
