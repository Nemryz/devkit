# Pruebas de regresion del bloque P cerrado: reintentos, aborto y reconciliacion.
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devkit.cli import app
from devkit.core import politica, runlog, safety, workspace
from devkit.errors import ErrorIntegridad

EJECUTOR = CliRunner()
POLITICA_TRIM = politica.derivar('trim', 'aplicar', forzada=True)
POLITICA_ORGANIZE = politica.derivar('organize', 'aplicar', confirmada=True)


def _entorno(tmp_path: Path) -> dict:
    return {'DEVKIT_ESTADO': str(tmp_path / 'estado')}


def _manifiesto(
    base: Path,
    acciones: list[dict],
    identificador: str = 'plan-organize',
    herramienta: str = 'organize',
) -> Path:
    # Guarda un manifiesto firmado y ligado al workspace de la raiz.
    ident = workspace.workspace_id(base)
    return safety.guardar_plan(
        identificador,
        herramienta,
        acciones,
        destino_dir=base / 'planes',
        workspace_id=ident,
        workspace_root=str(base),
    )


def _accion_mover(base: Path, nombre: str = 'archivo.txt') -> tuple[dict, Path, Path]:
    # Construye una accion de movimiento con tamano y hash coherentes.
    origen = base / nombre
    destino = base / 'destino' / nombre
    origen.write_text('contenido', encoding='utf-8')
    accion = {
        'tipo': 'mover',
        'origen': str(origen),
        'destino': str(destino),
        'tamano': origen.stat().st_size,
        'hash': safety.hash_contenido(origen),
    }
    return accion, origen, destino


def _fallo_windows(codigo: int, texto: str = 'fallo simulado') -> OSError:
    fallo = OSError(texto)
    fallo.winerror = codigo
    return fallo


def _hitos(ruta_plan: Path) -> list[dict]:
    return runlog.hitos_del_plan(ruta_plan.stem)


def test_reintenta_bloqueo_transitorio(tmp_path, monkeypatch):
    base = tmp_path
    accion, origen, destino = _accion_mover(base)
    ruta_plan = _manifiesto(base, [accion])
    original = safety._ejecutar_accion
    intentos = {'n': 0}

    def falla_dos_veces(accion_actual):
        intentos['n'] += 1
        if intentos['n'] <= 2:
            raise _fallo_windows(32, 'archivo bloqueado')
        return original(accion_actual)

    monkeypatch.setattr(safety, '_ejecutar_accion', falla_dos_veces)
    monkeypatch.setattr(safety, '_espera_reintento', lambda intento: 0)
    resultado = safety.aplicar_manifiesto(
        ruta_plan, 'organize', espacio_trabajo=str(base),
        politica=POLITICA_ORGANIZE,
    )
    assert resultado['codigo'] == 0
    assert destino.exists()
    assert not origen.exists()
    reintentos = [h for h in _hitos(ruta_plan) if h['estado'] == 'REINTENTO']
    assert len(reintentos) == 2
    assert all(h['codigo_error'] == 'ARCHIVO_BLOQUEADO' for h in reintentos)


def test_reintento_agotado_falla_sin_mover(tmp_path, monkeypatch):
    base = tmp_path
    accion, origen, destino = _accion_mover(base)
    ruta_plan = _manifiesto(base, [accion])

    def siempre_bloqueado(accion_actual):
        raise _fallo_windows(33, 'archivo bloqueado')

    monkeypatch.setattr(safety, '_ejecutar_accion', siempre_bloqueado)
    monkeypatch.setattr(safety, '_espera_reintento', lambda intento: 0)
    resultado = safety.aplicar_manifiesto(
        ruta_plan, 'organize', espacio_trabajo=str(base),
        politica=POLITICA_ORGANIZE,
    )
    assert resultado['codigo'] == 2
    assert origen.exists()
    assert not destino.exists()
    hitos = _hitos(ruta_plan)
    assert len([h for h in hitos if h['estado'] == 'REINTENTO']) == 2
    fallos = [h for h in hitos if h['estado'] == 'FAILED']
    assert len(fallos) == 1
    assert fallos[0]['codigo_error'] == 'ARCHIVO_BLOQUEADO'


