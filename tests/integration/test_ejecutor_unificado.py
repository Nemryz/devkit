# Pruebas del ejecutor unico de manifiestos compartido por trim, dedupe y organize.
import json
import os
import time
from pathlib import Path

from typer.testing import CliRunner

from devkit.cli import app
from devkit.core import runlog, safety
from devkit.tools import dedupe, organize, trim

EJECUTOR = CliRunner()


def crear_cache(raiz: Path, nombre: str, dias=10):
    # Crea una carpeta limpiable con un archivo y una fecha vieja.
    destino = raiz / nombre
    destino.mkdir(parents=True, exist_ok=True)
    (destino / 'dato.pyc').write_bytes(b'x' * 100)
    marca = time.time() - dias * 86400
    os.utime(destino, (marca, marca))
    return destino


def crear_archivo(ruta: Path, contenido=b'x' * 100, dias=40):
    # Crea un archivo con fecha vieja para que entre en el escaneo de duplicados.
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    marca = time.time() - dias * 86400
    os.utime(ruta, (marca, marca))
    return ruta


def test_trim_aplica_el_manifiesto_guardado_sin_reescanear(tmp_path):
    # Un cache creado despues del escaneo no entra en la aplicacion del manifiesto.
    raiz = tmp_path / 'proyecto'
    raiz.mkdir()
    crear_cache(raiz, '__pycache__')
    escaneo = trim.escanear_trim(raiz, edad_dias=7)
    assert escaneo['total'] >= 1
    tardio = crear_cache(raiz, 'htmlcov')
    ruta_plan = Path(escaneo['plan_persistente'])
    resultado = trim.aplicar_trim(raiz, edad_dias=7, plan=ruta_plan)
    assert resultado['estado'] == 'correcto'
    assert resultado['total_movidos'] == escaneo['total']
    assert tardio.exists()
    datos_plan = json.loads(ruta_plan.read_text(encoding='utf-8'))
    assert datos_plan['estado'] == 'aplicado'


def test_trim_acepta_plan_por_la_linea(estado_temporal, tmp_path):
    raiz = tmp_path / 'proyecto'
    raiz.mkdir()
    crear_cache(raiz, '__pycache__')
    salida = EJECUTOR.invoke(
        app, ['trim', 'escanear', str(raiz)], env={'DEVKIT_ESTADO': str(estado_temporal)}
    )
    assert salida.exit_code == 0
    ruta_plan = json.loads(salida.stdout)['plan_persistente']
    aplicado = EJECUTOR.invoke(
        app, ['trim', 'aplicar', str(raiz), '--forzar', '--plan', ruta_plan],
        env={'DEVKIT_ESTADO': str(estado_temporal)},
    )
    assert aplicado.exit_code == 0
    datos = json.loads(aplicado.stdout)
    assert datos['total_movidos'] >= 1
    assert datos['plan_persistente'] == ruta_plan


def test_dedupe_aplica_el_manifiesto_guardado_sin_reescanear(tmp_path):
    # Un duplicado creado despues del escaneo no entra en la aplicacion del manifiesto.
    raiz = tmp_path / 'catalogos'
    raiz.mkdir()
    crear_archivo(raiz / 'a/uno.jpg', b'img' * 100)
    crear_archivo(raiz / 'b/dos.jpg', b'img' * 100)
    escaneo = dedupe.escanear_dedupe(raiz, edad_dias=30)
    assert escaneo['total'] == 1
    tardio = crear_archivo(raiz / 'c/tres.jpg', b'img' * 100)
    ruta_plan = Path(escaneo['plan_persistente'])
    resultado = dedupe.aplicar_dedupe(raiz, edad_dias=30, plan=ruta_plan)
    assert resultado['estado'] == 'correcto'
    assert resultado['total_movidos'] == 1
    assert tardio.exists()
    datos_plan = json.loads(ruta_plan.read_text(encoding='utf-8'))
    assert datos_plan['estado'] == 'aplicado'


def test_dedupe_acepta_plan_por_la_linea(estado_temporal, tmp_path):
    raiz = tmp_path / 'catalogos'
    raiz.mkdir()
    crear_archivo(raiz / 'a/uno.jpg', b'img' * 100)
    crear_archivo(raiz / 'b/dos.jpg', b'img' * 100)
    salida = EJECUTOR.invoke(
        app, ['dedupe', 'escanear', str(raiz)], env={'DEVKIT_ESTADO': str(estado_temporal)}
    )
    assert salida.exit_code == 0
    ruta_plan = json.loads(salida.stdout)['plan_persistente']
    aplicado = EJECUTOR.invoke(
        app, ['dedupe', 'aplicar', str(raiz), '--forzar', '--plan', ruta_plan],
        env={'DEVKIT_ESTADO': str(estado_temporal)},
    )
    assert aplicado.exit_code == 0
    datos = json.loads(aplicado.stdout)
    assert datos['total_movidos'] == 1


