# Pruebas del descubrimiento de capacidades para usuarios y agentes.
import json

from typer.testing import CliRunner

from devkit.cli import app

EJECUTOR = CliRunner()


def test_capabilities_devuelve_registro_completo():
    resultado = EJECUTOR.invoke(app, ['capabilities'])
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['estado'] == 'correcto'
    assert datos['total'] == len(datos['capacidades'])
    assert any(c['name'] == 'trim' for c in datos['capacidades'])


def test_describe_conocido_devuelve_contrato():
    resultado = EJECUTOR.invoke(app, ['describe', 'trim'])
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['capacidad']['name'] == 'trim'
    assert datos['capacidad']['supports_dry_run'] is True


def test_describe_desconocido_falla_con_codigo_estable():
    resultado = EJECUTOR.invoke(app, ['describe', 'no-existe'])
    assert resultado.exit_code == 2
    datos = json.loads(resultado.stdout)
    assert datos['estado'] == 'error'
