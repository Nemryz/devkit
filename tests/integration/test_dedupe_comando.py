# Prueba de integracion del comando dedupe de punta a punta.
import json
import os
import time

import pytest
from typer.testing import CliRunner

from devkit.cli import app
from devkit.core import safety
from devkit.errors import ErrorDuplicados, ErrorSoloLectura
from devkit.tools import dedupe

EJECUTOR = CliRunner()


def crear_arbol(raiz):
    # Crea una carpeta con duplicados, un unico y una fuente protegida.
    for nombre, contenido in (
        ('a/uno.jpg', b'img' * 100),
        ('b/dos.jpg', b'img' * 100),
        ('unico.txt', b'unico'),
        ('src/copiar.jpg', b'img' * 100),
    ):
        ruta = raiz / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
        marca = time.time() - 40 * 86400
        os.utime(ruta, (marca, marca))
    return raiz


def test_escanear_devuelve_grupo(estado_temporal, tmp_path):
    raiz = crear_arbol(tmp_path / 'proyecto')
    resultado = dedupe.escanear_dedupe(raiz, edad_dias=30)
    assert resultado['estado'] == 'correcto'
    assert resultado['total_grupos'] == 1
    assert resultado['total'] == 1
    assert resultado['resumen_extension'][0]['extension'] == '.jpg'
    for accion in resultado['acciones']:
        assert 'src' not in accion['origen']


def test_comando_escanear_responde_json(estado_temporal, tmp_path):
    raiz = crear_arbol(tmp_path / 'proyecto')
    env = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    resultado = EJECUTOR.invoke(app, ['dedupe', 'escanear', str(raiz)], env=env)
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['herramienta'] == 'dedupe'
    assert datos['total_grupos'] == 1


def test_comando_aplicar_sin_forzar_no_toca(estado_temporal, tmp_path):
    raiz = crear_arbol(tmp_path / 'proyecto')
    env = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    resultado = EJECUTOR.invoke(app, ['dedupe', 'aplicar', str(raiz)], env=env)
    assert resultado.exit_code == 2
    assert (raiz / 'a' / 'uno.jpg').exists()
    assert (raiz / 'b' / 'dos.jpg').exists()


def test_aplicar_mueve_duplicado(estado_temporal, tmp_path, monkeypatch):
    raiz = crear_arbol(tmp_path / 'proyecto')
    movimientos = []
    monkeypatch.setattr(
        safety, 'mover_a_papelera_from_safety', lambda ruta: movimientos.append(str(ruta))
    )
    resultado = dedupe.aplicar_dedupe(raiz, edad_dias=30, forzar=True)
    assert resultado['estado'] == 'correcto'
    assert resultado['total_movidos'] == 1
    assert (raiz / 'src' / 'copiar.jpg').exists()
    assert (raiz / 'unico.txt').exists()
    assert movimientos and movimientos[0] == resultado['movidos'][0]['origen']


def test_aplicar_bloqueado_en_solo_lectura(estado_temporal, tmp_path, monkeypatch):
    raiz = crear_arbol(tmp_path / 'proyecto')
    monkeypatch.setenv('DEVKIT_READONLY', '1')
    with pytest.raises(ErrorSoloLectura):
        dedupe.aplicar_dedupe(raiz, edad_dias=30, forzar=True)


def test_escanear_rechaza_raiz_invalida(tmp_path):
    with pytest.raises(ErrorDuplicados):
        dedupe.escanear_dedupe(tmp_path / 'inexistente')


def test_aplicar_aborta_si_arbol_cambia(estado_temporal, tmp_path, monkeypatch):
    raiz = crear_arbol(tmp_path / 'proyecto')
    movimientos = []
    original = dedupe.construir_plan

    def plan_y_borrar(grupos, tope=dedupe.TOPE_BYTES):
        plan = original(grupos, tope)
        # Simula que el arbol cambio entre escanear y aplicar.
        import shutil

        shutil.rmtree(raiz / 'b', ignore_errors=True)
        return plan

    monkeypatch.setattr(dedupe, 'construir_plan', plan_y_borrar)
    monkeypatch.setattr(
        safety, 'mover_a_papelera_from_safety', lambda ruta: movimientos.append(str(ruta))
    )
    resultado = dedupe.aplicar_dedupe(raiz, edad_dias=30, forzar=True)
    assert resultado['estado'] == 'error'
    assert len(resultado['fallidos']) >= 1
    assert movimientos == []


def test_aplicar_registra_fallidos_sin_abortar(estado_temporal, tmp_path, monkeypatch):
    raiz = crear_arbol(tmp_path / 'proyecto')

    def mover(ruta):
        from devkit.errors import ErrorLimpieza

        raise ErrorLimpieza('bloqueado por prueba')

    monkeypatch.setattr(safety, 'mover_a_papelera_from_safety', mover)
    resultado = dedupe.aplicar_dedupe(raiz, edad_dias=30, forzar=True)
    assert resultado['estado'] == 'error'
    assert len(resultado['fallidos']) == 1
