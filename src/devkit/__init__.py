# Paquete interno de herramientas de mantenimiento para Windows.
from __future__ import annotations

import importlib.metadata


def _version() -> str:
    try:
        return importlib.metadata.version('devkit')
    except importlib.metadata.PackageNotFoundError:
        return '0.0.0'


__version__ = _version()
