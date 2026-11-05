# Pruebas de clasificacion y plan del modulo de organizacion.
import os
import time

import pytest

from devkit.errors import ErrorOrganizar
from devkit.tools import organize


def crear_archivo(ruta, contenido=b'x' * 20, dias=0):
    # Crea un archivo con fecha antigua y sin tocar el mtime con dias.
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    if dias:
        marca = time.time() - dias * 86400
        os.utime(ruta, (marca, marca))
    return ruta


def test_validar_raiz_rechaza_inexistente(tmp_path):
    with pytest.raises(ErrorOrganizar):
        organize.validar_raiz(tmp_path / 'no-existe')


def test_validar_raiz_rechaza_unidad(tmp_path):
    with pytest.raises(ErrorOrganizar):
        organize.validar_raiz(tmp_path.resolve().anchor)


def test_validar_raiz_acepta(tmp_path):
    assert organize.validar_raiz(tmp_path) == tmp_path.resolve()


def test_detectar_tipo_por_firma_jpg(tmp_path):
    ruta = crear_archivo(tmp_path / 'foto.bin', b'\xff\xd8\xff\x00hola')
    tipo, ext = organize.detectar_tipo(ruta)
    assert tipo == 'imagen'
    assert ext == '.jpg'


def test_detectar_tipo_por_firma_pdf(tmp_path):
    ruta = crear_archivo(tmp_path / 'doc.bin', b'%PDF-1.4 hola')
    tipo, ext = organize.detectar_tipo(ruta)
    assert tipo == 'documento'
    assert ext == '.pdf'


def test_detectar_por_extension_cuando_no_hay_firma(tmp_path):
    ruta = crear_archivo(tmp_path / 'notas.md', b'texto')
    tipo, _ = organize.detectar_tipo(ruta)
    assert tipo == 'documento'


def test_detectar_otros_sin_extension(tmp_path):
    ruta = crear_archivo(tmp_path / 'sin_extension', b'xyz')
    tipo, ext = organize.detectar_tipo(ruta)
    assert tipo == 'otros'
    assert ext == ''


def test_anio_archivo_usa_modificacion(tmp_path):
    ruta = crear_archivo(tmp_path / 'viejo.txt', b'x', dias=365)
    assert organize.anio_archivo(ruta) == str(time.localtime(time.time() - 365 * 86400).tm_year)


def test_recolectar_no_baja_a_git(tmp_path):
    crear_archivo(tmp_path / '.git' / 'oculto.txt')
    crear_archivo(tmp_path / 'visible.txt')
    archivos = organize.recolectar_archivos(tmp_path, True)
    assert all('.git' not in str(ruta) for ruta in archivos)
    assert any('visible' in str(ruta) for ruta in archivos)


def test_recolectar_no_sigue_enlaces(tmp_path):
    crear_archivo(tmp_path / 'real.txt', b'x')
    enlace = tmp_path / 'enlace.txt'
    try:
        enlace.symlink_to(tmp_path / 'real.txt')
    except OSError:
        pytest.skip('enlaces no disponibles')
    archivos = organize.recolectar_archivos(tmp_path, True)
    assert all('enlace' not in ruta.name for ruta in archivos)


def test_recolectar_respeta_onedrive(tmp_path, monkeypatch):
    crear_archivo(tmp_path / 'nota.md')
    monkeypatch.setenv('OneDrive', str(tmp_path))
    assert organize.recolectar_archivos(tmp_path, True) == []
    assert len(organize.recolectar_archivos(tmp_path, False)) >= 1


def test_construir_plan_anio_y_tipo(tmp_path):
    crear_archivo(tmp_path / 'foto.jpg', b'\xff\xd8\xff\x00', dias=400)
    crear_archivo(tmp_path / 'doc.pdf', b'%PDF-1.4 ', dias=400)
    archivos = organize.recolectar_archivos(tmp_path, True)
    plan = organize.construir_plan(tmp_path, tmp_path / 'Organizados', archivos)
    assert plan['total'] == 2
    assert plan['por_tipo']['imagen'] == 1
    assert plan['por_tipo']['documento'] == 1


def test_construir_plan_resuelve_colisiones(tmp_path):
    crear_archivo(tmp_path / 'a' / 'foto.jpg', b'\xff\xd8\xff\x00', dias=1)
    crear_archivo(tmp_path / 'b' / 'foto.jpg', b'\xff\xd8\xff\x00', dias=1)
    archivos = organize.recolectar_archivos(tmp_path, True)
    plan = organize.construir_plan(tmp_path, tmp_path / 'Organizados', archivos)
    destinos = [str(x['destino']) for x in plan['acciones']]
    assert len(destinos) == 2
    assert destinos[0] != destinos[1]
    assert '_' in destinos[1] or destinos[1] != destinos[0]


def test_escanear_registra_journal(estado_temporal, tmp_path):
    crear_archivo(tmp_path / 'uno.jpg', b'\xff\xd8\xff\x00')
    resultado = organize.escanear_organize(tmp_path)
    assert resultado['herramienta'] == 'organize'
    assert 'plan' in resultado['accion']
    journal = estado_temporal / 'journal' / 'ejecuciones.jsonl'
    assert 'organize' in journal.read_text(encoding='utf-8')
