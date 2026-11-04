# Diagnostico previo del equipo y del entorno donde corre el toolkit.
from __future__ import annotations

import importlib.util
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from devkit import __version__
from devkit.core import paths, runlog, sistema

DEPENDENCIAS = ('typer', 'rich', 'psutil', 'pydantic', 'orjson')
RAM_AVISO_GB = 1.0
RAM_ERROR_GB = 0.3
DISCO_AVISO_GB = 20.0
DISCO_ERROR_GB = 5.0


def _resultado(nombre: str, estado: str, detalle: str, valor: Any = None) -> dict:
    # Uniforma la forma de cada comprobacion para que el JSON sea predecible.
    return {'nombre': nombre, 'estado': estado, 'detalle': detalle, 'valor': valor}


def comprobar_python() -> dict:
    # Comprueba que el interprete cumple la version minima del proyecto.
    actual = sys.version_info
    texto = f'{actual.major}.{actual.minor}.{actual.micro}'
    if actual < (3, 12):
        return _resultado('python', 'error', f'se requiere 3.12 o superior y hay {texto}', texto)
    return _resultado('python', 'ok', f'version {texto}', texto)


def comprobar_dependencias() -> dict:
    # Verifica que los cinco paquetes del nucleo se puedan importar.
    faltantes = [nombre for nombre in DEPENDENCIAS if importlib.util.find_spec(nombre) is None]
    if faltantes:
        unidos = ', '.join(faltantes)
        return _resultado('dependencias', 'error', f'faltan paquetes {unidos}', faltantes)
    total = len(DEPENDENCIAS)
    return _resultado('dependencias', 'ok', f'{total} paquetes disponibles', total)


def comprobar_memoria() -> dict:
    # Compara la memoria disponible con los umbrales definidos para este equipo.
    disponible = psutil.virtual_memory().available / (1024**3)
    redondeado = round(disponible, 2)
    if disponible < RAM_ERROR_GB:
        return _resultado('memoria', 'error', f'{redondeado} GB disponibles', redondeado)
    if disponible < RAM_AVISO_GB:
        return _resultado('memoria', 'aviso', f'{redondeado} GB disponibles', redondeado)
    return _resultado('memoria', 'ok', f'{redondeado} GB disponibles', redondeado)


def comprobar_disco() -> dict:
    # Mide el espacio libre en el volumen donde vive el perfil del usuario.
    ancla = Path.home().anchor or 'C:\\'
    uso = shutil.disk_usage(ancla)
    libre = uso.free / (1024**3)
    redondeado = round(libre, 2)
    if libre < DISCO_ERROR_GB:
        return _resultado('disco', 'error', f'{redondeado} GB libres en {ancla}', redondeado)
    if libre < DISCO_AVISO_GB:
        return _resultado('disco', 'aviso', f'{redondeado} GB libres en {ancla}', redondeado)
    return _resultado('disco', 'ok', f'{redondeado} GB libres en {ancla}', redondeado)


def comprobar_estado() -> dict:
    # Confirma que la carpeta de estado existe y acepta escritura.
    destino = paths.directorio_estado()
    prueba = destino / 'prueba-escritura.tmp'
    try:
        paths.asegurar_directorio(destino)
        prueba.write_text('ok', encoding='utf-8')
        prueba.unlink()
    except OSError as fallo:
        detalle = f'no se puede escribir en {destino} porque {fallo}'
        return _resultado('estado', 'error', detalle, str(destino))
    return _resultado('estado', 'ok', f'carpeta {destino}', str(destino))


def comprobar_journal() -> dict:
    # Comprueba que el registro de ejecuciones se pueda crear y contar.
    try:
        paths.asegurar_directorio(paths.directorio_journal())
        total = runlog.contar_ejecuciones()
    except OSError as fallo:
        return _resultado('journal', 'error', f'no se puede preparar el journal porque {fallo}')
    return _resultado('journal', 'ok', f'{total} ejecuciones registradas', total)


def comprobar_onedrive() -> dict:
    # Avisa cuando el directorio de trabajo cae dentro de una carpeta sincronizada.
    trabajo = Path.cwd()
    if paths.es_onedrive(trabajo):
        detalle = f'el directorio actual esta en OneDrive {trabajo}'
        return _resultado('onedrive', 'aviso', detalle, str(trabajo))
    return _resultado('onedrive', 'ok', 'el directorio actual no esta en OneDrive', str(trabajo))


def comprobar_rutas_largas() -> dict:
    # Detecta si el sistema permite rutas de mas de 260 caracteres.
    if sistema.rutas_largas_habilitadas():
        return _resultado('rutas_largas', 'ok', 'el sistema admite rutas extendidas', True)
    return _resultado('rutas_largas', 'aviso', 'LongPathsEnabled esta desactivado', False)


def comprobar_elevacion() -> dict:
    # Informa el nivel de permisos sin exigir elevacion para el diagnostico.
    if sistema.es_administrador():
        return _resultado('elevacion', 'ok', 'el proceso tiene elevacion', True)
    return _resultado('elevacion', 'ok', 'el proceso corre sin elevacion', False)


def calcular_estado(comprobaciones: list[dict]) -> tuple[str, int]:
    # Resume las comprobaciones en un estado y un codigo de salida estables.
    if any(fila['estado'] == 'error' for fila in comprobaciones):
        return 'error', 2
    if any(fila['estado'] == 'aviso' for fila in comprobaciones):
        return 'aviso', 1
    return 'correcto', 0


def _memoria_actual() -> int:
    try:
        return int(psutil.Process().memory_info().rss)
    except psutil.Error:
        return 0


def ejecutar_doctor(argumentos: list[str] | None = None) -> dict:
    # Ejecuta todas las comprobaciones y deja constancia en el journal.
    inicio = time.perf_counter()
    comprobaciones = [
        comprobar_python(),
        comprobar_dependencias(),
        comprobar_memoria(),
        comprobar_disco(),
        comprobar_estado(),
        comprobar_journal(),
        comprobar_onedrive(),
        comprobar_rutas_largas(),
        comprobar_elevacion(),
    ]
    estado, codigo = calcular_estado(comprobaciones)
    duracion = round((time.perf_counter() - inicio) * 1000, 1)
    resultado = {
        'herramienta': 'doctor',
        'version': __version__,
        'fecha': datetime.now(UTC).isoformat(),
        'equipo': sistema.nombre_equipo(),
        'sistema': sistema.descripcion_sistema(),
        'estado': estado,
        'codigo': codigo,
        'duracion_ms': duracion,
        'comprobaciones': comprobaciones,
    }
    try:
        runlog.registrar_ejecucion(
            herramienta='doctor',
            argumentos=argumentos or [],
            inicio=inicio,
            codigo=codigo,
            memoria_pico=_memoria_actual(),
            detalle=estado,
        )
    except OSError as fallo:
        resultado['aviso_journal'] = str(fallo)
    return resultado
