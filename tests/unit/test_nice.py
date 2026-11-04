# Pruebas del envoltorio de procesos con prioridad baja.
import sys

import pytest

from devkit.errors import ErrorProceso
from devkit.tools import nice


def test_validar_comando_rechaza_vacio():
    with pytest.raises(ErrorProceso):
        nice.validar_comando([])


def test_validar_comando_rechaza_primero_vacio():
    with pytest.raises(ErrorProceso):
        nice.validar_comando(['', 'x'])


def test_validar_comando_acepta_lista():
    assert nice.validar_comando(['hola', '--flag']) == ['hola', '--flag']


def test_ejecutar_nice_ok(estado_temporal):
    resultado = nice.ejecutar_nice(
        [sys.executable, '-c', 'print("hola")'], prioridad='bajo', timeout=20
    )
    assert resultado['estado'] == 'correcto'
    assert resultado['codigo_proceso'] == 0
    assert resultado['prioridad'] == 'bajo'
    assert 'hola' in resultado['salida']


def test_ejecutar_nice_codigo_distinto_no_cero(estado_temporal):
    resultado = nice.ejecutar_nice(
        [sys.executable, '-c', 'import sys; sys.exit(3)'], timeout=20
    )
    assert resultado['estado'] == 'error'
    assert resultado['codigo_proceso'] == 3


def test_ejecutar_nice_timeout(estado_temporal):
    resultado = nice.ejecutar_nice(
        [sys.executable, '-c', 'import time; time.sleep(5)'], timeout=1
    )
    assert resultado['estado'] == 'error'
    assert resultado['codigo_proceso'] == 124
    assert 'tiempo maximo' in resultado['error'] or 'segundos' in resultado['error']


def test_ejecutar_nice_rechaza_tiempo_invalido(estado_temporal):
    with pytest.raises(ErrorProceso):
        nice.ejecutar_nice([sys.executable, '-c', 'pass'], timeout=0)


def test_ejecutar_nice_rechaza_memoria_invalida(estado_temporal):
    with pytest.raises(ErrorProceso):
        nice.ejecutar_nice(
            [sys.executable, '-c', 'pass'], timeout=20, memoria_maxima_mb=0
        )


def test_ejecutar_nice_registra_journal(estado_temporal):
    nice.ejecutar_nice([sys.executable, '-c', 'pass'], timeout=20)
    journal = estado_temporal / 'journal' / 'ejecuciones.jsonl'
    assert 'nice' in journal.read_text(encoding='utf-8')
