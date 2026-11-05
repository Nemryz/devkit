# Clasificacion por extension, firma binaria y año con plan previo.
from __future__ import annotations

import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from devkit.core import paths, runlog, safety
from devkit.errors import ErrorOrganizar

# Carpetas que nunca entran en el plan, igual que en el resto del toolkit.
CARPETAS_PROTEGIDAS = {'.git', '.idea', '.venv', '.vscode', 'src', 'tests'}
# Tabla de firmas binarias por magic number inicial y tipo.
FIRMAS = (
    (b'\xff\xd8\xff', 'imagen', '.jpg'),
    (b'\x89PNG', 'imagen', '.png'),
    (b'GIF8', 'imagen', '.gif'),
    (b'%PDF-', 'documento', '.pdf'),
    (b'PK\x03\x04', 'zip', '.zip'),
    (b'\x1f\x8b', 'zip', '.gz'),
    (b'ID3', 'audio', '.mp3'),
    (b'\xff\xfb', 'audio', '.mp3'),
    (b'OggS', 'audio', '.ogg'),
    (b'\x00\x00\x00\x18ftyp', 'video', '.mp4'),
    (b'\x00\x00\x00\x20ftyp', 'video', '.mp4'),
    (b'RIFF', 'video', '.avi'),
    (b'RIFF', 'audio', '.wav'),
    (b'7z\xbc\xaf', 'zip', '.7z'),
    (b'Rar!', 'zip', '.rar'),
    (b'\x1aE\xdf\xa3', 'video', '.mkv'),
)
# Tipos aceptados como nombre de carpeta por defecto.
TIPOS = {'imagen', 'audio', 'video', 'documento', 'zip', 'otros'}


def validar_raiz(raiz: Path | str) -> Path:
    # Comprueba que la raiz exista y que no sea una unidad completa.
    ruta = Path(raiz).expanduser().resolve()
    if not ruta.is_dir():
        raise ErrorOrganizar(f'la raiz no existe o no es carpeta {ruta}')
    if str(ruta) == str(ruta.anchor):
        raise ErrorOrganizar(f'la raiz no puede ser la unidad completa {ruta}')
    return ruta


def _esta_protegida(raiz: Path, ruta: Path) -> bool:
    # Una ruta queda protegida si alguna de sus partes es una carpeta prohibida.
    if ruta == raiz:
        return False
    return any(parte in CARPETAS_PROTEGIDAS for parte in ruta.relative_to(raiz).parts)


def detectar_tipo(ruta: Path) -> tuple[str, str]:
    # Lee los primeros bytes y cae a la extension si la firma no coincide.
    sufijo = ruta.suffix.lower()
    try:
        with ruta.open('rb') as archivo:
            cabecera = archivo.read(16)
    except OSError:
        cabecera = b''
    for firma, tipo, ext in FIRMAS:
        if cabecera.startswith(firma):
            # Formato real en el caso de RIFF necesita mirar dentro de la cabecera.
            if firma == b'RIFF' and len(cabecera) >= 12:
                tipo_interno = cabecera[8:12]
                if tipo_interno == b'WAVE':
                    return 'audio', '.wav'
                if tipo_interno == b'AVI ':
                    return 'video', '.avi'
            return tipo, ext
    if sufijo in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff'}:
        return 'imagen', sufijo if sufijo != '.jpeg' else '.jpg'
    if sufijo in {'.mp3', '.ogg', '.wav', '.flac', '.m4a'}:
        return 'audio', sufijo
    if sufijo in {'.mp4', '.mkv', '.avi', '.mov', '.webm'}:
        return 'video', sufijo
    if sufijo in {'.pdf', '.txt', '.md', '.csv', '.docx', '.xlsx', '.pptx', '.json'}:
        return 'documento', sufijo
    if sufijo in {'.zip', '.rar', '.7z', '.tar', '.gz'}:
        return 'zip', sufijo
    if sufijo:
        # .txt y similares que no coinciden con firma caen a documento por extension.
        return 'documento' if sufijo in {'.txt', '.md', '.csv', '.json'} else 'otros', sufijo
    return 'otros', ''


def anio_archivo(ruta: Path) -> str:
    # Usa el año de modificacion y cae al actual si falla la lectura.
    try:
        return str(datetime.fromtimestamp(ruta.stat().st_mtime).year)
    except OSError:
        return str(datetime.now().year)


