# Pruebas de las funciones auxiliares del modulo de limpieza.
import os
import time

import pytest

from devkit.errors import ErrorLimpieza
from devkit.tools import trim


def crear_cache(raiz, nombre='__pycache__', dias=10, contenido=b'x' * 100):
    # Crea una carpeta con un archivo y fecha antigua para el escaneo.
    destino = raiz / nombre
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / 'dato.pyc'
    archivo.write_bytes(contenido)
    marca = time.time() - dias * 86400
    os.utime(destino, (marca, marca))
    return destino


def test_validar_raiz_rechaza_inexistente(tmp_path):
    with pytest.raises(ErrorLimpieza):
        trim.validar_raiz(tmp_path / 'no-existe')


def test_validar_raiz_rechaza_unidad_completa(tmp_path):
    with pytest.raises(ErrorLimpieza):
        trim.validar_raiz(tmp_path.resolve().anchor)


def test_validar_raiz_acepta_carpeta(tmp_path):
    assert trim.validar_raiz(tmp_path) == tmp_path.resolve()


def test_calcular_tamano_cuenta_archivos(tmp_path):
    (tmp_path / 'uno.txt').write_bytes(b'x' * 50)
    (tmp_path / 'dos.txt').write_bytes(b'y' * 70)
    assert trim.calcular_tamano(tmp_path) == 120


def test_escanear_detecta_cache_antigua(tmp_path):
    crear_cache(tmp_path)
    candidatos = trim.escanear(tmp_path, edad_dias=7)
    assert len(candidatos) == 1
    assert candidatos[0]['tipo'] == 'carpeta'
    assert candidatos[0]['tamano'] == 100


def test_escanear_ignora_cache_reciente(tmp_path):
    crear_cache(tmp_path, dias=0)
    candidatos = trim.escanear(tmp_path, edad_dias=7)
    assert candidatos == []


def test_escanear_nunca_entra_en_git(tmp_path):
    crear_cache(tmp_path / '.git', '__pycache__', 10, b'x' * 10)
    (tmp_path / '.git' / 'fuente.txt').write_text('x', encoding='utf-8')
    candidatos = trim.escanear(tmp_path, edad_dias=7)
    assert all('.git' not in item['ruta'] for item in candidatos)


def test_escanear_detecta_archivo_temporal(tmp_path):
    archivo = tmp_path / 'registro.log'
    archivo.write_bytes(b'x' * 20)
    marca = time.time() - 10 * 86400
    os.utime(archivo, (marca, marca))
    candidatos = trim.escanear(tmp_path, edad_dias=7)
    assert any(item['ruta'].endswith('registro.log') for item in candidatos)


def test_escanear_nunca_toca_src(tmp_path):
    crear_cache(tmp_path / 'src' / '__pycache__', '__pycache__', 10, b'x' * 10)
    candidatos = trim.escanear(tmp_path, edad_dias=7)
    assert all('src' not in item['ruta'] for item in candidatos)


def test_escanear_salta_venv_sin_flag(tmp_path):
    crear_cache(tmp_path, '.venv', 10, b'x' * 30)
    candidatos = trim.escanear(tmp_path, edad_dias=7, incluir_venv=False)
    assert candidatos == []


def test_escanear_incluye_venv_con_flag(tmp_path):
    crear_cache(tmp_path, '.venv', 10, b'x' * 30)
    candidatos = trim.escanear(tmp_path, edad_dias=7, incluir_venv=True)
    assert any('.venv' in item['ruta'] for item in candidatos)


def test_construir_plan_respeta_tope(tmp_path):
    crear_cache(tmp_path, '__pycache__', 10, b'x' * 200)
    crear_cache(tmp_path, '.pytest_cache', 10, b'x' * 300)
    candidatos = trim.escanear(tmp_path, edad_dias=7)
    plan = trim.construir_plan(candidatos, tope=250)
    assert plan['total_bytes'] <= 250
    assert plan['omitidos'] == 1


def test_construir_plan_no_corta_si_todo_cabe(tmp_path):
    crear_cache(tmp_path, '__pycache__', 10, b'x' * 50)
    candidatos = trim.escanear(tmp_path, edad_dias=7)
    plan = trim.construir_plan(candidatos, tope=1000)
    assert plan['total'] == 1
    assert plan['total_bytes'] == 50


def test_escanear_trim_registra_journal(estado_temporal, tmp_path):
    crear_cache(tmp_path, '__pycache__', 10, b'x' * 10)
    resultado = trim.escanear_trim(tmp_path, edad_dias=7)
    assert resultado['herramienta'] == 'trim'
    assert resultado['total'] >= 1
    journal = estado_temporal / 'journal' / 'ejecuciones.jsonl'
    assert journal.is_file()
    assert 'trim' in journal.read_text(encoding='utf-8')