def test_permiso_denegado_continua_con_la_siguiente(tmp_path, monkeypatch):
    base = tmp_path
    primera, origen_uno, destino_uno = _accion_mover(base, 'uno.txt')
    segunda, origen_dos, destino_dos = _accion_mover(base, 'dos.txt')
    ruta_plan = _manifiesto(base, [primera, segunda])
    original = safety._ejecutar_accion

    def deniega_la_primera(accion_actual):
        if accion_actual['origen'] == str(origen_uno):
            raise _fallo_windows(5, 'acceso denegado')
        return original(accion_actual)

    monkeypatch.setattr(safety, '_ejecutar_accion', deniega_la_primera)
    resultado = safety.aplicar_manifiesto(
        ruta_plan, 'organize', espacio_trabajo=str(base),
        politica=POLITICA_ORGANIZE,
    )
    assert resultado['codigo'] == 2
    assert resultado['estado_plan'] == 'parcial'
    assert origen_uno.exists() and not destino_uno.exists()
    assert destino_dos.exists() and not origen_dos.exists()
    codigos = {f['codigo_error'] for f in resultado['fallidos']}
    assert 'PERMISO_DENEGADO' in codigos


def test_disco_lleno_aborta_el_lote(tmp_path, monkeypatch):
    base = tmp_path
    primera, origen_uno, destino_uno = _accion_mover(base, 'uno.txt')
    segunda, origen_dos, destino_dos = _accion_mover(base, 'dos.txt')
    ruta_plan = _manifiesto(base, [primera, segunda])
    llamadas = []

    def disco_lleno(accion_actual):
        llamadas.append(accion_actual['origen'])
        raise _fallo_windows(112, 'no queda espacio')

    monkeypatch.setattr(safety, '_ejecutar_accion', disco_lleno)
    resultado = safety.aplicar_manifiesto(
        ruta_plan, 'organize', espacio_trabajo=str(base),
        politica=POLITICA_ORGANIZE,
    )
    assert resultado['codigo'] == 2
    assert len(llamadas) == 1
    assert origen_uno.exists() and origen_dos.exists()
    assert not destino_uno.exists() and not destino_dos.exists()
    omitidos = [h for h in _hitos(ruta_plan) if h['estado'] == 'OMITIDO']
    assert len(omitidos) == 1
    assert omitidos[0]['codigo_error'] == 'DISCO_LLENO'


def test_preflight_aborta_antes_de_mover(tmp_path):
    base = tmp_path
    accion, origen, destino = _accion_mover(base)
    accion['tamano'] = 10**18
    ruta_plan = _manifiesto(base, [accion])
    with pytest.raises(ErrorIntegridad) as error:
        safety.aplicar_manifiesto(
            ruta_plan, 'organize', espacio_trabajo=str(base),
            politica=POLITICA_ORGANIZE,
        )
    assert 'DISCO_LLENO' in str(error.value)
    assert origen.exists()
    assert not destino.exists()
    assert _hitos(ruta_plan) == []


