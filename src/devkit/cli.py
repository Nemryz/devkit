# Punto de entrada de la interfaz de linea de comandos del toolkit.
from __future__ import annotations

import sys

import typer

from devkit import __version__
from devkit.core.output import emitir
from devkit.tools.doctor import ejecutar_doctor

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help='Herramientas internas de mantenimiento para Windows.',
)


def mostrar_version(valor: bool) -> None:
    # Responde a la opcion global sin cargar el resto de modulos.
    if valor:
        typer.echo(f'devkit {__version__}')
        raise typer.Exit()


@app.callback()
def principal(
    version: bool = typer.Option(
        False,
        '--version',
        '-v',
        callback=mostrar_version,
        is_eager=True,
        help='Muestra la version instalada y termina.',
    ),
) -> None:
    # El callback global solo declara las opciones comunes a todos los comandos.
    return None


@app.command('doctor')
def comando_doctor(
    formato: str = typer.Option(
        'json',
        '--formato',
        '-f',
        help='Formato de salida, json o tabla.',
    ),
) -> None:
    # Ejecuta el diagnostico y traduce el estado a un codigo de salida.
    resultado = ejecutar_doctor(sys.argv[1:])
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


def main() -> None:
    # Fija UTF-8 en la salida para evitar fallos de consola con caracteres especiales.
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, 'reconfigure'):
            flujo.reconfigure(encoding='utf-8', errors='replace')
    app()


if __name__ == '__main__':
    main()