def test_fallo_en_una_accion_deja_el_estado_parcial(tmp_path, monkeypatch):
    # La tanda sigue con el resto de acciones y el manifiesto queda en parcial.
    raiz = tmp_path / 'proyecto'
    raiz.mkdir()
    crear_cache(raiz, '__pycache__')
    crear_cache(raiz, 'dist')
    movimientos = []

    def mediador(ruta):
        if 'dist' in str(ruta):
            raise RuntimeError('bloqueo simulado')
        movimientos.append(str(ruta))

    monkeypatch.setattr(safety, 'mover_a_papelera_from_safety', mediador)
    resultado = trim.aplicar_trim(raiz, edad_dias=7)
    assert resultado['estado'] == 'error'
    assert resultado['total_movidos'] == 1
    assert len(resultado['fallidos']) == 1
    assert resultado['fallidos'][0]['detalle'] == 'bloqueo simulado'
    assert resultado['estado_plan'] == 'parcial'
    ruta_plan = Path(resultado['plan_persistente'])
    datos_plan = json.loads(ruta_plan.read_text(encoding='utf-8'))
    assert datos_plan['estado'] == 'parcial'
    assert len(movimientos) == 1


def test_gancho_de_autorizacion_omite_acciones_y_deja_parcial(tmp_path):
    # Las acciones sin autorizacion no se tocan y el manifiesto acaba en parcial.
    raiz = tmp_path / 'descargas'
    raiz.mkdir()
    crear_archivo(raiz / 'foto.jpg', b'\xff\xd8\xff\x00' + b'x' * 40, dias=400)
    crear_archivo(raiz / 'doc.pdf', b'%PDF-1.4' + b'y' * 40, dias=400)
    escaneo = organize.escanear_organize(raiz)
    ruta_plan = Path(escaneo['plan_persistente'])
    resultado = safety.aplicar_manifiesto(
        ruta_plan, 'organize', espacio_trabajo=str(raiz), autorizar=lambda accion: False
    )
    assert resultado['estado_plan'] == 'parcial'
    assert resultado['movidos'] == []
    assert resultado['fallidos'] == []
    assert len(resultado['omitidos']) == 2
    assert (raiz / 'foto.jpg').exists()
    datos_plan = json.loads(ruta_plan.read_text(encoding='utf-8'))
    assert datos_plan['estado'] == 'parcial'


def test_reanudacion_tras_interrupcion_termina_el_resto(estado_temporal, tmp_path):
    # Tras un corte el manifiesto sigue aplicable y el doctor lo recupera coherentemente.
    raiz = tmp_path / 'proyecto'
    raiz.mkdir()
    cache = crear_cache(raiz, '__pycache__')
    escaneo = trim.escanear_trim(raiz, edad_dias=7)
    ruta_plan = Path(escaneo['plan_persistente'])
    id_ejec = runlog.iniciar_ejecucion(
        'trim', 'aplicar', espacio_trabajo=str(raiz), id_plan=ruta_plan.stem
    )
    runlog.registrar_hito(
        id_ejec, 'trim', 'accion', 'COMPLETED', 'aplicada', origen=str(cache / 'dato.pyc'),
        espacio_trabajo=str(raiz), id_plan=ruta_plan.stem, nivel='accion',
    )
    recuperadas = runlog.recuperar_interrumpidas()
    assert recuperadas == [id_ejec]
    lineas = [
        json.loads(linea)
        for linea in runlog.ruta_journal().read_text(encoding='utf-8').strip().splitlines()
        if linea.strip() and json.loads(linea)['id_ejecucion'] == id_ejec
    ]
    corte = lineas[-1]
    assert corte['estado'] == 'INTERRUPTED'
    assert corte['id_plan'] == ruta_plan.stem
    assert 'ultima accion' in corte['detalle']
    resultado = safety.aplicar_manifiesto(ruta_plan, 'trim', espacio_trabajo=str(raiz))
    assert resultado['estado_plan'] == 'aplicado'
    assert runlog.ejecuciones_abiertas() == []


def test_aplicar_deja_un_solo_id_por_ejecucion_y_cero_pendientes(estado_temporal, tmp_path):
    # Ninguna ejecucion queda abierta y cada id tiene PENDING y cierre emparejados.
    raiz = tmp_path / 'proyecto'
    raiz.mkdir()
    crear_cache(raiz, '__pycache__')
    resultado = trim.aplicar_trim(raiz, edad_dias=7)
    assert resultado['estado'] == 'correcto'
    lineas = [
        json.loads(linea)
        for linea in runlog.ruta_journal().read_text(encoding='utf-8').strip().splitlines()
        if linea.strip()
    ]
    parejas: dict[str, list] = {}
    for datos in lineas:
        if datos.get('nivel') == 'accion':
            continue
        parejas.setdefault(datos['id_ejecucion'], []).append(datos['estado'])
    assert parejas
    for estados in parejas.values():
        assert len(estados) == 2
        assert estados[0] == 'PENDING'
        assert estados[-1] in {'COMPLETED', 'FAILED', 'INTERRUPTED'}
    ident = resultado['id_ejecucion']
    ejecucion_ident = [
        datos for datos in lineas
        if datos['id_ejecucion'] == ident and datos.get('nivel') != 'accion'
    ]
    assert len(ejecucion_ident) == 2
    assert ejecucion_ident[0]['estado'] == 'PENDING'
    assert ejecucion_ident[-1]['estado'] == 'COMPLETED'
    acciones = [
        datos for datos in lineas
        if datos['id_ejecucion'] == ident and datos.get('nivel') == 'accion'
    ]
    assert len(acciones) == 2
    assert acciones[0]['estado'] == 'PENDING'
    assert acciones[-1]['estado'] == 'COMPLETED'
    assert acciones[-1]['espacio_trabajo'] == str(raiz)
    assert runlog.ejecuciones_abiertas() == []