def _plan_de_cinco_estados(base: Path) -> tuple[Path, dict[str, Path]]:
    # Compone un manifiesto con una accion en cada estado de reconciliacion.
    completada_origen = base / 'completada.txt'
    completada_destino = base / 'destino' / 'completada.txt'
    completada_destino.parent.mkdir(parents=True, exist_ok=True)
    completada_destino.write_text('contenido', encoding='utf-8')
    pendiente_origen = base / 'pendiente.txt'
    pendiente_origen.write_text('contenido', encoding='utf-8')
    ambigua_origen = base / 'ambigua.txt'
    ambigua_origen.write_text('contenido', encoding='utf-8')
    ambigua_destino = base / 'destino' / 'ambigua.txt'
    ambigua_destino.write_text('contenido', encoding='utf-8')
    omitida_origen = base / 'omitida.txt'
    omitida_origen.write_text('contenido', encoding='utf-8')
    acciones = [
        {
            'tipo': 'mover',
            'origen': str(completada_origen),
            'destino': str(completada_destino),
            'hash': safety.hash_contenido(completada_destino),
        },
        {
            'tipo': 'mover',
            'origen': str(pendiente_origen),
            'destino': str(base / 'destino' / 'pendiente.txt'),
        },
        {
            'tipo': 'mover',
            'origen': str(ambigua_origen),
            'destino': str(ambigua_destino),
        },
        {
            'tipo': 'mover',
            'origen': str(base / 'inconsistente.txt'),
            'destino': str(base / 'destino' / 'inconsistente.txt'),
        },
        {
            'tipo': 'mover',
            'origen': str(omitida_origen),
            'destino': str(base / 'destino' / 'omitida.txt'),
        },
    ]
    ruta_plan = _manifiesto(base, acciones, 'reconciliar')
    runlog.registrar_hito(
        'ejecucion-previa',
        'trim',
        'accion',
        'OMITIDO',
        'sin autorizar',
        origen=str(omitida_origen),
        destino=str(base / 'destino' / 'omitida.txt'),
        id_plan='reconciliar',
        nivel='accion',
    )
    return ruta_plan, {
        'completada': completada_destino,
        'pendiente': pendiente_origen,
        'ambigua': ambigua_origen,
        'omitida': omitida_origen,
    }


def test_reconciliacion_cubre_los_cinco_estados(tmp_path):
    base = tmp_path
    ruta_plan, rutas = _plan_de_cinco_estados(base)
    reconciliacion = safety.reconciliar_plan(ruta_plan, str(base))
    assert len(reconciliacion['completadas']) == 1
    assert len(reconciliacion['pendientes']) == 1
    assert len(reconciliacion['ambiguas']) == 1
    assert len(reconciliacion['inconsistentes']) == 1
    assert len(reconciliacion['omitidas']) == 1
    assert reconciliacion['total'] == 5
    assert reconciliacion['pendientes'][0]['origen'] == str(rutas['pendiente'])
    assert reconciliacion['omitidas'][0]['origen'] == str(rutas['omitida'])


def test_hash_distinto_es_ambigua(tmp_path):
    base = tmp_path
    destino = base / 'destino' / 'archivo.txt'
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text('otro contenido', encoding='utf-8')
    accion = {
        'tipo': 'mover',
        'origen': str(base / 'archivo.txt'),
        'destino': str(destino),
        'hash': 'firma-que-no-coincide',
    }
    ruta_plan = _manifiesto(base, [accion])
    reconciliacion = safety.reconciliar_plan(ruta_plan, str(base))
    assert len(reconciliacion['ambiguas']) == 1
    assert not reconciliacion['completadas']


def test_journal_completed_sin_postcondicion_es_inconsistente(tmp_path):
    base = tmp_path
    accion, origen, _ = _accion_mover(base)
    ruta_plan = _manifiesto(base, [accion])
    runlog.registrar_hito(
        'ejecucion-previa',
        'trim',
        'accion',
        'COMPLETED',
        'aplicada',
        origen=str(origen),
        destino=str(accion['destino']),
        id_plan=ruta_plan.stem,
        nivel='accion',
    )
    reconciliacion = safety.reconciliar_plan(ruta_plan, str(base))
    assert len(reconciliacion['inconsistentes']) == 1


