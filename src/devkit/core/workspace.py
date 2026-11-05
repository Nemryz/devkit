# Identidad persistente de un workspace y validacion de rutas contenidas.
from __future__ import annotations

import json
import uuid
from pathlib import Path

from devkit.errors import ErrorIntegridad

NOMBRE_CARPETA = '.devkit'
NOMBRE_ARCHIVO = 'workspace'


def carpeta_devkit(raiz: Path) -> Path:
    # Devuelve la carpeta de metadatos del workspace, creandola si falta.
    ruta = Path(raiz).expanduser().resolve() / NOMBRE_CARPETA
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def workspace_id(raiz: Path) -> str:
    # Lee el identificador persistente del workspace.
    # Si no existe, lo genera y lo guarda. Si esta corrupto, falla con error explicito.
    carpeta = carpeta_devkit(raiz)
    archivo = carpeta / NOMBRE_ARCHIVO
    if archivo.exists():
        try:
            datos = json.loads(archivo.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as fallo:
            raise ErrorIntegridad(
                f'el identificador del workspace en {archivo} esta corrupto: {fallo}'
            ) from fallo
        ident = datos.get('workspace_id') if isinstance(datos, dict) else None
        if not isinstance(ident, str) or not ident:
            raise ErrorIntegridad(
                f'el identificador del workspace en {archivo} esta corrupto: falta workspace_id'
            )
        try:
            uuid.UUID(ident)
        except ValueError as fallo:
            raise ErrorIntegridad(
                f'el identificador del workspace en {archivo} esta corrupto: {fallo}'
            ) from fallo
        return ident
    nuevo = str(uuid.uuid4())
    archivo.write_text(
        json.dumps({'workspace_id': nuevo}, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    return nuevo


def misma_identidad(raiz_a: Path, raiz_b: Path) -> bool:
    # Indica si dos raices comparten el mismo workspace_id.
    return workspace_id(raiz_a) == workspace_id(raiz_b)


def esta_contenida(raiz: Path, ruta: Path) -> bool:
    # Comprueba que la ruta resuelta quede dentro de la raiz, sin seguir enlaces fuera.
    try:
        base = Path(raiz).expanduser().resolve()
        candidato = Path(ruta).expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    try:
        candidato.relative_to(base)
    except ValueError:
        return False
    return True

