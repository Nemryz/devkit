# Pruebas de trazabilidad del journal transaccional y de su recuperacion.
import json
import subprocess
import sys

from devkit.core import paths, runlog

CODIGO_HERMANO = (
    'from devkit.core import runlog\n'
    'for i in range(30):\n'
    '    runlog.registrar_hito("pool-" + str(i), "carga", "linea", "COMPLETED", "concurrente")\n'
)


def test_journal_registra_workspace_del_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv('DEVKIT_ESTADO', str(tmp_path / 'estado'))
    monkeypatch.setenv('DEVKIT_WORKSPACE', str(tmp_path / 'notas'))
    runlog.registrar_hito('x-1', 'prueba', 'accion', 'PENDING', detalle='hito con espacio')
    linea = paths.ruta_journal().read_text(encoding='utf-8').strip().splitlines()[-1]
    datos = json.loads(linea)
    assert datos['espacio_trabajo'] == str(tmp_path / 'notas')


def test_journal_distingue_espacios_por_parametro(tmp_path, monkeypatch):
    monkeypatch.setenv('DEVKIT_ESTADO', str(tmp_path / 'estado'))
    monkeypatch.setenv('DEVKIT_WORKSPACE', str(tmp_path / 'env'))
    runlog.registrar_hito('x-2', 'prueba', 'accion', 'PENDING', espacio_trabajo='C:/otro/lugar')
    linea = paths.ruta_journal().read_text(encoding='utf-8').strip().splitlines()[-1]
    datos = json.loads(linea)
    assert datos['espacio_trabajo'] == 'C:/otro/lugar'


def test_journal_guarda_id_de_plan(tmp_path, monkeypatch):
    monkeypatch.setenv('DEVKIT_ESTADO', str(tmp_path / 'estado'))
    id_ejec = runlog.iniciar_ejecucion(
        'prueba', 'aplicar', espacio_trabajo='C:/notas', id_plan='prueba-abcd'
    )
    runlog.registrar_hito(
        id_ejec, 'prueba', 'aplicar', 'RUNNING', espacio_trabajo='C:/notas', id_plan='prueba-abcd'
    )
    lineas = paths.ruta_journal().read_text(encoding='utf-8').strip().splitlines()
    del_ident = [
        json.loads(linea)
        for linea in lineas
        if linea.strip() and json.loads(linea)['id_ejecucion'] == id_ejec
    ]
    assert len(del_ident) == 2
    assert all(datos['id_plan'] == 'prueba-abcd' for datos in del_ident)
    assert all(datos['espacio_trabajo'] == 'C:/notas' for datos in del_ident)


def test_registrar_ejecucion_cierra_con_estado_estable(tmp_path, monkeypatch):
    monkeypatch.setenv('DEVKIT_ESTADO', str(tmp_path / 'estado'))
    runlog.registrar_ejecucion('prueba', ['accion'], 0.0, 0, 0, 'todo bien')
    lineas = paths.ruta_journal().read_text(encoding='utf-8').strip().splitlines()
    estados = [json.loads(linea)['estado'] for linea in lineas if linea.strip()]
    assert estados[-1] == 'COMPLETED'
    assert runlog.contar_ejecuciones() >= 1


def test_recuperar_interrumpidas_cierra_estados_abiertos(tmp_path, monkeypatch):
    monkeypatch.setenv('DEVKIT_ESTADO', str(tmp_path / 'estado'))
    id_pendiente = runlog.iniciar_ejecucion('prueba', 'accion')
    runlog.registrar_hito('x-run2', 'prueba', 'accion', 'RUNNING', detalle='a medio hacer')
    abiertas = {datos['id_ejecucion'] for datos in runlog.ejecuciones_abiertas()}
    assert id_pendiente in abiertas
    assert 'x-run2' in abiertas
    recuperadas = runlog.recuperar_interrumpidas()
    assert id_pendiente in recuperadas
    assert 'x-run2' in recuperadas
    assert runlog.ejecuciones_abiertas() == []