def test_muerte_antes_de_la_accion_queda_pendiente(tmp_path):
    base = tmp_path
    accion, origen, destino = _accion_mover(base)
    ruta_plan = _manifiesto(base, [accion])
    runlog.registrar_hito(
        'ejecucion-previa',
        'trim',
        'accion',
        'PENDING',
        'en curso',
        origen=str(origen),
        destino=str(destino),
        id_plan=ruta_plan.stem,
        nivel='accion',
    )
    reconciliacion = safety.reconciliar_plan(ruta_plan, str(base))
    assert len(reconciliacion['pendientes']) == 1
    assert len(reconciliacion['inconsistentes']) == 0


def test_muerte_despues_de_la_accion_queda_completada(tmp_path):
    base = tmp_path
    accion, origen, destino = _accion_mover(base)
    destino.parent.mkdir(parents=True, exist_ok=True)
    origen.replace(destino)
    ruta_plan = _manifiesto(base, [accion])
    runlog.registrar_hito(
        'ejecucion-previa',
        'trim',
        'accion',
        'PENDING',
        'en curso',
        origen=str(origen),
        destino=str(destino),
        id_plan=ruta_plan.stem,
        nivel='accion',
    )
    reconciliacion = safety.reconciliar_plan(ruta_plan, str(base))
    assert len(reconciliacion['completadas']) == 1
    assert len(reconciliacion['pendientes']) == 0


def test_reanudar_rechaza_ambiguas(tmp_path):
    base = tmp_path
    accion, origen, destino = _accion_mover(base)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text('contenido', encoding='utf-8')
    ruta_plan = _manifiesto(base, [accion])
    with pytest.raises(ErrorIntegridad) as error:
        safety.aplicar_manifiesto(
            ruta_plan, 'organize', espacio_trabajo=str(base), reanudar=True,
            politica=POLITICA_ORGANIZE,
        )
    assert 'RECONCILIACION_REQUIERE_INTERVENCION' in str(error.value)
    assert origen.exists()
    assert destino.exists()


def test_reanudar_ejecuta_solo_pendientes(tmp_path):
    base = tmp_path
    resuelta_origen = base / 'resuelta.txt'
    resuelta_destino = base / 'destino' / 'resuelta.txt'
    resuelta_destino.parent.mkdir(parents=True, exist_ok=True)
    resuelta_destino.write_text('contenido', encoding='utf-8')
    pendiente, pendiente_origen, pendiente_destino = _accion_mover(base, 'pendiente.txt')
    acciones = [
        {
            'tipo': 'mover',
            'origen': str(resuelta_origen),
            'destino': str(resuelta_destino),
            'hash': safety.hash_contenido(resuelta_destino),
        },
        pendiente,
    ]
    ruta_plan = _manifiesto(base, acciones)
    resultado = safety.aplicar_manifiesto(
        ruta_plan, 'organize', espacio_trabajo=str(base), reanudar=True,
        politica=POLITICA_ORGANIZE,
    )
    assert resultado['codigo'] == 0
    assert resultado['ya_resueltas'] == 1
    assert len(resultado['movidos']) == 1
    assert resultado['movidos'][0]['origen'] == str(pendiente_origen)
    assert pendiente_destino.exists()
    assert resuelta_destino.read_text(encoding='utf-8') == 'contenido'


def test_reanudar_sin_pendientes_no_abre_ejecucion(tmp_path):
    base = tmp_path
    accion, origen, destino = _accion_mover(base)
    destino.parent.mkdir(parents=True, exist_ok=True)
    origen.replace(destino)
    ruta_plan = _manifiesto(base, [accion])
    resultado = safety.aplicar_manifiesto(
        ruta_plan, 'organize', espacio_trabajo=str(base), reanudar=True,
        politica=POLITICA_ORGANIZE,
    )
    assert resultado['codigo'] == 0
    assert resultado['estado_plan'] == 'reconciliado'
    assert resultado['id_ejecucion'] == ''
    assert resultado['ya_resueltas'] == 1


