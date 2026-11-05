# Pruebas del indice FTS5 sobre notas Markdown.

import pytest

from devkit.errors import ErrorIndex, ErrorSoloLectura
from devkit.tools import idea, index


def crear_nota(raiz, titulo, cuerpo, estado='activo'):
    raiz.mkdir(parents=True, exist_ok=True)
    return idea.crear_nota(raiz, titulo, cuerpo, [estado], estado)


def test_ruta_indice_por_defecto_en_estado():

    ruta = index.ruta_indice()
    assert 'devkit' in str(ruta)
    assert str(ruta).endswith('index.sqlite')


def test_construir_indice_cuenta_notas(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    crear_nota(raiz, 'Primera', 'Texto sobre devkit y python')
    crear_nota(raiz, 'Segunda', 'Otro texto sin coincidencia')
    resultado = index.construir_indice(raiz)
    assert resultado['herramienta'] == 'index'
    assert resultado['total_notas'] == 2
    bd = index.ruta_indice()
    assert bd.is_file()


def test_buscar_encuentra_termino(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    crear_nota(raiz, 'Primera', 'Texto sobre devkit y python')
    index.construir_indice(raiz)
    resultado = index.buscar(raiz, 'devkit')
    assert resultado['total'] >= 1
    assert any(
        'devkit' in r['fragmento'].lower() or 'devkit' in r['titulo'].lower()
        for r in resultado['resultados']
    )


def test_buscar_sin_indice_falla(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    with pytest.raises(ErrorIndex):
        index.buscar(raiz, 'x')


def test_construir_bloqueado_solo_lectura(estado_temporal, tmp_path, monkeypatch):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    monkeypatch.setenv('DEVKIT_READONLY', '1')
    with pytest.raises(ErrorSoloLectura):
        index.construir_indice(raiz)


def test_actualizar_detecta_nueva_nota(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    crear_nota(raiz, 'Primera', 'Texto uno')
    index.construir_indice(raiz)
    crear_nota(raiz, 'Segunda', 'Texto dos')
    resultado = index.actualizar_indice(raiz)
    assert resultado['insertados'] >= 1
    assert resultado['total_notas'] == 2


def test_actualizar_detecta_eliminada(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    crear_nota(raiz, 'Temporal', 'Texto temporal')
    index.construir_indice(raiz)
    for ruta in raiz.rglob('*.md'):
        ruta.unlink()
    resultado = index.actualizar_indice(raiz)
    assert resultado['total_notas'] == 0


def test_exportar_indice(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    crear_nota(raiz, 'Exportable', 'Cuerpo de prueba')
    index.construir_indice(raiz)
    salida = tmp_path / 'export.json'
    resultado = index.exportar_indice(index.ruta_indice(), salida)
    assert resultado['total'] == 1
    assert salida.is_file()
    import json

    datos = json.loads(salida.read_text(encoding='utf-8'))
    assert datos[0]['titulo'] == 'Exportable'


def test_construir_indice_rechaza_raiz_invalida(tmp_path):
    with pytest.raises(ErrorIndex):
        index.construir_indice(tmp_path / 'no-existe')


def test_ruta_indice_por_defecto(tmp_path):
    ruta = index.ruta_indice()
    assert str(ruta).endswith('index.sqlite')
    assert 'devkit' in str(ruta)
