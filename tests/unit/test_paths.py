# Pruebas de resolucion de rutas y deteccion de OneDrive.
from pathlib import Path

from devkit.core import paths


def test_directorio_estado_respeta_variable(estado_temporal):
    assert paths.directorio_estado() == estado_temporal


def test_directorio_journal_cuelga_del_estado(estado_temporal):
    assert paths.directorio_journal() == estado_temporal / 'journal'


def test_es_onedrive_detecta_nombre_en_ruta():
    assert paths.es_onedrive(Path('C:/Users/ana/OneDrive/Documentos')) is True


def test_es_onedrive_rechaza_ruta_normal():
    assert paths.es_onedrive(Path('C:/Users/ana/Projects/devkit')) is False


def test_es_onedrive_detecta_variable_de_entorno(monkeypatch):
    monkeypatch.setenv('OneDrive', 'C:\\Perfil\\Sincronizado')
    assert paths.es_onedrive(Path('C:/Perfil/Sincronizado/Notas')) is True


def test_ruta_larga_conserva_rutas_cortas():
    texto = paths.ruta_larga(Path('C:/Users/ana/Projects'))
    assert texto.startswith('C:')
    assert texto.startswith('\\\\?\\') is False


def test_ruta_larga_antepone_prefijo_en_rutas_extensas():
    ruta = Path('C:/' + 'a' * 300)
    assert paths.ruta_larga(ruta).startswith('\\\\?\\')


def test_asegurar_directorio_crea_la_carpeta(tmp_path):
    destino = tmp_path / 'nueva' / 'profunda'
    resultado = paths.asegurar_directorio(destino)
    assert resultado == destino
    assert destino.is_dir()
