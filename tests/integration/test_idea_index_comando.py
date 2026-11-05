# Prueba de integracion de idea e index de punta a punta.
import json

import pytest
from typer.testing import CliRunner

from devkit.cli import app
from devkit.errors import ErrorSoloLectura
from devkit.tools import idea, index

EJECUTOR = CliRunner()


def crear_nota_cli(raiz, titulo, cuerpo='Cuerpo', estado='activo'):
    env = {'DEVKIT_ESTADO': str(raiz.parent / 'estado')}
    resultado = EJECUTOR.invoke(
        app,
        [
            'idea',
            'crear',
            str(raiz),
            '--titulo',
            titulo,
            '--cuerpo',
            cuerpo,
            '--estado',
            estado,
        ],
        env=env,
    )
    assert resultado.exit_code == 0
    return json.loads(resultado.stdout)


def test_idea_crear_responde_json(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    env = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    resultado = EJECUTOR.invoke(
        app,
        ['idea', 'crear', str(raiz), '--titulo', 'Hola', '--cuerpo', 'texto'],
        env=env,
    )
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['herramienta'] == 'idea'
    assert datos['accion'] == 'crear'
    assert (raiz).is_dir()


def test_idea_revisar_detecta_enlace_roto(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    (raiz / 'nota.md').write_text(
        '---\ntitulo: Nota\ncreado: 2026-11-05\n---\n\nVer [otra](no-existe.md)',
        encoding='utf-8',
    )
    env = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    resultado = EJECUTOR.invoke(app, ['idea', 'revisar', str(raiz)], env=env)
    assert resultado.exit_code == 2
    datos = json.loads(resultado.stdout)
    assert datos['total_errores'] >= 1


def test_idea_listar_filtra_estado(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    (raiz / 'a.md').write_text(
        '---\ntitulo: A\ncreado: 2026-11-05\nestado: activo\n---\n\nC', encoding='utf-8'
    )
    (raiz / 'b.md').write_text(
        '---\ntitulo: B\ncreado: 2026-11-05\nestado: borrador\n---\n\nC', encoding='utf-8'
    )
    env = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    resultado = EJECUTOR.invoke(app, ['idea', 'listar', str(raiz), '--estado', 'activo'], env=env)
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['total'] == 1


def test_index_construir_y_buscar(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    (raiz / 'a.md').write_text(
        '---\ntitulo: Alpha\ncreado: 2026-11-05\n---\n\nTexto sobre python', encoding='utf-8'
    )
    (raiz / 'b.md').write_text(
        '---\ntitulo: Beta\ncreado: 2026-11-05\n---\n\nOtro texto', encoding='utf-8'
    )
    env = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    resultado = EJECUTOR.invoke(app, ['index', 'construir', str(raiz)], env=env)
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['total_notas'] == 2
    # La busqueda usa el indice en estado local.
    resultado2 = EJECUTOR.invoke(app, ['index', 'buscar', 'python', '--raiz', str(raiz)], env=env)
    assert resultado2.exit_code == 0
    datos2 = json.loads(resultado2.stdout)
    assert datos2['total'] >= 1


def test_index_exportar(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    (raiz / 'a.md').write_text(
        '---\ntitulo: Exportable\ncreado: 2026-11-05\n---\n\nCuerpo', encoding='utf-8'
    )
    env = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    EJECUTOR.invoke(app, ['index', 'construir', str(raiz)], env=env)
    salida = tmp_path / 'export.json'
    resultado = EJECUTOR.invoke(
        app, ['index', 'exportar', str(salida), '--raiz', str(raiz)], env=env
    )
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['total'] == 1


def test_idea_crear_bloqueado_solo_lectura(estado_temporal, tmp_path, monkeypatch):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    monkeypatch.setenv('DEVKIT_READONLY', '1')
    with pytest.raises(ErrorSoloLectura):
        idea.crear_nota(raiz, 'X', 'Cuerpo')


def test_index_construir_bloqueado_solo_lectura(estado_temporal, tmp_path, monkeypatch):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    monkeypatch.setenv('DEVKIT_READONLY', '1')
    with pytest.raises(ErrorSoloLectura):
        index.construir_indice(raiz)


def test_idea_revisar_sin_notas(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    env = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    resultado = EJECUTOR.invoke(app, ['idea', 'revisar', str(raiz)], env=env)
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['total_notas'] == 0
    assert datos['total_errores'] == 0
