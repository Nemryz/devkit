# Configuracion persistente del toolkit, con valores por defecto seguros.
from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from devkit.core import paths
from devkit.errors import ErrorConfiguracion


class ConfiguracionAlmacenamiento(BaseModel):
    # El campo config queda fuera a proposito porque la carpeta de configuracion
    # no puede resolverse a traves del propio archivo que reside en ella.
    model_config = ConfigDict(extra='ignore')

    perfil: str = ''
    state: str | None = None
    cache: str | None = None
    plans: str | None = None
    journal: str | None = None


class Configuracion(BaseModel):
    model_config = ConfigDict(extra='ignore')

    raices: list[str] = Field(default_factory=list)
    retencion_dias: int = 180
    idioma: str = 'es'
    perfil: str = 'global'
    version: int = 1
    storage: ConfiguracionAlmacenamiento = Field(default_factory=ConfiguracionAlmacenamiento)


def ruta_config() -> Path:
    return paths.directorio_config() / 'config.toml'


def cargar_configuracion() -> Configuracion:
    # Devuelve los valores por defecto sin archivo y falla explicito con archivo danado.
    ruta = ruta_config()
    if not ruta.exists():
        return Configuracion()
    try:
        with ruta.open('rb') as archivo:
            datos = tomllib.load(archivo)
    except tomllib.TOMLDecodeError as fallo:
        raise ErrorConfiguracion(
            f'la configuracion {ruta} no es TOML valido porque {fallo}'
        ) from fallo
    except OSError as fallo:
        raise ErrorConfiguracion(
            f'no se pudo leer la configuracion {ruta} porque {fallo}'
        ) from fallo
    try:
        return Configuracion(**datos)
    except ValidationError as fallo:
        raise ErrorConfiguracion(
            f'la configuracion {ruta} tiene valores invalidos porque {fallo}'
        ) from fallo
