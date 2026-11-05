# Resolucion de las rutas conocidas del sistema y del estado del toolkit.
from __future__ import annotations

import os
from pathlib import Path

import platformdirs

NOMBRE_ESTADO = 'devkit'
NOMBRE_CONFIG = 'devkit'
VARIABLE_ESTADO = 'DEVKIT_ESTADO'
VARIABLE_CONFIG = 'DEVKIT_CONFIG'


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


def directorio_estado() -> Path:
    # Permite redirigir el estado en pruebas sin tocar el perfil real.
    personalizado = os.environ.get(VARIABLE_ESTADO)
    if personalizado:
        return Path(personalizado).expanduser()
    return raiz_local() / NOMBRE_ESTADO


def directorio_config() -> Path:
    # Permite redirigir la configuracion en pruebas sin tocar el perfil real.
    personalizado = os.environ.get(VARIABLE_CONFIG)
    if personalizado:
        return Path(personalizado).expanduser()
    return raiz_remota() / NOMBRE_CONFIG


def directorio_journal() -> Path:
    return directorio_estado() / 'journal'


def ruta_journal() -> Path:
    return directorio_journal() / 'ejecuciones.jsonl'


def directorio_respaldos() -> Path:
    # Los respaldos viven junto al estado hasta que exista un volumen secundario.
    return directorio_estado() / 'backups'


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


# --- Perfiles de almacenamiento (Bloque 2) ---


VARIABLE_WORKSPACE = 'DEVKIT_WORKSPACE'
VARIABLE_PERFIL = 'DEVKIT_PERFIL'


def perfil_activo() -> str:
    # Lee el perfil de config.toml o de la variable de entorno.
    personalizado = os.environ.get(VARIABLE_PERFIL, '').strip().lower()
    if personalizado in {'global', 'portable', 'custom', 'temporary'}:
        return personalizado
    try:
        from devkit.config import cargar_configuracion

        config = cargar_configuracion()
        perfil = getattr(config, 'perfil', 'global')
        if perfil in {'global', 'portable', 'custom', 'temporary'}:
            return perfil
    except Exception:  # noqa: BLE001
        pass
    return 'global'


def directorio_cache() -> Path:
    # Resuelve la carpeta de cache segun el perfil activo.
    personalizado = os.environ.get('DEVKIT_CACHE')
    if personalizado:
        return Path(personalizado).expanduser()
    perfil = perfil_activo()
    if perfil == 'portable':
        return directorio_estado() / 'cache'
    if perfil == 'temporary':
        import tempfile

        return Path(tempfile.gettempdir()) / 'devkit-cache'
    # global y custom usan platformdirs.
    return Path(platformdirs.user_cache_dir('devkit', 'devkit'))


def directorio_planes() -> Path:
    # Resuelve la carpeta de planes segun el perfil activo.
    personalizado = os.environ.get('DEVKIT_PLANES')
    if personalizado:
        return Path(personalizado).expanduser()
    perfil = perfil_activo()
    if perfil == 'portable':
        return directorio_estado() / 'planes'
    if perfil == 'temporary':
        import tempfile

        return Path(tempfile.gettempdir()) / 'devkit-planes'
    return directorio_estado() / 'planes'


def directorio_temporal() -> Path:
    # Resuelve la carpeta temporal de ejecucion.
    import tempfile

    personalizado = os.environ.get('DEVKIT_TEMP')
    if personalizado:
        return Path(personalizado).expanduser()
    return Path(tempfile.gettempdir()) / 'devkit-tmp'


def directorio_proyectos() -> Path:
    # Resuelve la carpeta de proyectos sin hardcodear rutas personales.
    personalizado = os.environ.get('DEVKIT_PROYECTOS')
    if personalizado:
        return Path(personalizado).expanduser()
    return Path.home() / 'Projects'


def workspace_activo() -> Path | None:
    # Devuelve la carpeta de trabajo actual si DEVKIT_WORKSPACE esta definido.
    personalizado = os.environ.get(VARIABLE_WORKSPACE)
    if personalizado:
        return Path(personalizado).expanduser().resolve()
    return None


def directorio_estado_por_perfil() -> Path:
    # Resuelve el directorio de estado segun el perfil activo.
    perfil = perfil_activo()
    if perfil == 'portable':
        # En portable, el estado vive junto a la instalacion.
        return directorio_estado()
    if perfil == 'temporary':
        import tempfile

        return Path(tempfile.gettempdir()) / 'devkit-state'
    # global y custom usan el directorio de estado normal.
    return directorio_estado()
