# Punto de entrada de la interfaz de linea de comandos del toolkit.
from __future__ import annotations

import sys
from pathlib import Path

import typer

from devkit import __version__
from devkit.core.output import emitir
from devkit.errors import ErrorBase
from devkit.tools import backup as modulo_respaldo
from devkit.tools.doctor import ejecutar_doctor

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help='Herramientas internas de mantenimiento para Windows.',
)
app_backup = typer.Typer(
    no_args_is_help=True,
    help='Respaldos cifrados con manifiesto de hashes y verificacion.',
)
app.add_typer(app_backup, name='backup')


def mostrar_version(valor: bool) -> None:
    # Responde a la opcion global sin cargar el resto de modulos.
    if valor:
        typer.echo(f'devkit {__version__}')
        raise typer.Exit()


def salir_con_error(accion: str, fallo: ErrorBase, formato: str) -> None:
    # Convierte una excepcion propia en salida estable y codigo de salida.
    emitir(
        {
            'herramienta': 'devkit',
            'accion': accion,
            'estado': 'error',
            'codigo': fallo.codigo,
            'detalle': str(fallo),
        },
        formato=formato,
    )
    raise typer.Exit(code=fallo.codigo)


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


@app_backup.command('crear')
def comando_backup_crear(
    origen: list[Path] = typer.Option(
        ...,
        '--origen',
        '-o',
        help='Carpeta que se respalda. Se puede repetir.',
    ),
    destino: Path | None = typer.Option(
        None,
        '--destino',
        '-d',
        help='Carpeta donde se guarda el respaldo.',
    ),
    etiqueta: str = typer.Option('', '--etiqueta', '-e', help='Nombre corto del respaldo.'),
    clave: Path | None = typer.Option(
        None,
        '--clave',
        '-c',
        help='Archivo con la clave en la primera linea.',
    ),
    sin_cifrado: bool = typer.Option(False, '--sin-cifrado', help='Genera el respaldo sin cifrar.'),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida, json o tabla.'),
) -> None:
    # Construye el respaldo y devuelve el resumen en el formato pedido.
    try:
        ruta_clave = str(clave) if clave else None
        texto = None if sin_cifrado else modulo_respaldo.obtener_clave(ruta_clave)
        resultado = modulo_respaldo.crear_respaldo(
            origen, destino, etiqueta, texto, not sin_cifrado
        )
    except ErrorBase as fallo:
        salir_con_error('backup crear', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_backup.command('verificar')
def comando_backup_verificar(
    carpeta: Path = typer.Argument(..., help='Carpeta del respaldo que se quiere comprobar.'),
    clave: Path | None = typer.Option(
        None,
        '--clave',
        '-c',
        help='Archivo con la clave en la primera linea.',
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida, json o tabla.'),
) -> None:
    # Extrae el respaldo en temporal y compara cada hash con el manifiesto.
    try:
        manifiesto = modulo_respaldo.leer_manifiesto(carpeta.expanduser().resolve())
        texto = None
        if manifiesto.get('cifrado'):
            texto = modulo_respaldo.obtener_clave(str(clave) if clave else None)
        resultado = modulo_respaldo.verificar_respaldo(carpeta, texto)
    except ErrorBase as fallo:
        salir_con_error('backup verificar', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_backup.command('restaurar')
def comando_backup_restaurar(
    carpeta: Path = typer.Argument(..., help='Carpeta del respaldo que se quiere restaurar.'),
    destino: Path = typer.Option(..., '--destino', '-d', help='Carpeta vacia donde se restaura.'),
    clave: Path | None = typer.Option(
        None,
        '--clave',
        '-c',
        help='Archivo con la clave en la primera linea.',
    ),
    forzar: bool = typer.Option(
        False, '--forzar', help='Permite restaurar sobre contenido existente.'
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida, json o tabla.'),
) -> None:
    # Restaura el contenido y verifica la integridad al terminar.
    try:
        manifiesto = modulo_respaldo.leer_manifiesto(carpeta.expanduser().resolve())
        texto = None
        if manifiesto.get('cifrado'):
            texto = modulo_respaldo.obtener_clave(str(clave) if clave else None)
        resultado = modulo_respaldo.restaurar_respaldo(carpeta, destino, texto, forzar)
    except ErrorBase as fallo:
        salir_con_error('backup restaurar', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_backup.command('listar')
def comando_backup_listar(
    destino: Path | None = typer.Option(
        None,
        '--destino',
        '-d',
        help='Carpeta donde buscar respaldos.',
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida, json o tabla.'),
) -> None:
    # Enumera los respaldos disponibles sin abrir los contenedores.
    try:
        resultado = modulo_respaldo.listar_respaldos(destino)
    except ErrorBase as fallo:
        salir_con_error('backup listar', fallo, formato)
        return
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
