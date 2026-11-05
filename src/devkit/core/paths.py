# Resolucion de las rutas conocidas del sistema y del estado del toolkit.
# Precedencia al resolver: variable de entorno, config.toml, perfil activo, raices del sistema.
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import platformdirs

from devkit.errors import ErrorConfiguracion

NOMBRE_ESTADO = 'devkit'
NOMBRE_CONFIG = 'devkit'
VARIABLE_ESTADO = 'DEVKIT_ESTADO'
VARIABLE_CONFIG = 'DEVKIT_CONFIG'
VARIABLE_CACHE = 'DEVKIT_CACHE'
VARIABLE_PLANES = 'DEVKIT_PLANES'
VARIABLE_TEMP = 'DEVKIT_TEMP'
VARIABLE_PROYECTOS = 'DEVKIT_PROYECTOS'
VARIABLE_WORKSPACE = 'DEVKIT_WORKSPACE'
VARIABLE_PERFIL = 'DEVKIT_PERFIL'

# Perfiles admitidos por el resolvedor de almacenamiento.
PERFILES = ('global', 'portable', 'custom', 'temporary')


def raiz_local() -> Path:
    # Devuelve la carpeta local del perfil, que Windows no sincroniza con OneDrive.
    base = os.environ.get('LOCALAPPDATA')
    if base:
        return Path(base)
    return Path.home() / 'AppData' / 'Local'


def raiz_remota() -> Path:
    # Devuelve la carpeta de datos de aplicacion del perfil del usuario.
    base = os.environ.get('APPDATA')
    if base:
        return Path(base)
    return Path.home() / 'AppData' / 'Roaming'


def _raiz_instalacion() -> Path:
    # Localiza la raiz de instalacion del paquete para el perfil portable.
    for candidato in Path(__file__).resolve().parents:
        if (candidato / 'pyproject.toml').is_file():
            return candidato
    # Sin checkout del proyecto el paquete vive dentro de site-packages.
    return Path(__file__).resolve().parents[2]


def _raiz_temporaria() -> Path:
    # Carpeta raiz del perfil temporary dentro del directorio temporal del sistema.
    return Path(tempfile.gettempdir()) / 'devkit'


def _ruta_de(valor) -> Path | None:
    # Convierte un valor de config.toml en ruta cuando es un texto util.
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    return Path(texto).expanduser()


def _perfil_de(config) -> str:
    # Deriva el perfil activo desde la variable de entorno y desde el propio config.toml.
    personal = os.environ.get(VARIABLE_PERFIL, '').strip().lower()
    if personal in PERFILES:
        return personal
    del_toml = str(config.storage.perfil or config.perfil or '').strip().lower()
    if del_toml in PERFILES:
        return del_toml
    return 'global'


def perfil_activo() -> str:
    # Nombre del perfil que gobernara el resolvedor en esta llamada.
    from devkit.config import cargar_configuracion

    return _perfil_de(cargar_configuracion())


def directorio_estado() -> Path:
    # Resuelve el estado respetando la capa de configuracion mas alta disponible.
    del_env = os.environ.get(VARIABLE_ESTADO)
    if del_env:
        return Path(del_env).expanduser()
    from devkit.config import cargar_configuracion

    config = cargar_configuracion()
    personalizado = _ruta_de(config.storage.state)
    if personalizado:
        return personalizado
    perfil = _perfil_de(config)
    if perfil == 'portable':
        return _raiz_instalacion() / '.devkit' / 'estado'
    if perfil == 'temporary':
        return _raiz_temporaria() / 'estado'
    if perfil == 'custom':
        raise ErrorConfiguracion('el perfil custom exige [storage] state en config.toml')
    return raiz_local() / NOMBRE_ESTADO


def directorio_config() -> Path:
    # La carpeta de configuracion no puede depender del propio config.toml, solo del entorno.
    del_env = os.environ.get(VARIABLE_CONFIG)
    if del_env:
        return Path(del_env).expanduser()
    personal = os.environ.get(VARIABLE_PERFIL, '').strip().lower()
    if personal == 'portable':
        return _raiz_instalacion() / '.devkit' / 'config'
    if personal == 'temporary':
        return _raiz_temporaria() / 'config'
    return raiz_remota() / NOMBRE_CONFIG


