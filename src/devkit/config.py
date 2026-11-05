# Configuracion persistente del toolkit, con valores por defecto seguros.
from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from devkit.core import paths


class ConfiguracionAlmacenamiento(BaseModel):
    model_config = ConfigDict(extra='ignore')

    perfil: str = 'global'
    state: str | None = None
    config: str | None = None
    cache: str | None = None
    plans: str | None = None
    journal: str | None = None


class Configuracion(BaseModel):
    model_config = ConfigDict(extra='ignore')

    raices: list[str] = Field(default_factory=list)
    retencion_dias: int = 180
    idioma: str = 'es'
    perfil: str = 'global'
    storage: ConfiguracionAlmacenamiento = Field(default_factory=ConfiguracionAlmacenamiento)


def ruta_config() -> Path:
    return paths.directorio_config() / 'config.toml'


def cargar_configuracion() -> Configuracion:
    # Devuelve los valores por defecto cuando el archivo no existe o esta dañado.
    ruta = ruta_config()
    if not ruta.exists():
        return Configuracion()
    try:
        with ruta.open('rb') as archivo:
            datos = tomllib.load(archivo)
    except (OSError, tomllib.TOMLDecodeError):
        return Configuracion()
    return Configuracion(**datos)
