# Respaldos cifrados con manifiesto de hashes y verificacion obligatoria.
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from devkit.core import paths, runlog, safety
from devkit.errors import ErrorBase, ErrorClave, ErrorProceso, ErrorRespaldo

NOMBRE_MANIFIESTO = 'manifiesto.json'
NOMBRE_ARCHIVO = 'respaldo.tar.7z'
NOMBRE_TAR = 'respaldo.tar'
VERSION_MANIFIESTO = 1
BLOQUE_LECTURA = 1024 * 1024
TIEMPO_MAXIMO = 3600
CARPETAS_EXCLUIDAS = {
    '.git',
    '.idea',
    '.mypy_cache',
    '.pytest_cache',
    '.ruff_cache',
    '.venv',
    '.vscode',
    '__pycache__',
    'htmlcov',
    'node_modules',
}
RUTAS_SIETE = (
    Path('C:/Program Files/7-Zip/7z.exe'),
    Path('C:/Program Files (x86)/7-Zip/7z.exe'),
)


def encontrar_siete() -> Path | None:
    # Busca 7z en el PATH y en las ubicaciones habituales de Windows.
    encontrado = shutil.which('7z') or shutil.which('7za')
    if encontrado:
        return Path(encontrado)
    for candidato in RUTAS_SIETE:
        if candidato.is_file():
            return candidato
    return None


def calcular_sha256(ruta: Path) -> str:
    # Lee por bloques para no cargar archivos grandes en memoria.
    resumen = hashlib.sha256()
    try:
        with ruta.open('rb') as archivo:
            for bloque in iter(lambda: archivo.read(BLOQUE_LECTURA), b''):
                resumen.update(bloque)
    except OSError as fallo:
        raise ErrorRespaldo(f'no se puede leer {ruta} porque {fallo}') from fallo
    return resumen.hexdigest()


def nombre_respaldo(etiqueta: str) -> str:
    # Sanea la etiqueta para que el nombre de carpeta sea portable.
    marca = datetime.now().strftime('%Y%m%d-%H%M%S')
    limpia = ''.join(caracter for caracter in etiqueta if caracter.isalnum() or caracter in '-_')
    return f'{marca}-{limpia}' if limpia else marca


def validar_origenes(origenes: list[Path]) -> list[Path]:
    # Rechaza rutas inexistentes antes de construir cualquier plan.
    if not origenes:
        raise ErrorRespaldo('hace falta al menos un origen')
    limpios = []
    for origen in origenes:
        ruta = origen.expanduser().resolve()
        if not ruta.is_dir():
            raise ErrorRespaldo(f'el origen no es una carpeta {ruta}')
        limpios.append(ruta)
    return limpios


def validar_destino(destino: Path, origenes: list[Path]) -> Path:
    # Impide guardar el respaldo dentro de lo que se esta respaldando.
    ruta = destino.expanduser().resolve()
    for origen in origenes:
        if ruta == origen or origen in ruta.parents:
            raise ErrorRespaldo(f'el destino no puede estar dentro del origen {origen}')
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def recolectar_archivos(origenes: list[Path]) -> tuple[list[dict], list[tuple[Path, str]]]:
    # Recorre sin seguir enlaces y registra tamano y hash de cada archivo.
    registros = []
    pares = []
    for origen in origenes:
        prefijo = origen.name or 'origen'
        for carpeta, subcarpetas, archivos in os.walk(origen, followlinks=False):
            subcarpetas[:] = sorted(
                nombre for nombre in subcarpetas if nombre not in CARPETAS_EXCLUIDAS
            )
            for nombre in sorted(archivos):
                ruta = Path(carpeta) / nombre
                if ruta.is_symlink() or ruta.is_junction():
                    continue
                relativa = ruta.relative_to(origen).as_posix()
                destino = f'{prefijo}/{relativa}'
                datos = ruta.stat()
                registros.append(
                    {
                        'ruta': destino,
                        'tamano': datos.st_size,
                        'sha256': calcular_sha256(ruta),
                        'modificado': datetime.fromtimestamp(datos.st_mtime, UTC).isoformat(),
                    }
                )
                pares.append((ruta, destino))
    return registros, pares


