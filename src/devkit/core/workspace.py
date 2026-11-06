# Identidad persistente de un workspace y validacion de rutas contenidas.
from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from devkit.errors import ErrorIntegridad

NOMBRE_CARPETA = '.devkit'
NOMBRE_ARCHIVO = 'workspace'
NOMBRE_REGISTRO = 'workspaces.json'


def carpeta_devkit(raiz: Path) -> Path:
    # Devuelve la carpeta de metadatos del workspace, creandola si falta.
    ruta = Path(raiz).expanduser().resolve() / NOMBRE_CARPETA
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def leer_id(raiz: Path) -> str | None:
    # Lee el identificador persistente sin crear nada.
    # Devuelve None si el archivo no existe; lanza ErrorIntegridad si esta corrupto.
    base = Path(raiz).expanduser().resolve()
    archivo = base / NOMBRE_CARPETA / NOMBRE_ARCHIVO
    if not archivo.is_file():
        return None
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


def workspace_id(raiz: Path) -> str:
    # Lee el identificador persistente del workspace.
    # Si no existe, lo genera y lo guarda. Si esta corrupto, falla con error explicito.
    base = Path(raiz).expanduser().resolve()
    ident = leer_id(base)
    if ident is not None:
        return ident
    carpeta = base / NOMBRE_CARPETA
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / NOMBRE_ARCHIVO
    nuevo = str(uuid.uuid4())
    archivo.write_text(
        json.dumps({'workspace_id': nuevo}, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    return nuevo


def _ruta_normalizada(raiz: Path) -> str:
    return str(Path(raiz).expanduser().resolve()).casefold()


def _ruta_registro() -> Path:
    # Ruta del registro local de workspaces, respetando DEVKIT_ESTADO.
    from devkit.core import paths

    carpeta = paths.directorio_estado()
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta / NOMBRE_REGISTRO


def _cargar_registro() -> dict:
    ruta = _ruta_registro()
    if not ruta.is_file():
        return {'version': 1, 'workspaces': {}}
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {'version': 1, 'workspaces': {}}
    if not isinstance(datos, dict) or 'workspaces' not in datos:
        return {'version': 1, 'workspaces': {}}
    return datos


def _guardar_registro(datos: dict) -> None:
    ruta = _ruta_registro()
    temporal = ruta.with_suffix('.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(str(temporal), str(ruta))


def registrar(raiz: Path) -> str | None:
    # Registra la raiz en el registro local de workspaces.
    # Devuelve el workspace_id o None si no hay identidad.
    # Solo debe llamarse desde caminos de escritura.
    ident = leer_id(raiz)
    if ident is None:
        return None
    base = Path(raiz).expanduser().resolve()
    ruta_norm = _ruta_normalizada(base)
    ahora = datetime.now(UTC).isoformat()
    registro = _cargar_registro()
    workspaces = registro.setdefault('workspaces', {})
    entrada = workspaces.setdefault(ident, {'roots': [], 'first_seen': ahora, 'shared': False})
    raices = entrada.setdefault('roots', [])
    # Comprobar si ya se vio bajo otra raiz normalizada.
    raices_existentes = {r.get('path', '') for r in raices}
    if ruta_norm not in raices_existentes and raices_existentes:
        entrada['shared'] = True
    # Actualizar o añadir la raiz.
    encontrada = False
    for r in raices:
        if r.get('path') == ruta_norm:
            r['last_seen'] = ahora
            encontrada = True
            break
    if not encontrada:
        raices.append({'path': ruta_norm, 'last_seen': ahora})
    # Limitar a las ultimas 8 raices por identificador.
    if len(raices) > 8:
        raices.sort(key=lambda x: x.get('last_seen', ''))
        del raices[:-8]
    _guardar_registro(registro)
    return ident


def es_compartido(raiz: Path) -> bool:
    # Indica si el workspace se ha visto bajo mas de una raiz.
    ident = leer_id(raiz)
    if ident is None:
        return False
    registro = _cargar_registro()
    entrada = registro.get('workspaces', {}).get(ident)
    if not isinstance(entrada, dict):
        return False
    return bool(entrada.get('shared', False))


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

