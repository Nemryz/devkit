# Migracion explicita de planes y configuraciones a la version vigente.
from __future__ import annotations

import json
import os
import time
import tomllib
from pathlib import Path

from devkit import config as modulo_config
from devkit.core import runlog, safety
from devkit.errors import ErrorIntegridad

CODIGO_TIPO_NO_SOPORTADO = 'TIPO_NO_SOPORTADO'
CODIGO_RUTA_NO_ENCONTRADA = 'RUTA_NO_ENCONTRADA'
CODIGO_VERSION_ORIGEN_INESPERADA = 'VERSION_ORIGEN_INESPERADA'
CODIGO_VERSION_DESTINO_NO_SOPORTADA = 'VERSION_DESTINO_NO_SOPORTADA'

TIPOS_SOPORTADOS = ('plan', 'config')


def _leer_texto(ruta: Path) -> str:
    # Lee el archivo completo sin traducir saltos de linea para conservarlos al escribir.
    if not ruta.is_file():
        raise ErrorIntegridad(f'{CODIGO_RUTA_NO_ENCONTRADA}: no existe el archivo {ruta}')
    try:
        with ruta.open('r', encoding='utf-8', newline='') as archivo:
            return archivo.read()
    except OSError as fallo:
        raise ErrorIntegridad(f'no se pudo leer {ruta} porque {fallo}') from fallo


def _escribir_atomico(ruta: Path, texto: str) -> None:
    # Escribe mediante un temporal para no dejar el archivo a medias si el proceso muere.
    temporal = ruta.with_name(ruta.name + '.tmp')
    try:
        with temporal.open('w', encoding='utf-8', newline='') as archivo:
            archivo.write(texto)
        os.replace(temporal, ruta)
    except OSError as fallo:
        temporal.unlink(missing_ok=True)
        raise ErrorIntegridad(f'no se pudo escribir {ruta} porque {fallo}') from fallo


def _verificar_expectativas(
    origen: int, desde: int | None, hasta: int | None, destino: int
) -> None:
    # Comprueba las versiones pedidas por el usuario antes de tocar el archivo.
    if desde is not None and origen != desde:
        raise ErrorIntegridad(
            f'{CODIGO_VERSION_ORIGEN_INESPERADA}: el archivo declara version '
            f'{origen} y se esperaba {desde}'
        )
    if hasta is not None and hasta != destino:
        raise ErrorIntegridad(
            f'{CODIGO_VERSION_DESTINO_NO_SOPORTADA}: la version de destino '
            f'{hasta} no esta soportada'
        )


def _registrar(tipo: str, ruta: Path, origen: int, destino: int) -> None:
    # Deja una ejecucion de administracion en el journal solo cuando hubo cambios.
    runlog.registrar_ejecucion(
        'migrate',
        ['migrar', tipo, str(ruta)],
        time.perf_counter(),
        0,
        0,
        detalle=f'version {origen} a {destino}',
        espacio_trabajo=str(ruta.parent),
    )


def migrar_plan_archivo(
    ruta: Path, desde: int | None = None, hasta: int | None = None
) -> dict:
    # Lleva un manifiesto a la version actual y no reescribe si ya esta al dia.
    texto = _leer_texto(ruta)
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as fallo:
        raise ErrorIntegridad(f'el plan {ruta} no es JSON valido porque {fallo}') from fallo
    origen = datos.get('schema_version')
    if origen is None:
        raise ErrorIntegridad(
            f'{safety.CODIGO_MANIFEST_SCHEMA_VERSION_MISSING}: el plan {ruta} no '
            f'declara schema_version'
        )
    if origen not in safety.SCHEMAS_SOPORTADOS:
        raise ErrorIntegridad(
            f'{safety.CODIGO_MANIFEST_SCHEMA_VERSION_NO_SOPORTADA}: el plan {ruta} '
            f'declara schema_version {origen}, no soportada'
        )
    destino = safety.SCHEMA_VERSION_ACTUAL
    _verificar_expectativas(origen, desde, hasta, destino)
    if origen == destino:
        safety.cargar_plan(ruta)
        migrado = False
        detalle = 'el plan ya estaba en la version actual'
    else:
        safety.migrar_plan(ruta)
        migrado = True
        detalle = f'plan migrado de la version {origen} a la {destino}'
    if migrado:
        _registrar('plan', ruta, origen, destino)
    return {
        'tipo': 'plan',
        'ruta': str(ruta),
        'version_origen': origen,
        'version_destino': destino,
        'migrado': migrado,
        'detalle': detalle,
    }


def migrar_config_archivo(
    ruta: Path, desde: int | None = None, hasta: int | None = None
) -> dict:
    # Anade la version vigente a una configuracion anterior sin alterar sus valores.
    texto = _leer_texto(ruta)
    try:
        datos = tomllib.loads(texto)
    except tomllib.TOMLDecodeError as fallo:
        raise ErrorIntegridad(
            f'la configuracion {ruta} no es TOML valido porque {fallo}'
        ) from fallo
    destino = modulo_config.VERSION_CONFIG_ACTUAL
    if 'version' in datos:
        origen = datos['version']
        if not isinstance(origen, int) or origen not in modulo_config.VERSIONES_CONFIG_SOPORTADAS:
            raise ErrorIntegridad(
                f'{modulo_config.CODIGO_CONFIG_VERSION_NO_SOPORTADA}: la configuracion '
                f'{ruta} declara version {origen}, no soportada'
            )
    else:
        origen = 0
    _verificar_expectativas(origen, desde, hasta, destino)
    if origen == destino:
        migrado = False
        detalle = 'la configuracion ya estaba en la version actual'
    else:
        salto = '\r\n' if '\r\n' in texto else '\n'
        nuevo = 'version = ' + str(destino) + salto + texto
        _escribir_atomico(ruta, nuevo)
        try:
            comprobado = tomllib.loads(nuevo)
        except tomllib.TOMLDecodeError as fallo:
            raise ErrorIntegridad(
                f'la configuracion {ruta} quedo invalida despues de migrar porque {fallo}'
            ) from fallo
        if comprobado.get('version') != destino:
            raise ErrorIntegridad(
                f'la configuracion {ruta} no declara la version {destino} despues de migrar'
            )
        migrado = True
        detalle = f'configuracion migrada de la version {origen} a la {destino}'
    if migrado:
        _registrar('config', ruta, origen, destino)
    return {
        'tipo': 'config',
        'ruta': str(ruta),
        'version_origen': origen,
        'version_destino': destino,
        'migrado': migrado,
        'detalle': detalle,
    }


def migrar(
    ruta: str | Path,
    tipo: str,
    desde: int | None = None,
    hasta: int | None = None,
) -> dict:
    # Enruta la migracion al tipo de dato explicado por el llamador.
    if tipo not in TIPOS_SOPORTADOS:
        raise ErrorIntegridad(
            f'{CODIGO_TIPO_NO_SOPORTADO}: el tipo {tipo} no esta soportado'
        )
    destino = Path(ruta).expanduser()
    if tipo == 'plan':
        return migrar_plan_archivo(destino, desde=desde, hasta=hasta)
    return migrar_config_archivo(destino, desde=desde, hasta=hasta)
