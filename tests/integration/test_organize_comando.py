# Prueba de integracion del comando organize de punta a punta.
import json
import os
import time

import pytest
from typer.testing import CliRunner

from devkit.cli import app
from devkit.errors import ErrorOrganizar, ErrorSoloLectura
from devkit.tools import organize

EJECUTOR = CliRunner()


def crear_arbol(raiz):
    # Crea carpeta con imagen y documento reales, mas un protegido en .git.
    for nombre, contenido in (
        ('foto.jpg', b'\xff\xd8\xff\x00hola'),
        ('sub/doc.pdf', b'%PDF-1.4 contenido'),
        ('texto.md', b'# notas'),
        ('.git/ignorame.txt', b'no'),
    ):
        ruta = raiz / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
        marca = time.time() - 400 * 86400
        os.utime(ruta, (marca, marca))
    return raiz


def test_plan_devuelve_tipo_y_anio(estado_temporal, tmp_path):
    raiz = crear_arbol(tmp_path / 'proyecto')
    resultado = organize.escanear_organize(raiz)
    assert resultado['estado'] == 'correcto'
    assert resultado['total'] == 3
    assert resultado['por_tipo']['imagen'] == 1
    assert resultado['por_tipo']['documento'] == 2


def test_comando_plan_responde_json(estado_temporal, tmp_path):
    raiz = crear_arbol(tmp_path / 'proyecto')
    env = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    resultado = EJECUTOR.invoke(app, ['organize', 'plan', str(raiz)], env=env)
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['herramienta'] == 'organize'
    assert datos['accion'] == 'plan'


def test_comando_aplicar_sin_flag_no_toca(estado_temporal, tmp_path):
    raiz = crear_arbol(tmp_path / 'proyecto')
    env = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    resultado = EJECUTOR.invoke(app, ['organize', 'aplicar', str(raiz)], env=env)
    assert resultado.exit_code == 2
    assert (raiz / 'foto.jpg').exists()


def test_aplicar_mueve_con_todos(estado_temporal, tmp_path):
    raiz = crear_arbol(tmp_path / 'proyecto')
    resultado = organize.aplicar_organize(raiz, todos=True, confirmar=True)
    assert resultado['estado'] == 'correcto'
    assert resultado['total_movidos'] == 3
    assert not (raiz / 'foto.jpg').exists()
    destino = raiz / 'Organizados'
    assert destino.is_dir()
    assert (raiz / '.git' / 'ignorame.txt').exists()


def test_aplicar_bloqueado_en_solo_lectura(estado_temporal, tmp_path, monkeypatch):
    raiz = crear_arbol(tmp_path / 'proyecto')
    monkeypatch.setenv('DEVKIT_READONLY', '1')
    with pytest.raises(ErrorSoloLectura):
        organize.aplicar_organize(raiz, todos=True, confirmar=True)


def test_comando_aplicar_todos_json(estado_temporal, tmp_path):
    raiz = crear_arbol(tmp_path / 'proyecto')
    env = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    resultado = EJECUTOR.invoke(app, ['organize', 'aplicar', '--todos', '--si', str(raiz)], env=env)
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['total_movidos'] == 3


def test_escanear_rechaza_raiz_invalida(tmp_path):
    with pytest.raises(ErrorOrganizar):
        organize.escanear_organize(tmp_path / 'inexistente')


def test_aplicar_aborta_si_arbol_cambia(estado_temporal, tmp_path, monkeypatch):
    raiz = crear_arbol(tmp_path / 'proyecto')
    original = organize.construir_plan

    def plan_y_borrar(raiz_arg, destino_arg, archivos_arg):
        plan = original(raiz_arg, destino_arg, archivos_arg)
        (raiz / 'foto.jpg').unlink()
        return plan

    monkeypatch.setattr(organize, 'construir_plan', plan_y_borrar)
    resultado = organize.aplicar_organize(raiz, todos=True, confirmar=True)
    assert resultado['estado'] == 'error'
    assert len(resultado['fallidos']) >= 1