def _crear_tar(pares: list[tuple[Path, str]], ruta_tar: Path) -> None:
    # Empaqueta con nombres relativos para que el respaldo no dependa del perfil.
    try:
        with tarfile.open(ruta_tar, 'w') as archivo_tar:
            for ruta, nombre in pares:
                archivo_tar.add(str(ruta), arcname=nombre, recursive=False)
    except (OSError, tarfile.TarError) as fallo:
        raise ErrorRespaldo(f'no se pudo empaquetar el respaldo porque {fallo}') from fallo


def ejecutar_siete(comando: list[str], entrada: str = '') -> None:
    # Ejecuta 7z con la clave por entrada estandar para no exponerla en el proceso.
    proceso = None
    try:
        proceso = subprocess.Popen(
            comando,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        salida, error = proceso.communicate(input=entrada, timeout=TIEMPO_MAXIMO)
    except FileNotFoundError as fallo:
        raise ErrorProceso('no se encontro el ejecutable de 7z') from fallo
    except subprocess.TimeoutExpired as fallo:
        if proceso is not None:
            proceso.kill()
        raise ErrorProceso('7z supero el tiempo maximo permitido') from fallo
    if proceso.returncode != 0:
        lineas = (error or salida or '').strip().splitlines()
        ultimo = lineas[-1] if lineas else 'sin detalle'
        raise ErrorRespaldo(f'7z fallo con codigo {proceso.returncode} y detalle {ultimo}')


def comprimir(ruta_tar: Path, ruta_salida: Path, clave: str | None) -> None:
    # Cifra con AES-256 y cabecera cifrada cuando hay clave disponible.
    siete = encontrar_siete()
    if siete is None:
        raise ErrorRespaldo('no se encontro 7z, instala 7-Zip para crear respaldos')
    comando = [str(siete), 'a', '-t7z', '-mx=5', '-mhe=on', '-y', str(ruta_salida), str(ruta_tar)]
    entrada = ''
    if clave:
        comando.insert(2, '-p')
        entrada = clave + '\n'
    ejecutar_siete(comando, entrada)


def descomprimir(ruta_archivo: Path, destino: Path, clave: str | None) -> None:
    # Extrae el contenedor 7z a una carpeta temporal controlada.
    siete = encontrar_siete()
    if siete is None:
        raise ErrorRespaldo('no se encontro 7z, instala 7-Zip para leer respaldos')
    destino.mkdir(parents=True, exist_ok=True)
    # 7z lee la clave de la entrada estandar sin -p al extraer, igual que al probar.
    comando = [str(siete), 'x', '-y', f'-o{destino}', str(ruta_archivo)]
    entrada = ''
    if clave:
        entrada = clave + '\n'
    ejecutar_siete(comando, entrada)


def extraer_tar(ruta_tar: Path, destino: Path) -> None:
    # Usa el filtro de datos para rechazar rutas absolutas y saltos de directorio.
    destino.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(ruta_tar) as archivo_tar:
            archivo_tar.extractall(destino, filter='data')
    except (OSError, tarfile.TarError) as fallo:
        raise ErrorRespaldo(f'no se pudo extraer el contenido porque {fallo}') from fallo


def comparar(base: Path, manifiesto: dict) -> dict:
    # Confirma que cada archivo del manifiesto existe y conserva su hash.
    correctos = 0
    faltantes = []
    alterados = []
    for registro in manifiesto.get('archivos', []):
        ruta = base / registro['ruta']
        if not ruta.is_file():
            faltantes.append(registro['ruta'])
        elif calcular_sha256(ruta) != registro['sha256']:
            alterados.append(registro['ruta'])
        else:
            correctos += 1
    return {'correctos': correctos, 'faltantes': faltantes, 'alterados': alterados}


def leer_manifiesto(carpeta: Path) -> dict:
    # Rechaza manifiestos ausentes, dañados o de una version desconocida.
    ruta = carpeta / NOMBRE_MANIFIESTO
    if not ruta.is_file():
        raise ErrorRespaldo(f'no existe el manifiesto en {carpeta}')
    try:
        with ruta.open('r', encoding='utf-8') as archivo:
            datos = json.load(archivo)
    except (OSError, json.JSONDecodeError) as fallo:
        raise ErrorRespaldo(f'el manifiesto esta dañado en {carpeta}') from fallo
    if datos.get('version') != VERSION_MANIFIESTO:
        raise ErrorRespaldo(f'version de manifiesto no soportada en {carpeta}')
    return datos


def _escribir_manifiesto(carpeta: Path, manifiesto: dict) -> None:
    ruta = carpeta / NOMBRE_MANIFIESTO
    try:
        ruta.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError as fallo:
        raise ErrorRespaldo(f'no se pudo escribir el manifiesto porque {fallo}') from fallo


def _carpeta_nueva(base: Path, etiqueta: str) -> Path:
    # Evita colisiones cuando se crean dos respaldos en el mismo segundo.
    nombre = nombre_respaldo(etiqueta)
    candidata = base / nombre
    contador = 2
    while candidata.exists():
        candidata = base / f'{nombre}-{contador}'
        contador += 1
    candidata.mkdir(parents=True)
    return candidata


def obtener_clave(ruta_clave: str | None) -> str | None:
    # Prioriza el archivo indicado, luego la variable y por ultimo la consola.
    if ruta_clave:
        archivo = Path(ruta_clave).expanduser()
        if not archivo.is_file():
            raise ErrorClave(f'no existe el archivo de clave {archivo}')
        lineas = archivo.read_text(encoding='utf-8').splitlines()
        if not lineas or not lineas[0].strip():
            raise ErrorClave('el archivo de clave esta vacio')
        return lineas[0].strip()
    valor = os.environ.get('DEVKIT_CLAVE', '').strip()
    if valor:
        return valor
    if sys.stdin.isatty():
        import getpass

        return getpass.getpass('clave del respaldo ')
    raise ErrorClave('no hay clave disponible, usa --clave o la variable DEVKIT_CLAVE')


def crear_respaldo(
    origenes: list[Path],
    destino: Path | None = None,
    etiqueta: str = '',
    clave: str | None = None,
    cifrado: bool = True,
) -> dict:
    # Construye el respaldo completo y deja el resumen listo para la salida comun.
    safety.verificar_escritura('crear un respaldo')
    inicio = time.perf_counter()
    limpios = validar_origenes(origenes)
    base = validar_destino(destino or paths.directorio_respaldos(), limpios)
    if cifrado and not clave:
        raise ErrorClave('el respaldo cifrado necesita una clave')
    carpeta = _carpeta_nueva(base, etiqueta)
    registros, pares = recolectar_archivos(limpios)
    ruta_tar = carpeta / NOMBRE_TAR
    ruta_salida = carpeta / NOMBRE_ARCHIVO
    try:
        _crear_tar(pares, ruta_tar)
        comprimir(ruta_tar, ruta_salida, clave if cifrado else None)
    finally:
        if ruta_tar.exists():
            ruta_tar.unlink()
    manifiesto = {
        'version': VERSION_MANIFIESTO,
        'fecha': datetime.now(UTC).isoformat(),
        'etiqueta': etiqueta,
        'archivo': NOMBRE_ARCHIVO,
        'contenido': NOMBRE_TAR,
        'cifrado': cifrado,
        'origenes': [str(ruta) for ruta in limpios],
        'total_archivos': len(registros),
        'total_bytes': sum(registro['tamano'] for registro in registros),
        'archivos': registros,
    }
    _escribir_manifiesto(carpeta, manifiesto)
    duracion = round((time.perf_counter() - inicio) * 1000, 1)
    runlog.registrar_ejecucion('backup', ['crear', etiqueta], inicio, 0, 0, 'crear')
    return {
        'herramienta': 'backup',
        'accion': 'crear',
        'estado': 'correcto',
        'codigo': 0,
        'carpeta': str(carpeta),
        'archivo': str(ruta_salida),
        'cifrado': cifrado,
        'total_archivos': len(registros),
        'total_bytes': manifiesto['total_bytes'],
        'duracion_ms': duracion,
    }


def _extraer_paquete(carpeta: Path, manifiesto: dict, destino: Path, clave: str | None) -> Path:
    # Descomprime el contenedor y devuelve la ruta del tar interno.
    archivo = carpeta / manifiesto['archivo']
    if not archivo.is_file():
        raise ErrorRespaldo(f'no existe el archivo de respaldo en {carpeta}')
    empaquetado = destino / '_empaquetado'
    descomprimir(archivo, empaquetado, clave if manifiesto.get('cifrado') else None)
    ruta_tar = empaquetado / manifiesto.get('contenido', NOMBRE_TAR)
    if not ruta_tar.is_file():
        raise ErrorRespaldo('el contenedor no tiene el archivo interno esperado')
    return ruta_tar


def verificar_respaldo(carpeta: Path, clave: str | None = None) -> dict:
    # Extrae en una carpeta temporal y compara cada hash con el manifiesto.
    inicio = time.perf_counter()
    ruta_carpeta = carpeta.expanduser().resolve()
    manifiesto = leer_manifiesto(ruta_carpeta)
    with tempfile.TemporaryDirectory(prefix='devkit-verificar-') as temporal:
        base = Path(temporal)
        ruta_tar = _extraer_paquete(ruta_carpeta, manifiesto, base, clave)
        contenido = base / 'contenido'
        extraer_tar(ruta_tar, contenido)
        resultado = comparar(contenido, manifiesto)
    estado = 'correcto' if not resultado['faltantes'] and not resultado['alterados'] else 'error'
    codigo = 0 if estado == 'correcto' else 2
    runlog.registrar_ejecucion('backup', ['verificar'], inicio, codigo, 0, estado)
    return {
        'herramienta': 'backup',
        'accion': 'verificar',
        'estado': estado,
        'codigo': codigo,
        'carpeta': str(ruta_carpeta),
        'correctos': resultado['correctos'],
        'faltantes': resultado['faltantes'],
        'alterados': resultado['alterados'],
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }


def restaurar_respaldo(
    carpeta: Path,
    destino: Path,
    clave: str | None = None,
    forzar: bool = False,
) -> dict:
    # Restaura sobre una carpeta vacia y comprueba la integridad al terminar.
    safety.verificar_escritura('restaurar un respaldo')
    inicio = time.perf_counter()
    ruta_carpeta = carpeta.expanduser().resolve()
    manifiesto = leer_manifiesto(ruta_carpeta)
    ruta_destino = destino.expanduser().resolve()
    if ruta_destino.exists() and any(ruta_destino.iterdir()) and not forzar:
        raise ErrorRespaldo(f'el destino no esta vacio {ruta_destino}')
    ruta_destino.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='devkit-restaurar-') as temporal:
        ruta_tar = _extraer_paquete(ruta_carpeta, manifiesto, Path(temporal), clave)
        extraer_tar(ruta_tar, ruta_destino)
    resultado = comparar(ruta_destino, manifiesto)
    estado = 'correcto' if not resultado['faltantes'] and not resultado['alterados'] else 'error'
    codigo = 0 if estado == 'correcto' else 2
    runlog.registrar_ejecucion('backup', ['restaurar'], inicio, codigo, 0, estado)
    return {
        'herramienta': 'backup',
        'accion': 'restaurar',
        'estado': estado,
        'codigo': codigo,
        'carpeta': str(ruta_carpeta),
        'destino': str(ruta_destino),
        'correctos': resultado['correctos'],
        'faltantes': resultado['faltantes'],
        'alterados': resultado['alterados'],
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }


def listar_respaldos(destino: Path | None = None) -> dict:
    # Resume los respaldos disponibles sin abrir los contenedores.
    base = (destino or paths.directorio_respaldos()).expanduser()
    elementos = []
    if base.is_dir():
        for carpeta in sorted(base.iterdir(), reverse=True):
            if not carpeta.is_dir() or not (carpeta / NOMBRE_MANIFIESTO).is_file():
                continue
            try:
                manifiesto = leer_manifiesto(carpeta)
            except ErrorBase:
                elementos.append({'carpeta': str(carpeta), 'estado': 'dañado'})
                continue
            elementos.append(
                {
                    'carpeta': str(carpeta),
                    'etiqueta': manifiesto.get('etiqueta', ''),
                    'fecha': manifiesto.get('fecha', ''),
                    'cifrado': manifiesto.get('cifrado', False),
                    'total_archivos': manifiesto.get('total_archivos', 0),
                    'total_bytes': manifiesto.get('total_bytes', 0),
                    'estado': 'correcto',
                }
            )
    return {
        'herramienta': 'backup',
        'accion': 'listar',
        'estado': 'correcto',
        'codigo': 0,
        'carpeta': str(base),
        'total': len(elementos),
        'respaldos': elementos,
    }