def test_reanudar_sin_plan_falla_en_el_cli(tmp_path):
    origen = tmp_path / 'descargas'
    origen.mkdir()
    resultado = EJECUTOR.invoke(
        app,
        ['trim', 'aplicar', str(origen), '--forzar', '--reanudar'],
        env=_entorno(tmp_path),
    )
    assert resultado.exit_code == 2
    datos = json.loads(resultado.stdout)
    assert datos['estado'] == 'error'
    assert 'reanudar exige un plan' in datos['detalle']


def test_reanudar_ambiguo_falla_en_el_cli(tmp_path):
    origen = tmp_path / 'descargas'
    origen.mkdir()
    archivo = origen / 'foto.jpg'
    archivo.write_bytes(b'\xff\xd8\xff\x00' + b'x' * 40)
    salida = EJECUTOR.invoke(
        app, ['organize', 'plan', str(origen)], env=_entorno(tmp_path)
    )
    assert salida.exit_code == 0
    ruta_plan = json.loads(salida.stdout)['plan_persistente']
    manifiesto = json.loads(Path(ruta_plan).read_text(encoding='utf-8'))
    destino = Path(manifiesto['acciones'][0]['destino'])
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(archivo.read_bytes())
    salida = EJECUTOR.invoke(
        app,
        [
            'organize', 'aplicar', str(origen),
            '--todos', '--si', '--plan', ruta_plan, '--reanudar',
        ],
        env=_entorno(tmp_path),
    )
    assert salida.exit_code == 2
    datos = json.loads(salida.stdout)
    assert 'RECONCILIACION_REQUIERE_INTERVENCION' in datos['detalle']
    assert archivo.exists()
    assert destino.exists()


def test_papelera_reintenta_si_el_sistema_bloquea(tmp_path, monkeypatch):
    # La papelera debe conservar el winerror para que el reintento sea posible.
    base = tmp_path
    origen = base / 'basura.txt'
    origen.write_text('contenido', encoding='utf-8')
    ruta_plan = _manifiesto(
        base, [{'tipo': 'papelera', 'origen': str(origen)}],
        'plan-trim', herramienta='trim',
    )
    intentos = {'n': 0}

    def bloquea_la_primera(ruta):
        intentos['n'] += 1
        if intentos['n'] == 1:
            raise _fallo_windows(32, 'archivo bloqueado')
        origen.unlink()

    monkeypatch.setattr(safety, 'mover_a_papelera_from_safety', bloquea_la_primera)
    monkeypatch.setattr(safety, '_espera_reintento', lambda intento: 0)
    resultado = safety.aplicar_manifiesto(
        ruta_plan, 'trim', espacio_trabajo=str(base),
        politica=POLITICA_TRIM,
    )
    assert resultado['codigo'] == 0
    assert intentos['n'] == 2
    assert not origen.exists()
    hitos = _hitos(ruta_plan)
    assert len([h for h in hitos if h['estado'] == 'REINTENTO']) == 1
    assert hitos[-1]['estado'] == 'COMPLETED'


def test_papelera_denegada_se_clasifica_como_permiso(tmp_path, monkeypatch):
    # Un acceso denegado no se reintenta y queda con su codigo estable.
    base = tmp_path
    origen = base / 'basura.txt'
    origen.write_text('contenido', encoding='utf-8')
    ruta_plan = _manifiesto(
        base, [{'tipo': 'papelera', 'origen': str(origen)}],
        'plan-trim', herramienta='trim',
    )

    def deniega(ruta):
        raise _fallo_windows(5, 'acceso denegado')

    monkeypatch.setattr(safety, 'mover_a_papelera_from_safety', deniega)
    resultado = safety.aplicar_manifiesto(
        ruta_plan, 'trim', espacio_trabajo=str(base),
        politica=POLITICA_TRIM,
    )
    assert resultado['codigo'] == 2
    assert resultado['fallidos'][0]['codigo_error'] == 'PERMISO_DENEGADO'
    assert origen.exists()
    assert not [h for h in _hitos(ruta_plan) if h['estado'] == 'REINTENTO']

