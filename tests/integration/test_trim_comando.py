# Prueba de integracion del comando trim de punta a punta.
import json
import os
import time

import pytest
from typer.testing import CliRunner

from devkit.cli import app
from devkit.core import safety
from devkit.errors import ErrorLimpieza, ErrorSoloLectura
from devkit.tools import trim

EJECUTOR = CliRunner()
os.environ.setdefault('XDG_CACHE_HOME', '')


def crear_arbol(raiz):
    # Crea una carpeta con cache, log viejo y una fuente que no debe tocarse.
    raiz.mkdir(parents=True, exist_ok=True)
    cache = raiz / '__pycache__'
    cache.mkdir(exist_ok=True)
    (cache / 'modulo.pyc').write_bytes(b'x' * 40)
    marca = time.time() - 10 * 86400
    os.utime(cache, (marca, marca))
    registro = raiz / 'app.log'
    registro.write_bytes(b'x' * 20)
    os.utime(registro, (marca, marca))
    fuente = raiz / 'src' / '__pycache__'
    fuente.mkdir(parents=True, exist_ok=True)
    (fuente / 'otro.pyc').write_bytes(b'x' * 99)
    os.utime(fuente, (marca, marca))
    return raiz


def test_escanear_devuelve_plan(estado_temporal, tmp_path):
    raiz = crear_arbol(tmp_path / 'proyecto')
    resultado = trim.escanear_trim(raiz, edad_dias=7)
    assert resultado['estado'] == 'correcto'
    assert resultado['total'] >= 2
    assert all('src' not in item['ruta'] for item in resultado['acciones'])


def test_comando_escanear_responde_json(estado_temporal, tmp_path):
    raiz = crear_arbol(tmp_path / 'proyecto')
    resultado = EJECUTOR.invoke(
        app,
        ['trim', 'escanear', str(raiz), '--edad-dias', '7'],
        env={'DEVKIT_ESTADO': str(tmp_path / 'estado')},
    )
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['herramienta'] == 'trim'
    assert datos['accion'] == 'escanear'


def test_comando_aplicar_sin_forzar_no_toca(estado_temporal, tmp_path):
    raiz = crear_arbol(tmp_path / 'proyecto')
    env = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    resultado = EJECUTOR.invoke(app, ['trim', 'aplicar', str(raiz)], env=env)
    assert resultado.exit_code == 2
    assert (raiz / '__pycache__').exists()


def test_aplicar_mueve_a_papelera(estado_temporal, tmp_path, monkeypatch):
    raiz = crear_arbol(tmp_path / 'proyecto')
    movimientos = []
    monkeypatch.setattr(
        safety, 'mover_a_papelera_from_safety', lambda ruta: movimientos.append(str(ruta))
    )
    resultado = trim.aplicar_trim(raiz, edad_dias=7)
    assert resultado['estado'] == 'correcto'
    assert resultado['total_movidos'] >= 2
    assert len(movimientos) == resultado['total_movidos']
    assert (raiz / 'src' / '__pycache__').exists()


def test_aplicar_bloqueado_en_solo_lectura(estado_temporal, tmp_path, monkeypatch):
    raiz = crear_arbol(tmp_path / 'proyecto')
    monkeypatch.setenv('DEVKIT_READONLY', '1')
    with pytest.raises(ErrorSoloLectura):
        trim.aplicar_trim(raiz, edad_dias=7)


def test_escanear_rechaza_raiz_invalida(tmp_path):
    with pytest.raises(ErrorLimpieza):
        trim.escanear(tmp_path / 'inexistente')


def test_aplicar_registra_fallidos_sin_abortar(estado_temporal, tmp_path, monkeypatch):
    raiz = crear_arbol(tmp_path / 'proyecto')

    def fallar_some(ruta):
        if '__pycache__' in str(ruta):
            raise ErrorLimpieza('bloqueado por prueba')
        movimientos.append(str(ruta))

    movimientos = []
    monkeypatch.setattr(safety, 'mover_a_papelera_from_safety', fallar_some)
    resultado = trim.aplicar_trim(raiz, edad_dias=7)
    assert resultado['estado'] == 'error'
    assert len(resultado['fallidos']) >= 1
    assert resultado['total_movidos'] >= 1
