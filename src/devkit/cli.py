# Punto de entrada de la interfaz de linea de comandos del toolkit.
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import typer

from devkit import __version__
from devkit.core import capabilities as modulo_capacidades
from devkit.core import migracion as modulo_migracion
from devkit.core.output import emitir
from devkit.errors import ErrorBase
from devkit.tools import backup as modulo_respaldo
from devkit.tools import dedupe as modulo_dedupe
from devkit.tools import idea as modulo_idea
from devkit.tools import index as modulo_index
from devkit.tools import nice as modulo_nice
from devkit.tools import ocr as modulo_ocr
from devkit.tools import organize as modulo_organize
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
app_organize = typer.Typer(
    no_args_is_help=True,
    help='Clasificacion por extension, firma y año con plan previo.',
)
app.add_typer(app_organize, name='organize')
app_idea = typer.Typer(
    no_args_is_help=True,
    help='Notas Markdown con frontmatter validado y revision de enlaces.',
)
app.add_typer(app_idea, name='idea')
app_index = typer.Typer(
    no_args_is_help=True,
    help='Indice SQLite con FTS5 sobre las notas Markdown.',
)
app.add_typer(app_index, name='index')
app_ocr = typer.Typer(
    no_args_is_help=True,
    help='OCR en solo lectura con Tesseract y PyMuPDF.',
)
app.add_typer(app_ocr, name='ocr')


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


