# Pruebas de las funciones auxiliares del modulo de duplicados.
import os
import time

import pytest

from devkit.errors import ErrorDuplicados
from devkit.tools import dedupe


def crear_archivo(ruta, contenido=b'x' * 100, dias=40):
    # Crea un archivo con fecha antigua para que entre en el escaneo.
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    marca = time.time() - dias * 86400
    os.utime(ruta, (marca, marca))
    return ruta


def test_validar_raiz_rechaza_inexistente(tmp_path):
    with pytest.raises(ErrorDuplicados):
        dedupe.validar_raiz(tmp_path / 'no-existe')


def test_validar_raiz_rechaza_unidad(tmp_path):
    with pytest.raises(ErrorDuplicados):
        dedupe.validar_raiz(tmp_path.resolve().anchor)


def test_validar_raiz_acepta_carpeta(tmp_path):
    assert dedupe.validar_raiz(tmp_path) == tmp_path.resolve()


def test_prehash_detecta_mismo_contenido(tmp_path):
    uno = crear_archivo(tmp_path / 'uno.txt', b'abc' * 50)
    dos = crear_archivo(tmp_path / 'dos.txt', b'abc' * 50)
    assert dedupe.prehash(uno) == dedupe.prehash(dos)


def test_hash_completo_distinto_si_contenido_distinto(tmp_path):
    uno = crear_archivo(tmp_path / 'uno.txt', b'abc' * 50)
    dos = crear_archivo(tmp_path / 'dos.txt', b'abd' * 50)
    assert dedupe.hash_completo(uno) != dedupe.hash_completo(dos)


def test_recolectar_no_baja_a_git(tmp_path):
    crear_archivo(tmp_path / '.git' / 'oculto.txt')
    crear_archivo(tmp_path / 'visible.txt')
    archivos = dedupe.recolectar_archivos(tmp_path, True, 30)
    assert all('.git' not in str(ruta) for ruta in archivos)
    assert any('visible' in str(ruta) for ruta in archivos)


def test_recolectar_respeta_edad(tmp_path):
    crear_archivo(tmp_path / 'nuevo.txt', dias=0)
    crear_archivo(tmp_path / 'viejo.txt', dias=40)
    archivos = dedupe.recolectar_archivos(tmp_path, True, 30)
    nombres = [ruta.name for ruta in archivos]
    assert 'viejo.txt' in nombres
    assert 'nuevo.txt' not in nombres


def test_recolectar_respeta_onedrive(tmp_path, monkeypatch):
    crear_archivo(tmp_path / 'nota.md')
    monkeypatch.setenv('OneDrive', str(tmp_path))
    sin_onedrive = dedupe.recolectar_archivos(tmp_path, True, 30)
    con_onedrive = dedupe.recolectar_archivos(tmp_path, False, 30)
    assert sin_onedrive == []
    assert len(con_onedrive) >= 1


def test_recolectar_no_sigue_enlaces(tmp_path):
    crear_archivo(tmp_path / 'real.txt', b'x' * 10)
    enlace = tmp_path / 'enlace.txt'
    try:
        enlace.symlink_to(tmp_path / 'real.txt')
    except OSError:
        pytest.skip('enlaces no disponibles')
    archivos = dedupe.recolectar_archivos(tmp_path, True, 30)
    assert all('enlace' not in ruta.name for ruta in archivos)


def test_construir_grupos_detecta_duplicados(tmp_path):
    crear_archivo(tmp_path / 'a' / 'uno.jpg', b'z' * 500)
    crear_archivo(tmp_path / 'b' / 'dos.jpg', b'z' * 500)
    crear_archivo(tmp_path / 'unico.jpg', b'z' * 10)
    archivos = dedupe.recolectar_archivos(tmp_path, True, 30)
    grupos = dedupe.construir_grupos(archivos)
    assert len(grupos) == 1
    assert grupos[0]['extension'] == '.jpg'
    assert len(grupos[0]['duplicados']) == 1


def test_construir_grupos_no_confunde_mismo_tamano(tmp_path):
    crear_archivo(tmp_path / 'a' / 'uno.bin', b'x' * 100)
    crear_archivo(tmp_path / 'b' / 'dos.bin', b'y' * 100)
    archivos = dedupe.recolectar_archivos(tmp_path, True, 30)
    grupos = dedupe.construir_grupos(archivos)
    assert grupos == []


def test_conservar_eligue_ruta_mas_corta(tmp_path):
    larga = crear_archivo(tmp_path / 'carpeta-larga' / 'archivo.txt', b'x' * 10, 50)
    corta = crear_archivo(tmp_path / 'a.txt', b'x' * 10, 50)
    assert dedupe._elegir_conservar([larga, corta]) == corta


def test_construir_plan_respeta_tope(tmp_path):
    crear_archivo(tmp_path / 'a' / 'uno.txt', b'x' * 200)
    crear_archivo(tmp_path / 'b' / 'dos.txt', b'x' * 200)
    crear_archivo(tmp_path / 'c' / 'tres.bin', b'y' * 500)
    crear_archivo(tmp_path / 'd' / 'cuatro.bin', b'y' * 500)
    archivos = dedupe.recolectar_archivos(tmp_path, True, 30)
    grupos = dedupe.construir_grupos(archivos)
    plan = dedupe.construir_plan(grupos, tope=250)
    assert plan['total_bytes'] <= 250
    assert plan['omitidos'] >= 1
    assert len(plan['resumen_extension']) >= 1


def test_resumen_por_extension_cuenta_ahorro(tmp_path):
    crear_archivo(tmp_path / 'a' / 'uno.pdf', b'p' * 300)
    crear_archivo(tmp_path / 'b' / 'dos.pdf', b'p' * 300)
    archivos = dedupe.recolectar_archivos(tmp_path, True, 30)
    grupos = dedupe.construir_grupos(archivos)
    plan = dedupe.construir_plan(grupos)
    resumen = {item['extension']: item for item in plan['resumen_extension']}
    assert resumen['.pdf']['ahorro_bytes'] == 300


def test_escanear_registra_journal(estado_temporal, tmp_path):
    crear_archivo(tmp_path / 'a.txt', b'x' * 5)
    resultado = dedupe.escanear_dedupe(tmp_path, edad_dias=30)
    assert resultado['herramienta'] == 'dedupe'
    journal = estado_temporal / 'journal' / 'ejecuciones.jsonl'
    assert 'dedupe' in journal.read_text(encoding='utf-8')
