# Punto de entrada de la interfaz de linea de comandos del toolkit.
from __future__ import annotations

import sys
from pathlib import Path

import typer

from devkit import __version__
from devkit.core.output import emitir
from devkit.errors import ErrorBase
from devkit.tools import backup as modulo_respaldo
from devkit.tools import dedupe as modulo_dedupe
from devkit.tools import nice as modulo_nice
from devkit.tools import trim as modulo_trim
from devkit.tools.doctor import ejecutar_doctor
from devkit.tools.health import ejecutar_salud

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
app_trim = typer.Typer(
    no_args_is_help=True,
    help='Limpieza de caches con plan previo y papelera de Windows.',
)
app.add_typer(app_trim, name='trim')
app_dedupe = typer.Typer(
    no_args_is_help=True,
    help='Duplicados exactos con BLAKE3, plan previo y papelera de Windows.',
)
app.add_typer(app_dedupe, name='dedupe')
app_nice = typer.Typer(
    no_args_is_help=True,
    help='Ejecuta hijos con prioridad baja y registro de memoria.',
)
app.add_typer(app_nice, name='nice')


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


@app.command('health')
def comando_health(
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Ejecuta el informe de salud y traduce el estado a codigo de salida.
    resultado = ejecutar_salud(sys.argv[1:])
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_nice.command('ejecutar')
def comando_nice_ejecutar(
    comando: list[str] = typer.Argument(
        ..., help='Comando y argumentos. Separa con -- antes de las opciones del hijo.'
    ),
    prioridad: str = typer.Option('bajo', '--prioridad', help='Prioridad del hijo.'),
    tiempo: float = typer.Option(3600.0, '--tiempo', help='Tiempo maximo en segundos.'),
    memoria_mb: int | None = typer.Option(
        None, '--memoria-mb', help='Limite aproximado en MB.'
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Envuelve el hijo con prioridad en bajo y un tiempo maximo dado.
    try:
        resultado = modulo_nice.ejecutar_nice(
            comando, prioridad, tiempo, memoria_mb
        )
    except ErrorBase as fallo:
        salir_con_error('nice ejecutar', fallo, formato)
        return
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


@app_trim.command('escanear')
def comando_trim_escanear(
    raiz: Path = typer.Argument(..., help='Carpeta que se quiere escanear.'),
    incluir_venv: bool = typer.Option(
        False, '--incluir-venv', help='Incluye la carpeta .venv en el plan.'
    ),
    edad_dias: int = typer.Option(7, '--edad-dias', help='Solo incluye elementos viejos.'),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Genera el plan en solo lectura y lo muestra sin tocar el disco.
    try:
        resultado = modulo_trim.escanear_trim(raiz, incluir_venv, edad_dias)
    except ErrorBase as fallo:
        salir_con_error('trim escanear', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_trim.command('aplicar')
def comando_trim_aplicar(
    raiz: Path = typer.Argument(..., help='Carpeta que se quiere limpiar.'),
    incluir_venv: bool = typer.Option(
        False, '--incluir-venv', help='Incluye la carpeta .venv en el plan.'
    ),
    edad_dias: int = typer.Option(7, '--edad-dias', help='Solo limpia elementos viejos.'),
    forzar: bool = typer.Option(
        False, '--forzar', help='Aplica el plan moviendo a la papelera de Windows.'
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Solo mueve a papelera cuando el usuario acepta con --forzar.
    if not forzar:
        typer.echo('sin --forzar no se aplica el plan, usa trim escanear', err=True)
        raise typer.Exit(code=2)
    try:
        resultado = modulo_trim.aplicar_trim(raiz, incluir_venv, edad_dias)
    except ErrorBase as fallo:
        salir_con_error('trim aplicar', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_dedupe.command('escanear')
def comando_dedupe_escanear(
    raiz: Path = typer.Argument(..., help='Carpeta que se quiere escanear.'),
    edad_dias: int = typer.Option(30, '--edad-dias', help='Solo archivos mas viejos.'),
    no_ignorar_onedrive: bool = typer.Option(
        False,
        '--no-ignorar-onedrive',
        help='Permite entrar en rutas de OneDrive.',
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Genera el plan en solo lectura y lo muestra sin tocar el disco.
    try:
        ignorar = not no_ignorar_onedrive
        resultado = modulo_dedupe.escanear_dedupe(raiz, edad_dias, ignorar)
    except ErrorBase as fallo:
        salir_con_error('dedupe escanear', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_dedupe.command('aplicar')
def comando_dedupe_aplicar(
    raiz: Path = typer.Argument(..., help='Carpeta que se quiere deduplicar.'),
    edad_dias: int = typer.Option(30, '--edad-dias', help='Solo archivos mas viejos.'),
    no_ignorar_onedrive: bool = typer.Option(
        False,
        '--no-ignorar-onedrive',
        help='Permite entrar en rutas de OneDrive.',
    ),
    forzar: bool = typer.Option(
        False, '--forzar', help='Aplica el plan moviendo a la papelera de Windows.'
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Solo mueve a papelera cuando el usuario acepta con --forzar.
    if not forzar:
        typer.echo('sin --forzar no se aplica el plan, usa dedupe escanear', err=True)
        raise typer.Exit(code=2)
    try:
        ignorar = not no_ignorar_onedrive
        resultado = modulo_dedupe.aplicar_dedupe(raiz, edad_dias, ignorar)
    except ErrorBase as fallo:
        salir_con_error('dedupe aplicar', fallo, formato)
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