def directorio_journal() -> Path:
    # El journal sigue al estado y solo se desvia cuando config.toml define su ruta.
    from devkit.config import cargar_configuracion

    config = cargar_configuracion()
    personalizado = _ruta_de(config.storage.journal)
    if personalizado:
        return personalizado
    return directorio_estado() / 'journal'


def ruta_journal() -> Path:
    return directorio_journal() / 'ejecuciones.jsonl'


def directorio_respaldos() -> Path:
    # Los respaldos viven junto al estado hasta que exista un volumen secundario.
    return directorio_estado() / 'backups'


def directorio_cache() -> Path:
    # Resuelve la cache con la precedencia completa de capas.
    del_env = os.environ.get(VARIABLE_CACHE)
    if del_env:
        return Path(del_env).expanduser()
    from devkit.config import cargar_configuracion

    config = cargar_configuracion()
    personalizado = _ruta_de(config.storage.cache)
    if personalizado:
        return personalizado
    perfil = _perfil_de(config)
    if perfil == 'temporary':
        return _raiz_temporaria() / 'cache'
    if perfil == 'global':
        return Path(platformdirs.user_cache_dir('devkit', 'devkit'))
    # portable y custom cuelgan del estado ya resuelto por perfil.
    return directorio_estado() / 'cache'


def directorio_planes() -> Path:
    # Resuelve la carpeta de planes con la misma precedencia de capas.
    del_env = os.environ.get(VARIABLE_PLANES)
    if del_env:
        return Path(del_env).expanduser()
    from devkit.config import cargar_configuracion

    config = cargar_configuracion()
    personalizado = _ruta_de(config.storage.plans)
    if personalizado:
        return personalizado
    if _perfil_de(config) == 'temporary':
        return _raiz_temporaria() / 'planes'
    return directorio_estado() / 'planes'


def directorio_temporal() -> Path:
    # Resuelve la carpeta temporal de ejecucion, independiente del almacenamiento del perfil.
    del_env = os.environ.get(VARIABLE_TEMP)
    if del_env:
        return Path(del_env).expanduser()
    return Path(tempfile.gettempdir()) / 'devkit-tmp'


def directorio_proyectos() -> Path:
    # Resuelve la carpeta de proyectos sin hardcodear rutas personales.
    del_env = os.environ.get(VARIABLE_PROYECTOS)
    if del_env:
        return Path(del_env).expanduser()
    return Path.home() / 'Projects'


def workspace_activo() -> Path | None:
    # Devuelve la carpeta de trabajo activa cuando DEVKIT_WORKSPACE esta definido.
    del_env = os.environ.get(VARIABLE_WORKSPACE)
    if del_env:
        return Path(del_env).expanduser().resolve()
    return None


def directorio_estado_por_perfil() -> Path:
    # Alias mantenido por compatibilidad porque directorio_estado ya aplica el perfil.
    return directorio_estado()


def asegurar_directorio(ruta: Path) -> Path:
    # Crea la carpeta si falta y devuelve la misma ruta para encadenar llamadas.
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def es_onedrive(ruta: Path) -> bool:
    # Detecta si la ruta cae dentro de una carpeta sincronizada por OneDrive.
    texto = str(ruta).lower()
    if 'onedrive' in texto:
        return True
    for clave in ('OneDrive', 'OneDriveCommercial', 'OneDriveConsumer'):
        valor = os.environ.get(clave)
        if valor and texto.startswith(valor.lower()):
            return True
    return False


def ruta_larga(ruta: Path) -> str:
    # Convierte una ruta en su forma extendida cuando supera el limite historico.
    texto = os.path.abspath(str(ruta))
    if os.name != 'nt' or texto.startswith('\\\\?\\'):
        return texto
    if len(texto) < 248:
        return texto
    if texto.startswith('\\\\'):
        return '\\\\?\\UNC\\' + texto[2:]
    return '\\\\?\\' + texto
