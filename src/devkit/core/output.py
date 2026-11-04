# Salida comun de las herramientas, con JSON como formato estable.
from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table

from devkit.errors import ErrorFormato

CONSOLA = Console()


def serializar(datos: Any) -> str:
    # Conserva tildes y eñes para que la salida sea legible sin escapes.
    return json.dumps(datos, ensure_ascii=False, indent=2)


def imprimir_json(datos: Any) -> None:
    print(serializar(datos))


def imprimir_tabla(datos: dict) -> None:
    # Resume el resultado en una tabla legible por personas.
    tabla = Table(title=str(datos.get('herramienta', 'devkit')))
    tabla.add_column('Bloque')
    tabla.add_column('Estado')
    tabla.add_column('Detalle')
    for fila in datos.get('comprobaciones') or datos.get('bloques') or []:
        tabla.add_row(str(fila['nombre']), str(fila['estado']), str(fila['detalle']))
    if not (datos.get('comprobaciones') or datos.get('bloques')) and datos.get('accion'):
        accion = str(datos.get('accion', ''))
        tabla.add_row(accion, str(datos.get('estado', '')), str(datos.get('detalle', '')))
    CONSOLA.print(tabla)
    estado = datos.get('estado', 'desconocido')
    CONSOLA.print(f'estado general {estado}')


def emitir(datos: dict, formato: str = 'json') -> None:
    # Elige el formato de salida y rechaza cualquier valor no soportado.
    if formato == 'json':
        imprimir_json(datos)
        return
    if formato == 'tabla':
        imprimir_tabla(datos)
        return
    raise ErrorFormato(f'formato no soportado {formato}')