def recolectar_archivos(raiz: Path, ignorar_onedrive: bool, edad_dias: int = 0) -> list[Path]:
    # Recorre sin seguir enlaces y devuelve los archivos dentro de la raiz.
    base = validar_raiz(raiz)
    corte = time.time() - edad_dias * 86400 if edad_dias else 0
    archivos: list[Path] = []
    for carpeta, subcarpetas, entradas in os.walk(base, followlinks=False):
        ruta_carpeta = Path(carpeta)
        conservadas = []
        for nombre in sorted(subcarpetas):
            ruta_sub = ruta_carpeta / nombre
            if ruta_sub.is_symlink() or ruta_sub.is_junction():
                continue
            if nombre in CARPETAS_PROTEGIDAS:
                continue
            conservadas.append(nombre)
        subcarpetas[:] = conservadas
        partes = ruta_carpeta.relative_to(base).parts
        if partes and any(parte in CARPETAS_PROTEGIDAS for parte in partes):
            continue
        for nombre in sorted(entradas):
            ruta = ruta_carpeta / nombre
            if ruta.is_symlink() or ruta.is_junction() or ruta.is_dir():
                continue
            if _esta_protegida(base, ruta):
                continue
            try:
                datos = ruta.stat()
            except OSError:
                continue
            if corte and datos.st_mtime >= corte:
                continue
            if ignorar_onedrive and paths.es_onedrive(ruta):
                continue
            archivos.append(ruta)
    archivos.sort()
    return archivos


def construir_plan(raiz: Path, destino: Path, archivos: list[Path]) -> dict:
    # Propone la ruta de cada archivo con <anio>/<tipo>/<nombre> y resuelve colisiones.
    base = validar_raiz(raiz)
    carpeta_destino = Path(destino).expanduser().resolve()
    ocupadas: set[str] = set()
    # Las ocupadas al inicio evitan pisar archivos ya organizados.
    if carpeta_destino.is_dir():
        for ruta in carpeta_destino.rglob('*'):
            if ruta.is_file():
                ocupadas.add(str(ruta).lower())
    acciones = []
    for ruta in archivos:
        tipo, ext = detectar_tipo(ruta)
        anio = anio_archivo(ruta)
        nombre = ruta.name
        propuesta = carpeta_destino / anio / tipo / nombre
        candidato = propuesta
        contador = 2
        while str(candidato).lower() in ocupadas or candidato.exists():
            # Consigue el stem sin la ultima extension para mantener formato.
            base_nombre = ruta.stem
            candidato = carpeta_destino / anio / tipo / f'{base_nombre}_{contador}{ruta.suffix}'
            contador += 1
        ocupadas.add(str(candidato).lower())
        acciones.append(
            {
                'tipo': 'mover',
                'origen': str(ruta),
                'destino': str(candidato),
                'anio': anio,
                'extension_tipo': tipo,
                'extension_real': ext,
                'nombre': ruta.relative_to(base).as_posix(),
            }
        )
    por_tipo: dict[str, int] = {}
    por_anio: dict[str, int] = {}
    for accion in acciones:
        por_tipo[accion['extension_tipo']] = por_tipo.get(accion['extension_tipo'], 0) + 1
        por_anio[accion['anio']] = por_anio.get(accion['anio'], 0) + 1
    total_bytes = sum(
        Path(a['origen']).stat().st_size for a in acciones if Path(a['origen']).exists()
    )
    return {
        'acciones': acciones,
        'total': len(acciones),
        'total_bytes': total_bytes,
        'por_tipo': dict(sorted(por_tipo.items())),
        'por_anio': dict(sorted(por_anio.items())),
        'destino': str(carpeta_destino),
    }


def _mover(origen: Path, destino: Path) -> None:
    # Mueve dentro del mismo volumen o entre volumenes con copia y borrado.
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        if origen.parent == destino.parent:
            origen.replace(destino)
        else:
            # shutil.move conserva enlaces, asi que no aplica a simbolicos ya filtrados.
            shutil.move(str(origen), str(destino))
    except OSError as fallo:
        raise ErrorOrganizar(f'no se pudo mover {origen} a {destino} porque {fallo}') from fallo


