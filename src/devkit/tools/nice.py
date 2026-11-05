# Envoltorio para procesos hijos con prioridad baja y registro de memoria.
from __future__ import annotations

import subprocess
import time
from contextlib import suppress
from datetime import UTC, datetime

import psutil

from devkit.core import proceso, runlog
from devkit.errors import ErrorProceso


def validar_comando(comando: list[str]) -> list[str]:
    # Comprueba que el ejecutable exista antes de envolverlo.
    if not comando:
        raise ErrorProceso('hace falta un comando para ejecutar')
    if not comando[0]:
        raise ErrorProceso('el comando no puede ser vacio')
    return comando


def ejecutar_nice(
    comando: list[str],
    prioridad: str = 'bajo',
    timeout: float = 3600.0,
    memoria_maxima_mb: int | None = None,
) -> dict:
    # Lanza el hijo con prioridad en bajo y un tiempo maximo en segundos.
    validado = validar_comando(comando)
    if timeout <= 0:
        raise ErrorProceso('el tiempo maximo debe ser positivo')
    inicio = time.perf_counter()
    memoria_maxima = None
    if memoria_maxima_mb is not None:
        if memoria_maxima_mb <= 0:
            raise ErrorProceso('el limite de memoria debe ser positivo')
        memoria_maxima = memoria_maxima_mb * 1024 * 1024
    job = proceso.crear_job_limite(memoria_maxima) if memoria_maxima else None
    codigo = 2
    salida = ''
    error = ''
    pico = 0
    detalle = 'error'
    hijo = None
    try:
        hijo = subprocess.Popen(
            validado,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        try:
            proceso._aplicar_prioridad(hijo.pid, prioridad)
        except psutil.Error as fallo:
            # Si falla la prioridad, matar al hijo para no dejarlo huerfano.
            with suppress(Exception):
                hijo.kill()
            detalle_prioridad = f'no se pudo aplicar la prioridad {prioridad} porque {fallo}'
            raise ErrorProceso(detalle_prioridad) from fallo
        if job is not None:
            job.asignar(hijo.pid)
        # Mide el pico mientras el hijo corre, no solo al final.
        import threading

        pico_ref = {'valor': 0}
        detenido = threading.Event()

        def _medir():
            while not detenido.wait(0.05):
                try:
                    memoria = psutil.Process(hijo.pid).memory_info().rss
                except psutil.Error:
                    try:
                        memoria = psutil.Process(hijo.pid).memory_full_info().uss
                    except psutil.Error:
                        memoria = 0
                if memoria > pico_ref['valor']:
                    pico_ref['valor'] = int(memoria)

        hilo = threading.Thread(target=_medir, daemon=True)
        hilo.start()
        try:
            salida, error = hijo.communicate(timeout=timeout)
        finally:
            detenido.set()
            hilo.join(timeout=1.0)
        codigo = hijo.returncode
        detalle = f'codigo {codigo}'
        pico = max(pico_ref['valor'], 0)
    except subprocess.TimeoutExpired:
        if hijo is not None:
            hijo.kill()
            hijo.communicate()
        codigo = 124
        detalle = 'tiempo maximo superado'
        error = f'supero {timeout} segundos'
    except FileNotFoundError as fallo:
        raise ErrorProceso(f'no se encontro el ejecutable {validado[0]}') from fallo
    finally:
        if job is not None:
            job.cerrar()
    runlog.registrar_ejecucion('nice', validado, inicio, codigo, pico, detalle)
    # Marca error cuando el hijo termina distinto de cero.
    estado = 'correcto' if codigo == 0 else 'error'
    salida_codigo = 0 if estado == 'correcto' else 2
    return {
        'herramienta': 'nice',
        'accion': 'ejecutar',
        'estado': estado,
        'codigo': salida_codigo,
        'comando': validado,
        'prioridad': prioridad,
        'codigo_proceso': codigo,
        'salida': (salida or '').strip()[-2000:],
        'error': (error or '').strip()[-2000:],
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
        'memoria_pico': pico,
        'fecha': datetime.now(UTC).isoformat(),
    }


__all__ = ['validar_comando', 'ejecutar_nice']
