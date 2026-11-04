# Resolucion de las rutas conocidas del sistema y del estado del toolkit.
from __future__ import annotations

import os
from pathlib import Path

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