def escanear_organize(
    raiz: Path,
    destino: Path | None = None,
    edad_dias: int = 0,
    ignorar_onedrive: bool = True,
) -> dict:
    # Construye el plan sin tocar el disco y lo registra en el journal.
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    carpeta_destino = Path(destino).expanduser().resolve() if destino else base / 'Organizados'
    if str(carpeta_destino) == str(base):
        carpeta_destino = base / 'Organizados'
    archivos = recolectar_archivos(base, ignorar_onedrive, edad_dias)
    # No reescanear el destino ya organizado.
    archivos = [ruta for ruta in archivos if carpeta_destino not in ruta.resolve().parents]
    plan = construir_plan(base, carpeta_destino, archivos)
    runlog.registrar_ejecucion('organize', ['plan'], inicio, 0, 0, 'plan')
    return {
        'herramienta': 'organize',
        'accion': 'plan',
        'estado': 'correcto',
        'codigo': 0,
        'raiz': str(base),
        'destino': str(carpeta_destino),
        'total_archivos': len(archivos),
        'total': plan['total'],
        'total_bytes': plan['total_bytes'],
        'por_tipo': plan['por_tipo'],
        'por_anio': plan['por_anio'],
        'acciones': plan['acciones'],
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }


def _confirmar(accion: dict, siempre: bool) -> bool:
    # Pregunta por canal interactivo cuando no se acepta todos de golpe.
    import sys

    if siempre:
        return True
    if not sys.stdin.isatty():
        return False
    print(f"{accion['origen']} -> {accion['destino']} s/n/a/t ")
    try:
        respuesta = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if respuesta in {'s', 'si', 'y', 'yes'}:
        return True
    if respuesta == 't':
        # Escribe en el estado compartido del caller mediante propiedad.
        accion['_todos'] = True
        return True
    return respuesta != 'a'


def aplicar_organize(
    raiz: Path,
    destino: Path | None = None,
    edad_dias: int = 0,
    ignorar_onedrive: bool = True,
    todos: bool = False,
    por_archivo: bool = False,
) -> dict:
    # Ejecuta el plan moviendo cada archivo a su ruta propuesta.
    safety.verificar_escritura('organizar archivos')
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    carpeta_destino = Path(destino).expanduser().resolve() if destino else base / 'Organizados'
    if str(carpeta_destino) == str(base):
        carpeta_destino = base / 'Organizados'
    archivos = recolectar_archivos(base, ignorar_onedrive, edad_dias)
    archivos = [ruta for ruta in archivos if carpeta_destino not in ruta.resolve().parents]
    plan = construir_plan(base, carpeta_destino, archivos)
    if por_archivo and not todos:
        # Sin --todos y sin reloj interactivo, aborta para obligar a elegir el modo.
        import sys

        if not sys.stdin.isatty():
            raise ErrorOrganizar('sin --todos ni tty no se puede confirmar archivo por archivo')
    movidos = []
    fallidos = []
    siempre = todos
    abortar = False
    for accion in plan['acciones']:
        if abortar:
            break
        accion['_todos'] = siempre
        if _confirmar(accion, siempre):
            if accion.get('_todos'):
                siempre = True
            try:
                origen = Path(accion['origen'])
                if not origen.is_file():
                    fallidos.append({'ruta': accion['origen'], 'detalle': 'ya no existe'})
                    continue
                # Si el arbol cambio entre plan y aplicar, se aborta para no pisar.
                nombre = accion['origen']
                if origen.resolve() != Path(nombre).resolve() and (
                    origen.stat().st_mtime != Path(nombre).stat().st_mtime
                ):
                    fallidos.append({'ruta': nombre, 'detalle': 'cambio entre plan y aplicar'})
                    continue
                _mover(origen, Path(accion['destino']))
                movidos.append({k: v for k, v in accion.items() if not k.startswith('_')})
            except ErrorOrganizar as fallo:
                fallidos.append({'ruta': accion['origen'], 'detalle': str(fallo)})
        else:
            # Si el usuario pulsa 'a' esperaba abortar, lo trata como omitido.
            if accion.get('_todos') is False and not siempre:
                # Omision normal, sin detalle.
                pass
    estado = 'correcto' if not fallidos else 'error'
    codigo = 0 if estado == 'correcto' else 2
    runlog.registrar_ejecucion('organize', ['aplicar'], inicio, codigo, 0, estado)
    return {
        'herramienta': 'organize',
        'accion': 'aplicar',
        'estado': estado,
        'codigo': codigo,
        'raiz': str(base),
        'destino': str(carpeta_destino),
        'total_movidos': len(movidos),
        'total_bytes': sum(
            Path(m['origen']).stat().st_size if Path(m['origen']).exists() else 0 for m in movidos
        )
        if movidos
        else 0,
        'movidos': movidos,
        'fallidos': fallidos,
        'fecha': datetime.now(UTC).isoformat(),
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }
