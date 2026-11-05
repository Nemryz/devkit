# Pruebas de integridad de los manifiestos y de las precondiciones de cada movimiento.
import json
import os

import pytest

from devkit.core import safety
from devkit.errors import ErrorIntegridad, ErrorSoloLectura


def test_plan_detecta_cambio_de_tamano(tmp_path):
    origen = tmp_path / 'a.txt'
    destino = tmp_path / 'b.txt'
    origen.write_text('original', encoding='utf-8')
    manifiesto = [
        {
            'origen': str(origen),
            'destino': str(destino),
            'tipo': 'mover',
            'tamano': 8,
            'mtime': origen.stat().st_mtime,
        }
    ]
    ruta_plan = safety.guardar_plan('x-1', 'prueba', manifiesto, destino_dir=tmp_path / 'planes')
    origen.write_text('original-plus', encoding='utf-8')
    fallos = safety._validar_arbol({'acciones': manifiesto})
    assert fallos and 'cambio de tamano' in fallos[0]['detalle']
    resultado = safety.aplicar_plan_persistente(ruta_plan)
    assert resultado['total'] == 0
    assert 'cambio de tamano' in resultado['fallos'][0]['detalle']
    assert origen.read_text(encoding='utf-8') == 'original-plus'


def test_plan_detecta_cambio_de_contenido_con_mismo_tamano(tmp_path, monkeypatch):
    import os

    origen = tmp_path / 'a.txt'
    destino = tmp_path / 'b.txt'
    origen.write_text('hola5', encoding='utf-8')
    mtime = origen.stat().st_mtime
    manifiesto = [
        {
            'origen': str(origen),
            'destino': str(destino),
            'tipo': 'mover',
            'tamano': 5,
            'mtime': mtime,
        }
    ]
    origen.write_text('chaos', encoding='utf-8')
    os.utime(origen, (mtime + 5.0, mtime + 5.0))
    fallos = safety._validar_arbol({'acciones': manifiesto})
    assert fallos
    assert 'cambio de contenido' in fallos[0]['detalle']


def test_plan_detecta_cambio_de_contenido_con_mismo_tamano_y_mtime(tmp_path):
    origen = tmp_path / 'a.txt'
    destino = tmp_path / 'b.txt'
    origen.write_text('hola5', encoding='utf-8')
    mtime = origen.stat().st_mtime
    manifiesto = [
        {
            'origen': str(origen),
            'destino': str(destino),
            'tipo': 'mover',
            'tamano': 5,
            'mtime': mtime,
            'hash': safety.hash_contenido(origen),
        }
    ]
    # Mismo tamano y mtime, distinto contenido: el hash lo detecta.
    origen.write_text('chaos', encoding='utf-8')
    os.utime(origen, (mtime, mtime))
    fallos = safety._validar_arbol({'acciones': manifiesto})
    assert fallos
    assert 'cambio de contenido' in fallos[0]['detalle']
    manifiesto = [{'origen': str(tmp_path / 'fantasma.txt'), 'destino': '', 'tipo': 'papelera'}]
    fallos = safety._validar_arbol({'acciones': manifiesto})
    assert fallos and 'ya no existe' in fallos[0]['detalle']


def test_plan_detecta_destino_ocupado(tmp_path):
    origen = tmp_path / 'a.txt'
    destino = tmp_path / 'b.txt'
    origen.write_text('a', encoding='utf-8')
    destino.write_text('no pisar', encoding='utf-8')
    manifiesto = [
        {
            'origen': str(origen),
            'destino': str(destino),
            'tipo': 'mover',
            'tamano': 1,
            'mtime': origen.stat().st_mtime,
        }
    ]
    fallos = safety._validar_arbol({'acciones': manifiesto})
    assert fallos and 'el destino ya existe' in fallos[0]['detalle']


def test_ejecutar_plan_no_sobrescribe_destino_creado_despues(tmp_path):
    origen = tmp_path / 'a.txt'
    origen.write_text('a', encoding='utf-8')
    plan = safety.Plan()
    destino = tmp_path / 'b.txt'
    plan.agregar(safety.Accion(tipo='mover', origen=str(origen), destino=str(destino)))
    destino.write_text('creado mientras tanto', encoding='utf-8')
    resultado = safety.ejecutar_plan(plan, 'prueba')
    assert len(resultado['fallos']) == 1
    assert 'no se sobrescribe' in resultado['fallos'][0]['detalle']
    assert origen.exists()
    assert destino.read_text(encoding='utf-8') == 'creado mientras tanto'


def test_firma_detecta_modificacion_del_manifiesto(tmp_path):
    manifiesto = [
        {
            'origen': str(tmp_path / 'a.txt'),
            'destino': str(tmp_path / 'b.txt'),
            'tipo': 'mover',
        }
    ]
    ruta_plan = safety.guardar_plan('x-2', 'prueba', manifiesto, destino_dir=tmp_path / 'planes')
    datos = safety.cargar_plan(ruta_plan)
    datos['acciones'][0]['destino'] = str(tmp_path / 'c.txt')
    ruta_plan.write_text(__import__('json').dumps(datos, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(ErrorIntegridad):
        safety.cargar_plan(ruta_plan)


def test_ruta_plan_rechaza_json_invalido(tmp_path):
    ruta = tmp_path / 'plan.json'
    ruta.write_text('{no es json', encoding='utf-8')
    with pytest.raises(ErrorIntegridad):
        safety.cargar_plan(ruta)


def test_estado_del_plan_evoluciona_sin_romper_la_firma(tmp_path):
    origen = tmp_path / 'a.txt'
    destino = tmp_path / 'b.txt'
    origen.write_text('a', encoding='utf-8')
    manifiesto = [
        {
            'origen': str(origen),
            'destino': str(destino),
            'tipo': 'mover',
            'tamano': 1,
            'mtime': origen.stat().st_mtime,
        }
    ]
    ruta_plan = safety.guardar_plan('x-3', 'prueba', manifiesto, destino_dir=tmp_path / 'planes')
    datos = json.loads(ruta_plan.read_text(encoding='utf-8'))
    assert datos['estado'] == 'pendiente'
    resultado = safety.aplicar_plan_persistente(ruta_plan)
    assert resultado['total'] == 1
    datos = json.loads(ruta_plan.read_text(encoding='utf-8'))
    assert datos['estado'] == 'aplicado'
    assert destino.read_text(encoding='utf-8') == 'a'


def test_readonly_bloquea_el_guardian(monkeypatch, tmp_path):
    monkeypatch.setenv('DEVKIT_READONLY', '1')
    plan = safety.Plan()
    with pytest.raises(ErrorSoloLectura):
        safety.ejecutar_plan(plan, 'prueba bloqueada')
