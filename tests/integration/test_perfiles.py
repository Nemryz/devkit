# Pruebas de contrato de los perfiles de almacenamiento y su precedencia.

import pytest

from devkit import config as modulo_config
from devkit.core import paths
from devkit.errors import ErrorConfiguracion


def _entorno_config(tmp_path, monkeypatch):
    # Aisla la configuracion en una carpeta temporal y limpia las variables conflictivas.
    carpeta = tmp_path / 'config'
    carpeta.mkdir()
    monkeypatch.setenv('DEVKIT_CONFIG', str(carpeta))
    monkeypatch.delenv('DEVKIT_PERFIL', raising=False)
    monkeypatch.delenv('DEVKIT_ESTADO', raising=False)
    monkeypatch.delenv('DEVKIT_CACHE', raising=False)
    monkeypatch.delenv('DEVKIT_PLANES', raising=False)
    monkeypatch.delenv('DEVKIT_WORKSPACE', raising=False)
    return carpeta


def test_perfil_global_usa_ubicacion_local(tmp_path, monkeypatch):
    _entorno_config(tmp_path, monkeypatch)
    assert paths.directorio_estado() == paths.raiz_local() / 'devkit'


def test_perfil_portable_guarda_junto_a_la_instalacion(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    monkeypatch.delenv('DEVKIT_CONFIG')
    monkeypatch.setenv('DEVKIT_PERFIL', 'portable')
    estado = paths.directorio_estado()
    config_dir = paths.directorio_config()
    raiz = paths._raiz_instalacion()
    assert estado.is_relative_to(raiz)
    assert config_dir.is_relative_to(raiz)
    assert estado != paths.raiz_local() / 'devkit'
    assert carpeta is not None  # la variable DEVKIT_CONFIG no gobierna aqui


def test_perfil_temporary_no_persiste_en_el_perfil_global(tmp_path, monkeypatch):
    _entorno_config(tmp_path, monkeypatch)
    monkeypatch.setenv('DEVKIT_PERFIL', 'temporary')
    estado = paths.directorio_estado()
    cache = paths.directorio_cache()
    planes = paths.directorio_planes()
    raiz_temporal = paths._raiz_temporaria()
    assert estado.is_relative_to(raiz_temporal)
    assert cache.is_relative_to(raiz_temporal)
    assert planes.is_relative_to(raiz_temporal)
    # El estado devkit del perfil global sigue intacto, tmp_path vive dentro del %TEMP% del usuario.
    almacenamiento_global = paths.raiz_local() / 'devkit'
    assert estado != almacenamiento_global
    assert not estado.is_relative_to(almacenamiento_global)
    assert not almacenamiento_global.is_relative_to(estado)


def test_perfil_custom_exige_storage_en_config(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    (carpeta / 'config.toml').write_text(
        'perfil = "custom"\n', encoding='utf-8'
    )
    with pytest.raises(ErrorConfiguracion):
        paths.directorio_estado()


def test_perfil_custom_usa_todas_las_rutas_personalizadas(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    destino = tmp_path / 'datos'
    (carpeta / 'config.toml').write_text(
        f'[storage]\nperfil = "custom"\nstate = "{destino.as_posix()}"\n',
        encoding='utf-8',
    )
    estado = paths.directorio_estado()
    cache = paths.directorio_cache()
    planes = paths.directorio_planes()
    journal = paths.directorio_journal()
    assert estado == destino
    assert cache == destino / 'cache'
    assert planes == destino / 'planes'
    assert journal == destino / 'journal'


def test_precedencia_variable_entorno_sobre_todo(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    del_toml = tmp_path / 'de-toml'
    otro = tmp_path / 'de-variable'
    (carpeta / 'config.toml').write_text(
        f'[storage]\nstate = "{del_toml.as_posix()}"\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('DEVKIT_PERFIL', 'custom')
    assert paths.directorio_estado() == del_toml
    monkeypatch.setenv('DEVKIT_ESTADO', str(otro))
    assert paths.directorio_estado() == otro


def test_precedencia_config_toml_sobre_perfil(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    del_toml = tmp_path / 'de-toml'
    (carpeta / 'config.toml').write_text(
        f'[storage]\nstate = "{del_toml.as_posix()}"\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('DEVKIT_PERFIL', 'temporary')
    assert paths.directorio_estado() == del_toml


def test_config_toml_inexistente_usa_valores_por_defecto(tmp_path, monkeypatch):
    _entorno_config(tmp_path, monkeypatch)
    datos = modulo_config.cargar_configuracion()
    assert datos.retencion_dias == 180
    assert datos.perfil == 'global'
    assert paths.perfil_activo() == 'global'


def test_config_toml_danado_error_explicito(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    (carpeta / 'config.toml').write_text('retencion_dias = [1, 2\n', encoding='utf-8')
    with pytest.raises(ErrorConfiguracion):
        modulo_config.cargar_configuracion()
    with pytest.raises(ErrorConfiguracion):
        paths.directorio_estado()


def test_config_valores_invalidos_error_explicito(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    (carpeta / 'config.toml').write_text('retencion_dias = "muchos"\n', encoding='utf-8')
    with pytest.raises(ErrorConfiguracion):
        paths.directorio_cache()


def test_perfil_en_storage_gana_sobre_niveles_superiores(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    (carpeta / 'config.toml').write_text(
        'perfil = "global"\n[storage]\nperfil = "portable"\n',
        encoding='utf-8',
    )
    assert paths.perfil_activo() == 'portable'


def test_perfil_invalido_en_variable_falla_de_forma_explicita(tmp_path, monkeypatch):
    _entorno_config(tmp_path, monkeypatch)
    monkeypatch.setenv('DEVKIT_PERFIL', 'portble')
    with pytest.raises(ErrorConfiguracion):
        paths.perfil_activo()


def test_perfil_invalido_en_config_falla_de_forma_explicita(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    (carpeta / 'config.toml').write_text('perfil = "portble"\n', encoding='utf-8')
    with pytest.raises(ErrorConfiguracion):
        paths.perfil_activo()


def test_perfil_invalido_en_storage_de_config_falla_de_forma_explicita(tmp_path, monkeypatch):
    carpeta = _entorno_config(tmp_path, monkeypatch)
    (carpeta / 'config.toml').write_text('[storage]\nperfil = "portble"\n', encoding='utf-8')
    with pytest.raises(ErrorConfiguracion):
        paths.perfil_activo()
