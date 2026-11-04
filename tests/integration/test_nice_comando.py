# Prueba de integracion del comando nice de punta a punta.
import json
import sys

from typer.testing import CliRunner

from devkit.cli import app

EJECUTOR = CliRunner()


def test_nice_ejecuta_con_prioridad(estado_temporal):
    env = {'DEVKIT_ESTADO': str(estado_temporal)}
    resultado = EJECUTOR.invoke(
        app,
        ['nice', 'ejecutar', '--prioridad', 'bajo', '--', sys.executable, '-c', 'print("ok")'],
        env=env,
    )
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['herramienta'] == 'nice'
    assert datos['prioridad'] == 'bajo'
    assert datos['codigo_proceso'] == 0


def test_nice_responde_tabla(estado_temporal):
    env = {'DEVKIT_ESTADO': str(estado_temporal)}
    resultado = EJECUTOR.invoke(
        app,
        ['nice', 'ejecutar', '--formato', 'tabla', '--', sys.executable, '-c', 'pass'],
        env=env,
    )
    assert resultado.exit_code == 0
    assert 'nice' in resultado.stdout
    assert 'estado general' in resultado.stdout


def test_nice_sin_comando_da_error(estado_temporal):
    env = {'DEVKIT_ESTADO': str(estado_temporal)}
    resultado = EJECUTOR.invoke(app, ['nice', 'ejecutar'], env=env)
    # Typer responde 2 cuando falta el argumento obligatorio.
    assert resultado.exit_code != 0


def test_nice_con_codigo_error(estado_temporal):
    env = {'DEVKIT_ESTADO': str(estado_temporal)}
    resultado = EJECUTOR.invoke(
        app,
        ['nice', 'ejecutar', '--', sys.executable, '-c', 'import sys; sys.exit(5)'],
        env=env,
    )
    assert resultado.exit_code == 2
    datos = json.loads(resultado.stdout)
    assert datos['codigo_proceso'] == 5
