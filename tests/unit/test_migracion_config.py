# Pruebas de migracion de configuraciones anteriores sin perder datos.
from devkit import config as modulo_config
from devkit.core import paths


def _entorno_config(tmp_path, monkeypatch):
    carpeta = tmp_path / 'config'
    carpeta.mkdir()
    monkeypatch.setenv('DEVKIT_CONFIG', str(carpeta))
    monkeypatch.delenv('DEVKIT_ESTADO', raising=False)
    monkeypatch.delenv('DEVKIT_PERFIL', raising=False)
    monkeypatch.delenv('DEVKIT_CACHE', raising=False)
    monkeypatch.delenv('DEVKIT_PLANES', raising=False)
    return carpeta


def test_configuracion_anterior_con_solo_perfil_se_preserva(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    (carpeta / 'config.toml').write_text(
        'raices = ["C:/Notas"]\n'
        'retencion_dias = 90\n'
        'idioma = "es"\n'
        'perfil = "portable"\n',
        encoding='utf-8',
    )
    datos = modulo_config.cargar_configuracion()
    assert datos.raices == ['C:/Notas']
    assert datos.retencion_dias == 90
    assert datos.idioma == 'es'
    assert datos.perfil == 'portable'
    assert datos.version == 1
    assert paths.perfil_activo() == 'portable'


def test_clave_storage_config_ignorada_sin_fallos(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    estado = tmp_path / 'datos-viejos'
    (carpeta / 'config.toml').write_text(
        f'[storage]\nstate = "{estado.as_posix()}"\nconfig = "D:/viejo/config"\n',
        encoding='utf-8',
    )
    datos = modulo_config.cargar_configuracion()
    assert datos.storage.state == estado.as_posix()
    assert paths.directorio_estado() == estado
    # La carpeta de configuracion nunca dependio del propio archivo.
    assert paths.directorio_config() == carpeta


def test_storage_parcial_conserva_valores_no_declarados(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    estado = tmp_path / 'datos'
    planes = tmp_path / 'planes-zona'
    (carpeta / 'config.toml').write_text(
        f'[storage]\nstate = "{estado.as_posix()}"\nplans = "{planes.as_posix()}"\n',
        encoding='utf-8',
    )
    assert paths.directorio_estado() == estado
    assert paths.directorio_planes() == planes
    # Lo no declarado cuelga del estado personalizado.
    assert paths.directorio_journal() == estado / 'journal'


def test_retencion_dias_cargada_del_archivo(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    (carpeta / 'config.toml').write_text('retencion_dias = 60\n', encoding='utf-8')
    datos = modulo_config.cargar_configuracion()
    assert datos.retencion_dias == 60
