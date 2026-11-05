# Prueba de integracion del comando health de punta a punta.
import json

from typer.testing import CliRunner

from devkit.cli import app

EJECUTOR = CliRunner()


def test_health_responde_json(estado_temporal):
    resultado = EJECUTOR.invoke(app, ['health', '--formato', 'json'])
    assert resultado.exit_code in (0, 1, 2)
    datos = json.loads(resultado.stdout)
    assert datos['herramienta'] == 'health'
    assert len(datos['bloques']) == 9
    nombres = [fila['nombre'] for fila in datos['bloques']]
    for esperado in ('memoria', 'disco', 'bateria', 'defender'):
        assert esperado in nombres


def test_health_responde_tabla(estado_temporal):
    resultado = EJECUTOR.invoke(app, ['health', '--formato', 'tabla'])
    assert resultado.exit_code in (0, 1, 2)
    assert 'estado general' in resultado.stdout
    assert 'health' in resultado.stdout


def test_health_sin_administrador_no_falla(estado_temporal):
    resultado = EJECUTOR.invoke(app, ['health'])
    assert resultado.exit_code in (0, 1, 2)
    datos = json.loads(resultado.stdout)
    for fila in datos['bloques']:
        assert fila['estado'] in ('ok', 'aviso', 'error', 'unknown')
