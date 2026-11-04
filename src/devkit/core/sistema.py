# Lecturas del sistema operativo que no dependen de PowerShell.
from __future__ import annotations

import ctypes
import os
import platform


def es_administrador() -> bool:
    # Comprueba si el proceso actual tiene elevacion activa.
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def rutas_largas_habilitadas() -> bool:
    # Consulta el valor que permite rutas de mas de 260 caracteres en Windows.
    try:
        import winreg
    except ImportError:
        return False
    ruta = r'SYSTEM\CurrentControlSet\Control\FileSystem'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ruta) as clave:
            valor, _ = winreg.QueryValueEx(clave, 'LongPathsEnabled')
    except OSError:
        return False
    return bool(valor)


def descripcion_sistema() -> str:
    return f'{platform.system()} {platform.release()} {platform.version()}'.strip()


def nombre_equipo() -> str:
    return os.environ.get('COMPUTERNAME', platform.node())