@app.command('capabilities')
def comando_capabilities(
    clase: str | None = typer.Option(
        None, '--clase', help='Filtrar por clase: capability, discovery, administration.'
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida, json o tabla.'),
) -> None:
    # Lista las capacidades de las herramientas para que agentes las descubran.
    clasificacion = modulo_capacidades.listar_clasificacion()
    capacidades = modulo_capacidades.listar_capacidades()
    if clase is not None:
        capacidades = [c for c in capacidades if c.get('clase') == clase]
        # Incluir comandos de discovery/administration si se filtra por clase.
        if clase in ('discovery', 'administration'):
            for nombre, cls in clasificacion.items():
                if cls == clase and not any(c['name'] == nombre for c in capacidades):
                    capacidades.append({'name': nombre, 'clase': cls})
    resultado = {
        'herramienta': 'devkit',
        'accion': 'capabilities',
        'estado': 'correcto',
        'codigo': 0,
        'version_contrato': modulo_capacidades.VERSION_CONTRATO,
        'contratos_soportados': list(modulo_capacidades.CONTRATOS_SOPORTADOS),
        'total': len(capacidades),
        'capacidades': capacidades,
    }
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app.command('describe')
def comando_describe(
    herramienta: str = typer.Argument(..., help='Nombre de la herramienta a describir.'),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida, json o tabla.'),
) -> None:
    # Describe una herramienta concreta con su contrato completo.
    capacidad = modulo_capacidades.obtener_capacidad(herramienta)
    if capacidad is None:
        emitir(
            {
                'herramienta': 'devkit',
                'accion': 'describe',
                'estado': 'error',
                'codigo': 2,
                'detalle': f'no existe la herramienta {herramienta}',
            },
            formato=formato,
        )
        raise typer.Exit(code=2)
    resultado = {
        'herramienta': 'devkit',
        'accion': 'describe',
        'estado': 'correcto',
        'codigo': 0,
        'capacidad': capacidad,
    }
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app.command('schema')
def comando_schema(
    herramienta: str = typer.Argument(..., help='Nombre de la herramienta.'),
    accion: str = typer.Argument(..., help='Accion (escanear, aplicar, plan, etc.).'),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Devuelve el esquema de entrada y salida de una accion concreta.
    capacidad = modulo_capacidades.obtener_capacidad(herramienta)
    if capacidad is None:
        emitir(
            {'herramienta': 'devkit', 'accion': 'schema', 'estado': 'error', 'codigo': 2,
             'detalle': f'no existe la herramienta {herramienta}'},
            formato=formato,
        )
        raise typer.Exit(code=2)
    entradas = capacidad.get('actions', {})
    salidas = capacidad.get('outputs', {})
    if accion not in entradas and accion not in salidas:
        emitir(
            {'herramienta': 'devkit', 'accion': 'schema', 'estado': 'error', 'codigo': 2,
             'detalle': f'no existe la accion {accion} en {herramienta}'},
            formato=formato,
        )
        raise typer.Exit(code=2)
    version_accion = int(capacidad.get('contrato_version', modulo_capacidades.VERSION_CONTRATO))
    if accion in entradas:
        try:
            version_accion = modulo_capacidades.version_contrato_de(herramienta, accion)
        except ErrorBase as fallo:
            salir_con_error('schema', fallo, formato)
            return
    resultado = {
        'herramienta': 'devkit',
        'accion': 'schema',
        'estado': 'correcto',
        'codigo': 0,
        'version_esquema': 1,
        'version_contrato': version_accion,
        'version_contrato_capacidad': capacidad.get('contrato_version'),
        'herramienta_objetivo': herramienta,
        'accion_objetivo': accion,
        'entrada': entradas.get(accion, {}).get('params', {}),
        'salida': entradas.get(accion, {}).get('outputs', salidas),
    }
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app.command('migrate')
def comando_migrate(
    ruta: Path = typer.Argument(..., help='Archivo de plan o configuracion a migrar.'),
    tipo: str = typer.Option(..., '--tipo', help='Tipo de dato, plan o config.'),
    desde: int | None = typer.Option(
        None, '--desde', help='Version de origen esperada.'
    ),
    hasta: int | None = typer.Option(
        None, '--hasta', help='Version de destino requerida.'
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Migra un plan o una configuracion y reporta la version de origen y la de destino.
    try:
        resultado = modulo_migracion.migrar(ruta, tipo, desde=desde, hasta=hasta)
    except ErrorBase as fallo:
        salir_con_error('migrate', fallo, formato)
        return
    salida = {
        'herramienta': 'devkit',
        'accion': 'migrate',
        'estado': 'correcto',
        'codigo': 0,
        **resultado,
    }
    emitir(salida, formato=formato)
    raise typer.Exit(code=0)


@app.command('buscar')
def comando_buscar(
    termino: str = typer.Argument(..., help='Termino a buscar e identificar.'),
    raiz: Path | None = typer.Option(None, '--raiz', '-r', help='Carpeta de trabajo.'),
    limite: int = typer.Option(20, '--limite', help='Maximo de resultados por fuente.'),
    duplicados: bool = typer.Option(
        False, '--duplicados', help='Incluir analisis de duplicados (hashea el arbol).'
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Busqueda e identificacion unificada, solo lectura, para usuarios y agentes.
    base = None
    try:
        base = modulo_index.raiz_efectiva(raiz)
    except Exception:  # noqa: BLE001
        base = raiz if raiz is not None else Path.cwd()
    resultados: dict[str, Any] = {
        'herramienta': 'devkit',
        'accion': 'buscar',
        'estado': 'correcto',
        'codigo': 0,
        'termino': termino,
        'raiz': str(base),
        'texto': None,
        'archivos': None,
        'duplicados': None,
    }
    # Texto en notas
    try:
        resultados['texto'] = modulo_index.buscar(base, termino, None, limite)
    except Exception as fallo:  # noqa: BLE001
        resultados['texto'] = {'estado': 'error', 'detalle': str(fallo)}
    # Identificacion de archivos (analisis puro, sin persistir)
    try:
        analisis = modulo_organize.analizar_organize(base)
        term_lower = termino.lower()
        filtrados = [
            a for a in analisis.get('acciones', [])
            if term_lower in str(a.get('origen', '')).lower()
            or term_lower in str(a.get('destino', '')).lower()
        ]
        analisis['acciones_filtradas'] = filtrados
        analisis['total_filtrados'] = len(filtrados)
        resultados['archivos'] = analisis
    except Exception as fallo:  # noqa: BLE001
        resultados['archivos'] = {'estado': 'error', 'detalle': str(fallo)}
    # Duplicados (opt-in)
    if duplicados:
        try:
            resultados['duplicados'] = modulo_dedupe.analizar_dedupe(base, edad_dias=30)
        except Exception as fallo:  # noqa: BLE001
            resultados['duplicados'] = {'estado': 'error', 'detalle': str(fallo)}
    else:
        resultados['duplicados'] = None
    # Determinar estado global y codigo de salida.
    fuentes_con_error = 0
    fuentes_evaluadas = 0
    val = resultados.get('texto')
    if isinstance(val, dict):
        fuentes_evaluadas += 1
        if val.get('estado') == 'error':
            fuentes_con_error += 1
    val = resultados.get('archivos')
    if isinstance(val, dict):
        fuentes_evaluadas += 1
        if val.get('estado') == 'error':
            fuentes_con_error += 1
    if duplicados:
        val = resultados.get('duplicados')
        if isinstance(val, dict):
            fuentes_evaluadas += 1
            if val.get('estado') == 'error':
                fuentes_con_error += 1
    if fuentes_con_error == 0:
        resultados['estado'] = 'correcto'
        resultados['codigo'] = 0
    elif fuentes_con_error < fuentes_evaluadas:
        resultados['estado'] = 'parcial'
        resultados['codigo'] = 1
    else:
        resultados['estado'] = 'error'
        resultados['codigo'] = 2
    emitir(resultados, formato=formato)
    raise typer.Exit(code=resultados['codigo'])
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
    dry_run: bool = typer.Option(
        False, '--dry-run', help='Simula la aplicacion sin tocar el disco.'
    ),
    reanudar: bool = typer.Option(
        False, '--reanudar', help='Reanuda una ejecucion interrumpida tras reconciliar.'
    ),
    plan: Path | None = typer.Option(
        None,
        '--plan',
        help='Aplica el manifiesto guardado por trim escanear sin reescanear.',
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # La politica del ejecutor exige --forzar antes de tocar la papelera.
    try:
        resultado = modulo_trim.aplicar_trim(
            raiz, incluir_venv, edad_dias, plan, dry_run=dry_run, reanudar=reanudar,
            forzar=forzar,
        )
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
    dry_run: bool = typer.Option(
        False, '--dry-run', help='Simula la aplicacion sin tocar el disco.'
    ),
    reanudar: bool = typer.Option(
        False, '--reanudar', help='Reanuda una ejecucion interrumpida tras reconciliar.'
    ),
    plan: Path | None = typer.Option(
        None,
        '--plan',
        help='Aplica el manifiesto guardado por dedupe escanear sin reescanear.',
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # La politica del ejecutor exige --forzar antes de tocar la papelera.
    try:
        ignorar = not no_ignorar_onedrive
        resultado = modulo_dedupe.aplicar_dedupe(
            raiz, edad_dias, ignorar, plan=plan, dry_run=dry_run, reanudar=reanudar,
            forzar=forzar,
        )
    except ErrorBase as fallo:
        salir_con_error('dedupe aplicar', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_organize.command('plan')
def comando_organize_plan(
    raiz: Path = typer.Argument(..., help='Carpeta que se quiere organizar.'),
    destino: Path | None = typer.Option(
        None, '--destino', '-d', help='Carpeta Organizados (por defecto raiz/Organizados).'
    ),
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
        resultado = modulo_organize.escanear_organize(raiz, destino, 0, ignorar)
    except ErrorBase as fallo:
        salir_con_error('organize plan', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_organize.command('aplicar')
def comando_organize_aplicar(
    raiz: Path = typer.Argument(..., help='Carpeta que se quiere organizar.'),
    destino: Path | None = typer.Option(
        None, '--destino', '-d', help='Carpeta Organizados.'
    ),
    todos: bool = typer.Option(
        False, '--todos', '-t', help='Selecciona todos los archivos sin confirmar uno a uno.'
    ),
    si: bool = typer.Option(
        False, '--si', '-s', help='Confirma la aplicacion del plan.'
    ),
    por_archivo: bool = typer.Option(
        False,
        '--por-archivo',
        help='Pregunta archivo por archivo (s/n/a/t).',
    ),
    no_ignorar_onedrive: bool = typer.Option(
        False,
        '--no-ignorar-onedrive',
        help='Permite entrar en rutas de OneDrive.',
    ),
    reanudar: bool = typer.Option(
        False, '--reanudar', help='Reanuda una ejecucion interrumpida tras reconciliar.'
    ),
    plan: Path | None = typer.Option(
        None,
        '--plan',
        help='Aplica el manifiesto guardado por organize plan sin reescanear.',
    ),
    dry_run: bool = typer.Option(
        False, '--dry-run', help='Simula la aplicacion sin tocar el disco.'
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # La seleccion no sustituye a la confirmacion: la politica exige --si.
    if not todos and not por_archivo:
        typer.echo('sin --todos ni --por-archivo no se aplica el plan', err=True)
        raise typer.Exit(code=2)
    try:
        ignorar = not no_ignorar_onedrive
        resultado = modulo_organize.aplicar_organize(
            raiz, destino, 0, ignorar, todos, por_archivo, plan, dry_run=dry_run,
            reanudar=reanudar, confirmar=si,
        )
    except ErrorBase as fallo:
        salir_con_error('organize aplicar', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_idea.command('crear')
def comando_idea_crear(
    raiz: Path = typer.Argument(..., help='Carpeta de notas.'),
    titulo: str = typer.Option(..., '--titulo', help='Titulo de la nota.'),
    cuerpo: str = typer.Option('', '--cuerpo', help='Cuerpo de la nota.'),
    etiquetas: list[str] = typer.Option(
        [], '--etiqueta', help='Etiqueta, se puede repetir.'
    ),
    estado: str = typer.Option('borrador', '--estado', help='borrador, activo o archivado.'),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Crea una nota con frontmatter validado y nombre estable.
    try:
        resultado = modulo_idea.crear_nota(raiz, titulo, cuerpo, etiquetas, estado)
    except ErrorBase as fallo:
        salir_con_error('idea crear', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_idea.command('revisar')
def comando_idea_revisar(
    raiz: Path = typer.Argument(..., help='Carpeta de notas.'),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Revisa frontmatter y enlaces sin tocar el disco.
    try:
        resultado = modulo_idea.revisar_notas(raiz)
    except ErrorBase as fallo:
        salir_con_error('idea revisar', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_idea.command('listar')
def comando_idea_listar(
    raiz: Path = typer.Argument(..., help='Carpeta de notas.'),
    estado: str | None = typer.Option(None, '--estado', help='Filtra por estado.'),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Lista las notas con su frontmatter resumido.
    try:
        resultado = modulo_idea.listar_notas(raiz, estado)
    except ErrorBase as fallo:
        salir_con_error('idea listar', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_index.command('construir')
def comando_index_construir(
    raiz: Path = typer.Argument(..., help='Carpeta de notas.'),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Reconstruye el indice FTS5 completo.
    try:
        resultado = modulo_index.construir_indice(raiz)
    except ErrorBase as fallo:
        salir_con_error('index construir', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_index.command('buscar')
def comando_index_buscar(
    termino: str = typer.Argument(..., help='Termino a buscar.'),
    raiz: Path | None = typer.Option(None, '--raiz', '-r', help='Carpeta de notas.'),
    estado: str | None = typer.Option(None, '--estado', help='Filtra por estado.'),
    limite: int = typer.Option(20, '--limite', help='Maximo de resultados.'),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Busca en el indice FTS5 y devuelve fragmentos.
    try:
        resultado = modulo_index.buscar(raiz, termino, estado, limite)
    except ErrorBase as fallo:
        salir_con_error('index buscar', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_index.command('actualizar')
def comando_index_actualizar(
    raiz: Path = typer.Argument(..., help='Carpeta de notas.'),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Actualiza el indice de forma incremental.
    try:
        resultado = modulo_index.actualizar_indice(raiz)
    except ErrorBase as fallo:
        salir_con_error('index actualizar', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_index.command('exportar')
def comando_index_exportar(
    salida: Path = typer.Argument(..., help='Archivo JSON de salida.'),
    raiz: Path | None = typer.Option(None, '--raiz', '-r', help='Carpeta de notas.'),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Exporta el indice a JSON para revisarlo fuera de SQLite.
    try:
        bd = modulo_index.ruta_indice(modulo_index.raiz_efectiva(raiz), crear=False)
        resultado = modulo_index.exportar_indice(bd, salida)
    except ErrorBase as fallo:
        salir_con_error('index exportar', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_ocr.command('escanear')
def comando_ocr_escanear(
    raiz: Path = typer.Argument(..., help='Carpeta con PDFs e imagenes.'),
    idioma: str = typer.Option('spa', '--idioma', help='Idioma Tesseract.'),
    no_ignorar_onedrive: bool = typer.Option(
        False,
        '--no-ignorar-onedrive',
        help='Permite entrar en rutas de OneDrive.',
    ),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Extrae texto en solo lectura y devuelve metricas por archivo.
    try:
        ignorar = not no_ignorar_onedrive
        resultado = modulo_ocr.escanear_ocr(raiz, idioma, ignorar)
    except ErrorBase as fallo:
        salir_con_error('ocr escanear', fallo, formato)
        return
    emitir(resultado, formato=formato)
    raise typer.Exit(code=resultado['codigo'])


@app_ocr.command('exportar')
def comando_ocr_exportar(
    raiz: Path = typer.Argument(..., help='Carpeta con PDFs e imagenes.'),
    destino: Path | None = typer.Option(
        None, '--destino', '-d', help='Carpeta de salida (defecto raiz/OCR).'
    ),
    idioma: str = typer.Option('spa', '--idioma', help='Idioma Tesseract.'),
    formato: str = typer.Option('json', '--formato', '-f', help='Formato de salida.'),
) -> None:
    # Genera notas con origen ocr listas para idea e index.
    try:
        resultado = modulo_ocr.exportar_ocr(raiz, destino, idioma)
    except ErrorBase as fallo:
        salir_con_error('ocr exportar', fallo, formato)
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
