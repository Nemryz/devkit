# Pruebas de regresion del bloque L: catálogo verificable bidireccional.
import json

import typer.main
from typer.testing import CliRunner

from devkit.cli import app
from devkit.core import capabilities as modulo_capacidades

EJECUTOR = CliRunner()


def _comandos_click() -> dict[str, object]:
    # Enumera los comandos de nivel superior desde la aplicacion Click.
    comando = typer.main.get_command(app)
    return dict(comando.commands)


def _subcomandos_click(nombre: str) -> set[str]:
    # Enumera los subcomandos de un comando de nivel superior.
    comando = typer.main.get_command(app)
    sub = comando.commands.get(nombre)
    if sub is None or not hasattr(sub, 'commands'):
        return set()
    return set(sub.commands.keys())


def _opciones_click(nombre: str) -> set[str]:
    # Enumera los nombres de opciones de un comando (incluyendo subcomandos).
    comando = typer.main.get_command(app)
    sub = comando.commands.get(nombre)
    if sub is None:
        return set()
    opciones: set[str] = set()
    if hasattr(sub, 'commands'):
        for subcmd in sub.commands.values():
            for param in getattr(subcmd, 'params', []):
                opciones.update(getattr(param, 'opts', []))
    else:
        for param in getattr(sub, 'params', []):
            opciones.update(getattr(param, 'opts', []))
    return opciones


def test_todos_los_comandos_estan_clasificados():
    comandos = _comandos_click()
    clasificacion = modulo_capacidades.listar_clasificacion()
    for nombre in comandos:
        assert nombre in clasificacion, f'comando {nombre} sin clasificar'
    # No hay clasificaciones huerfanas.
    for nombre in clasificacion:
        assert nombre in comandos, f'clasificacion huerfana: {nombre}'


def test_capacidades_coinciden_con_clasificacion():
    capacidades = modulo_capacidades.listar_capacidades()
    clasificacion = modulo_capacidades.listar_clasificacion()
    nombres_cap = {c['name'] for c in capacidades}
    nombres_clase = {n for n, c in clasificacion.items() if c == 'capability'}
    assert nombres_cap == nombres_clase, (
        f'capacidades != clasificacion capability: '
        f'solo en capacidades={nombres_cap - nombres_clase}, '
        f'solo en clasificacion={nombres_clase - nombres_cap}'
    )


def test_no_hay_duplicados_en_capacidades():
    capacidades = modulo_capacidades.listar_capacidades()
    nombres = [c['name'] for c in capacidades]
    assert len(nombres) == len(set(nombres)), 'capacidad duplicada'


def test_acciones_coinciden_con_subcomandos():
    capacidades = modulo_capacidades.listar_capacidades()
    for cap in capacidades:
        nombre = cap['name']
        subcomandos = _subcomandos_click(nombre)
        if not subcomandos:
            # Comando sin subcomandos: debe tener accion 'ejecutar'.
            assert 'ejecutar' in cap['actions'], (
                f'{nombre} sin subcomandos pero sin accion ejecutar'
            )
            continue
        acciones = set(cap['actions'].keys())
        assert acciones == subcomandos, (
            f'{nombre}: acciones={acciones} != subcomandos={subcomandos}'
        )


def test_supports_dry_run_coincide():
    capacidades = modulo_capacidades.listar_capacidades()
    for cap in capacidades:
        nombre = cap['name']
        opciones = _opciones_click(nombre)
        tiene_dry_run = '--dry-run' in opciones
        assert cap['supports_dry_run'] == tiene_dry_run, (
            f'{nombre}: supports_dry_run={cap["supports_dry_run"]} '
            f'pero --dry-run {"presente" if tiene_dry_run else "ausente"}'
        )


def test_schema_funciona_para_todas_las_acciones():
    capacidades = modulo_capacidades.listar_capacidades()
    for cap in capacidades:
        for accion in cap['actions']:
            resultado = EJECUTOR.invoke(app, ['schema', cap['name'], accion])
            assert resultado.exit_code == 0, (
                f'schema {cap["name"]} {accion} fallo: {resultado.stdout}'
            )
            datos = json.loads(resultado.stdout)
            assert datos['estado'] == 'correcto'


def test_describe_funciona_para_todas_las_capacidades():
    capacidades = modulo_capacidades.listar_capacidades()
    for cap in capacidades:
        resultado = EJECUTOR.invoke(app, ['describe', cap['name']])
        assert resultado.exit_code == 0, (
            f'describe {cap["name"]} fallo: {resultado.stdout}'
        )
        datos = json.loads(resultado.stdout)
        assert datos['capacidad']['name'] == cap['name']
        assert datos['capacidad']['clase'] == 'capability'


def test_clase_discovery():
    for nombre in ('capabilities', 'describe', 'schema'):
        assert modulo_capacidades.obtener_clase(nombre) == 'discovery'


def test_capacidades_filtradas_por_clase():
    resultado = EJECUTOR.invoke(app, ['capabilities', '--clase', 'capability'])
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert all(c.get('clase') == 'capability' for c in datos['capacidades'])
    assert datos['total'] == len(datos['capacidades'])

    resultado = EJECUTOR.invoke(app, ['capabilities', '--clase', 'discovery'])
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    nombres = {c['name'] for c in datos['capacidades']}
    assert nombres == {'capabilities', 'describe', 'schema'}
