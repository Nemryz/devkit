# Pruebas de identidad de espacios de trabajo para el indice SQLite.
import json

import pytest
from typer.testing import CliRunner

from devkit.cli import app
from devkit.core import paths
from devkit.errors import ErrorIndex
from devkit.tools import index as modulo_index

EJECUTOR = CliRunner()


def _nota(ruta, titulo, cuerpo):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        f'---\ntitulo: {titulo}\ncreado: 2026-11-05\n---\n\n{cuerpo}\n',
        encoding='utf-8',
    )


def test_buscar_sin_raiz_usa_el_directorio_actual(tmp_path, monkeypatch):
    notas = tmp_path / 'notas'
    _nota(notas / 'a.md', 'Alpha', 'contenido sobre python')
    entorno = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    resultado = EJECUTOR.invoke(app, ['index', 'construir', str(notas)], env=entorno)
    assert resultado.exit_code == 0
    monkeypatch.chdir(notas)
    salida = EJECUTOR.invoke(app, ['index', 'buscar', 'python'], env=entorno)
    assert salida.exit_code == 0
    datos = json.loads(salida.stdout)
    assert datos['total'] == 1


def test_buscar_sin_raiz_respeta_devkit_workspace(tmp_path, monkeypatch):
    notas = tmp_path / 'notas'
    _nota(notas / 'a.md', 'Alpha', 'contenido sobre python')
    entorno = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    resultado = EJECUTOR.invoke(app, ['index', 'construir', str(notas)], env=entorno)
    assert resultado.exit_code == 0
    otro = tmp_path / 'otra-carpeta'
    otro.mkdir()
    monkeypatch.chdir(otro)
    monkeypatch.setenv('DEVKIT_WORKSPACE', str(notas))
    salida = EJECUTOR.invoke(app, ['index', 'buscar', 'python'])
    assert salida.exit_code == 0
    datos = json.loads(salida.stdout)
    assert datos['total'] == 1


def test_buscar_sin_indice_error_explicito(tmp_path, monkeypatch):
    vacio = tmp_path / 'vacio'
    vacio.mkdir()
    monkeypatch.chdir(vacio)
    monkeypatch.delenv('DEVKIT_WORKSPACE', raising=False)
    salida = EJECUTOR.invoke(
        app, ['index', 'buscar', 'python'], env={'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    )
    assert salida.exit_code == 2
    datos = json.loads(salida.stdout)
    assert 'ejecuta index construir' in datos['detalle']


def test_workspace_movido_conserva_su_indice(tmp_path, monkeypatch):
    notas = tmp_path / 'origen' / 'notas'
    _nota(notas / 'a.md', 'Alpha', 'texto sobre rust')
    entorno = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    assert EJECUTOR.invoke(app, ['index', 'construir', str(notas)], env=entorno).exit_code == 0
    destino = tmp_path / 'nueva-ubicacion' / 'notas'
    destino.parent.mkdir(parents=True)
    notas.rename(destino)
    salida = EJECUTOR.invoke(app, ['index', 'buscar', 'rust', '--raiz', str(destino)], env=entorno)
    assert salida.exit_code == 0
    datos = json.loads(salida.stdout)
    assert datos['total'] == 1


def test_raiz_de_solo_lectura_da_error_explicito(tmp_path):
    notas = tmp_path / 'notas'
    notas.mkdir()
    (notas / '.devkit').write_text('bloquea la carpeta del indice', encoding='utf-8')
    _nota(notas / 'a.md', 'Alpha', 'texto')
    with pytest.raises(ErrorIndex):
        modulo_index.construir_indice(notas)


def test_espacios_separados_devuelven_solo_lo_propio(tmp_path):
    ws1 = tmp_path / 'ws1' / 'notas'
    ws2 = tmp_path / 'ws2' / 'notas'
    _nota(ws1 / 'a.md', 'Uno', 'codigo sobre single channel')
    _nota(ws2 / 'b.md', 'Dos', 'codigo sobre single channel')
    entorno = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    r1 = EJECUTOR.invoke(app, ['index', 'construir', str(ws1)], env=entorno)
    r2 = EJECUTOR.invoke(app, ['index', 'construir', str(ws2)], env=entorno)
    assert r1.exit_code == 0 and r2.exit_code == 0
    s1 = EJECUTOR.invoke(app, ['index', 'buscar', 'channel', '--raiz', str(ws1)], env=entorno)
    s2 = EJECUTOR.invoke(app, ['index', 'buscar', 'channel', '--raiz', str(ws2)], env=entorno)
    d1 = json.loads(s1.stdout)
    d2 = json.loads(s2.stdout)
    assert d1['total'] == 1
    assert 'ws1' in d1['resultados'][0]['ruta']
    assert d2['total'] == 1
    assert 'ws2' in d2['resultados'][0]['ruta']


def test_workspace_activo_sin_variable_da_none(monkeypatch):
    monkeypatch.delenv('DEVKIT_WORKSPACE', raising=False)
    assert paths.workspace_activo() is None
