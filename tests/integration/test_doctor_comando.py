# Prueba de integracion del comando doctor de punta a punta.
import json

from typer.testing import CliRunner

from devkit.cli import app

EJECUTOR = CliRunner()


def test_doctor_responde_json(estado_temporal):
    resultado = EJECUTOR.invoke(
        app,
        ['doctor', '--formato', 'json'],
        env={'DEVKIT_ESTADO': str(estado_temporal)},
    )
    assert resultado.exit_code in (0, 1, 2)
    datos = json.loads(resultado.stdout)
    assert datos['herramienta'] == 'doctor'
    assert datos['estado'] in ('correcto', 'aviso', 'error')
    assert len(datos['comprobaciones']) == 9


def test_doctor_responde_tabla(estado_temporal):
    resultado = EJECUTOR.invoke(
        app,
        ['doctor', '--formato', 'tabla'],
        env={'DEVKIT_ESTADO': str(estado_temporal)},
    )
    assert resultado.exit_code in (0, 1, 2)
    assert 'estado general' in resultado.stdout


def test_version_global_responde():
    resultado = EJECUTOR.invoke(app, ['--version'])
    assert resultado.exit_code == 0
    assert 'devkit' in resultado.stdout
