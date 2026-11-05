# Pruebas del flujo unificado de organize con manifiestos persistentes.
import json
from pathlib import Path

from typer.testing import CliRunner

from devkit.cli import app

EJECUTOR = CliRunner()


def _entorno(tmp_path):
    return {'DEVKIT_ESTADO': str(tmp_path / 'estado')}


def test_plan_guarda_manifiesto_persistente(tmp_path):
    origen = tmp_path / 'descargas'
    origen.mkdir()
    (origen / 'foto.jpg').write_bytes(b'\xff\xd8\xff\x00' + b'x' * 40)
    salida = EJECUTOR.invoke(app, ['organize', 'plan', str(origen)], env=_entorno(tmp_path))
    assert salida.exit_code == 0
    datos = json.loads(salida.stdout)
    ruta_plan = datos['plan_persistente']
    assert ruta_plan
    manifiesto = json.loads(Path(ruta_plan).read_text(encoding='utf-8'))
    assert manifiesto['estado'] == 'pendiente'
    assert manifiesto['total'] == 1
    fila = manifiesto['acciones'][0]
    assert fila['tipo'] == 'mover'
    assert fila['tamano'] > 0
    assert 'mtime' in fila


def test_aplicar_con_plan_persistente_no_reescanea(tmp_path):
    origen = tmp_path / 'descargas'
    origen.mkdir()
    (origen / 'doc.pdf').write_bytes(b'%PDF-1.4\n' + b'y' * 40)
    plan_salida = EJECUTOR.invoke(app, ['organize', 'plan', str(origen)], env=_entorno(tmp_path))
    ruta_plan = json.loads(plan_salida.stdout)['plan_persistente']
    # Se añade una nota nueva despues del plan, no debe entrar en la aplicacion.
    (origen / 'nota.md').write_text('tarde', encoding='utf-8')
    salida = EJECUTOR.invoke(
        app, ['organize', 'aplicar', str(origen), '--todos', '--plan', ruta_plan],
        env=_entorno(tmp_path),
    )
    assert salida.exit_code == 0
    datos = json.loads(salida.stdout)
    assert datos['total_movidos'] == 1
    assert any('doc.pdf' in m['origen'] for m in datos['movidos'])
    organizados = origen / 'Organizados'
    assert (organizados / '2026' / 'documento').is_dir()
    manifiesto = json.loads(Path(ruta_plan).read_text(encoding='utf-8'))
    assert manifiesto['estado'] == 'aplicado'


def test_aplicar_aborta_si_el_arbol_cambio(tmp_path):
    origen = tmp_path / 'descargas'
    origen.mkdir()
    fichero = origen / 'cancion.mp3'
    fichero.write_bytes(b'ID3\x03\x00' + b'z' * 40)
    plan_salida = EJECUTOR.invoke(app, ['organize', 'plan', str(origen)], env=_entorno(tmp_path))
    ruta_plan = json.loads(plan_salida.stdout)['plan_persistente']
    fichero.write_bytes(b'ID3\x03\x00' + b'z' * 60)
    salida = EJECUTOR.invoke(
        app, ['organize', 'aplicar', str(origen), '--todos', '--plan', ruta_plan],
        env=_entorno(tmp_path),
    )
    assert salida.exit_code == 2
    datos = json.loads(salida.stdout)
    assert datos['total_movidos'] == 0
    assert 'cambio' in datos['fallidos'][0]['detalle']
    assert fichero.exists()
    manifiesto = json.loads(Path(ruta_plan).read_text(encoding='utf-8'))
    assert manifiesto['estado'] == 'fallido'


def test_aplicar_no_pisa_un_destino_ocupado(tmp_path):
    origen = tmp_path / 'descargas'
    origen.mkdir()
    (origen / 'foto.jpg').write_bytes(b'\xff\xd8\xff\x00' + b'x' * 40)
    plan_salida = EJECUTOR.invoke(app, ['organize', 'plan', str(origen)], env=_entorno(tmp_path))
    ruta_plan = json.loads(plan_salida.stdout)['plan_persistente']
    datos_plan = json.loads(Path(ruta_plan).read_text(encoding='utf-8'))
    destino = Path(datos_plan['acciones'][0]['destino'])
    destino.parent.mkdir(parents=True)
    destino.write_bytes(b'\xff\xd8\xff\x00' + b'w' * 40)
    salida = EJECUTOR.invoke(
        app, ['organize', 'aplicar', str(origen), '--todos', '--plan', ruta_plan],
        env=_entorno(tmp_path),
    )
    assert salida.exit_code == 2
    datos = json.loads(salida.stdout)
    assert datos['total_movidos'] == 0
    assert 'el destino ya existe' in datos['fallidos'][0]['detalle']
    contenido = destino.read_bytes()
    assert contenido == b'\xff\xd8\xff\x00' + b'w' * 40
    assert (origen / 'foto.jpg').exists()
    manifiesto = json.loads(Path(ruta_plan).read_text(encoding='utf-8'))
    assert manifiesto['estado'] == 'fallido'
