# Pruebas de regresion del bloque P: preflight y reconciliacion.
import tempfile
from pathlib import Path

from devkit.core import safety


def test_preflight_pasa_con_espacio():
    d = Path(tempfile.mkdtemp())
    (d / 'test.txt').write_text('hello')
    # Create a simple manifest
    from devkit.core import runlog, workspace
    wid = workspace.workspace_id(d)
    id_ejec = runlog.iniciar_ejecucion('trim', 'aplicar', espacio_trabajo=str(d))
    ruta = safety.guardar_plan(id_ejec, 'trim', [], workspace_id=wid, workspace_root=str(d))
    # Preflight should pass
    assert safety.preflight_plan(ruta, str(d)) is True


def test_reconciliar_plan_completada():
    d = Path(tempfile.mkdtemp())
    origen = d / 'archivo.txt'
    destino = d / 'destino' / 'archivo.txt'
    origen.write_text('contenido')
    destino.parent.mkdir(parents=True)
    destino.write_text('contenido')
    origen.unlink()  # simulate completed move
    from devkit.core import runlog, workspace
    wid = workspace.workspace_id(d)
    id_ejec = runlog.iniciar_ejecucion('organize', 'aplicar', espacio_trabajo=str(d))
    accion = {
        'tipo': 'mover',
        'origen': str(origen),
        'destino': str(destino),
        'hash': safety.hash_contenido(destino),
        'tamano': destino.stat().st_size,
    }
    ruta = safety.guardar_plan(
        id_ejec, 'organize', [accion], workspace_id=wid, workspace_root=str(d)
    )
    rec = safety.reconciliar_plan(ruta, str(d))
    assert rec['completadas']
    assert not rec['pendientes']
    assert not rec['ambiguas']


def test_reconciliar_plan_pendiente():
    d = Path(tempfile.mkdtemp())
    origen = d / 'archivo.txt'
    destino = d / 'destino' / 'archivo.txt'
    origen.write_text('contenido')
    from devkit.core import runlog, workspace
    wid = workspace.workspace_id(d)
    id_ejec = runlog.iniciar_ejecucion('organize', 'aplicar', espacio_trabajo=str(d))
    accion = {
        'tipo': 'mover',
        'origen': str(origen),
        'destino': str(destino),
        'hash': 'abc123',
        'tamano': 9,
    }
    ruta = safety.guardar_plan(
        id_ejec, 'organize', [accion], workspace_id=wid, workspace_root=str(d)
    )
    rec = safety.reconciliar_plan(ruta, str(d))
    assert rec['pendientes']
    assert not rec['completadas']


def test_clasificar_error_windows():
    e = OSError('test')
    e.winerror = 32
    assert safety.clasificar_error_windows(e) == 'ARCHIVO_BLOQUEADO'
    e2 = OSError('test')
    e2.winerror = 5
    assert safety.clasificar_error_windows(e2) == 'PERMISO_DENEGADO'
    e3 = OSError('test')
    e3.winerror = 112
    assert safety.clasificar_error_windows(e3) == 'DISCO_LLENO'