def test_recuperacion_anota_interrupted_en_el_journal(tmp_path, monkeypatch):
    monkeypatch.setenv('DEVKIT_ESTADO', str(tmp_path / 'estado'))
    ident = runlog.iniciar_ejecucion('prueba', 'accion')
    runlog.recuperar_interrumpidas()
    lineas = paths.ruta_journal().read_text(encoding='utf-8').strip().splitlines()
    estados_ident = [
        json.loads(linea)['estado']
        for linea in lineas
        if linea.strip() and json.loads(linea)['id_ejecucion'] == ident
    ]
    assert estados_ident[0] == 'PENDING'
    assert estados_ident[-1] == 'INTERRUPTED'


def test_registrar_ejecucion_reutiliza_id_y_propaga_cierre(tmp_path, monkeypatch):
    # El cierre ya no abre su propio id, reutiliza el de la ejecucion iniciada.
    monkeypatch.setenv('DEVKIT_ESTADO', str(tmp_path / 'estado'))
    id_ejec = runlog.iniciar_ejecucion('prueba', 'aplicar', espacio_trabajo='C:/notas')
    runlog.registrar_ejecucion(
        'prueba', ['aplicar'], 0.0, 0, 0, 'cierre', espacio_trabajo='C:/notas', id_ejecucion=id_ejec
    )
    lineas = [
        json.loads(linea)
        for linea in paths.ruta_journal().read_text(encoding='utf-8').strip().splitlines()
        if linea.strip()
    ]
    assert [datos['id_ejecucion'] for datos in lineas] == [id_ejec, id_ejec]
    assert lineas[0]['estado'] == 'PENDING'
    assert lineas[1]['estado'] == 'COMPLETED'
    assert lineas[1]['espacio_trabajo'] == 'C:/notas'
    assert runlog.ejecuciones_abiertas() == []


def test_recuperar_interrumpidas_propaga_id_plan_y_ultima_accion(tmp_path, monkeypatch):
    # El corte anota el id del plan y el origen de la ultima accion en curso.
    monkeypatch.setenv('DEVKIT_ESTADO', str(tmp_path / 'estado'))
    id_ejec = runlog.iniciar_ejecucion(
        'trim', 'aplicar', espacio_trabajo='C:/notas', id_plan='trim-abcd'
    )
    runlog.registrar_hito(
        id_ejec, 'trim', 'accion', 'COMPLETED', 'aplicada', origen='C:/notas/cache',
        espacio_trabajo='C:/notas', id_plan='trim-abcd', nivel='accion',
    )
    recuperadas = runlog.recuperar_interrumpidas()
    assert recuperadas == [id_ejec]
    lineas = [
        json.loads(linea)
        for linea in paths.ruta_journal().read_text(encoding='utf-8').strip().splitlines()
        if linea.strip() and json.loads(linea)['id_ejecucion'] == id_ejec
    ]
    corte = lineas[-1]
    assert corte['estado'] == 'INTERRUPTED'
    assert corte['id_plan'] == 'trim-abcd'
    assert 'C:/notas/cache' in corte['detalle']
    assert runlog.ejecuciones_abiertas() == []


def test_escrituras_concurrentes_no_corrompen_el_journal(tmp_path, monkeypatch):
    # Dos procesos hermanos reales escriben al mismo tiempo con Popen y nada se rompe.
    estado = tmp_path / 'estado'
    monkeypatch.setenv('DEVKIT_ESTADO', str(estado))
    entornos = {**__import__('os').environ, 'DEVKIT_ESTADO': str(estado)}
    hermanos = [
        subprocess.Popen(
            [sys.executable, '-c', CODIGO_HERMANO],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=entornos,
        )
        for _ in range(2)
    ]
    for hermano in hermanos:
        salida, errores = hermano.communicate()
        assert salida == ''
        assert hermano.returncode == 0, errores
    ruta = estado / 'journal' / 'ejecuciones.jsonl'
    linea_invalida = 0
    total = 0
    with ruta.open('r', encoding='utf-8') as archivo:
        for linea in archivo:
            if not linea.strip():
                continue
            total += 1
            try:
                json.loads(linea)
            except json.JSONDecodeError:
                linea_invalida += 1
    assert linea_invalida == 0
    assert total == 60
