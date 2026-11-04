# Ejecucion de procesos hijos con prioridad reducida y tiempo maximo.
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

import psutil

from devkit.errors import ErrorProceso


@dataclass
class ResultadoProceso:
    codigo: int
    salida: str
    error: str
    duracion_ms: float


def ejecutar(comando: list[str], timeout: float = 60.0) -> ResultadoProceso:
    # Lanza el proceso con prioridad por debajo de la normal para no ahogar el escritorio.
    inicio = time.perf_counter()
    proceso = None
    try:
        proceso = subprocess.Popen(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        psutil.Process(proceso.pid).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        salida, error = proceso.communicate(timeout=timeout)
    except FileNotFoundError as fallo:
        raise ErrorProceso(f'no se encontro el ejecutable {comando[0]}') from fallo
    except subprocess.TimeoutExpired as fallo:
        if proceso is not None:
            proceso.kill()
        raise ErrorProceso(f'el proceso supero {timeout} segundos') from fallo
    duracion = round((time.perf_counter() - inicio) * 1000, 1)
    return ResultadoProceso(
        codigo=proceso.returncode,
        salida=salida or '',
        error=error or '',
        duracion_ms=duracion,
    )
