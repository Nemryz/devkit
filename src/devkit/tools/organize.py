# Clasificacion por extension, firma binaria y año con plan previo.
from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

from devkit.core import paths, runlog, safety
from devkit.core import workspace as modulo_workspace
from devkit.errors import ErrorOrganizar

# Carpetas que nunca entran en el plan, igual que en el resto del toolkit.
CARPETAS_PROTEGIDAS = {'.git', '.devkit', '.idea', '.venv', '.vscode', 'src', 'tests'}
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
    manifest = []
    for a in acciones:
        ruta = Path(a['origen'])
        datos = ruta.stat() if ruta.exists() else None
        manifest.append(
            {
                'origen': a['origen'],
                'destino': a['destino'],
                'tipo': 'mover',
                'tamano': datos.st_size if datos else 0,
                'mtime': datos.st_mtime if datos else 0,
                'hash': safety.hash_contenido(ruta) if (datos and ruta.exists()) else None,
            }
        )
    return {
        'acciones': acciones,
        'manifest': manifest,
        'total': len(acciones),
        'total_bytes': total_bytes,
        'por_tipo': dict(sorted(por_tipo.items())),
        'por_anio': dict(sorted(por_anio.items())),
        'destino': str(carpeta_destino),
    }


def analizar_organize(
    raiz: Path,
    destino: Path | None = None,
    edad_dias: int = 0,
    ignorar_onedrive: bool = True,
) -> dict:
    # Analisis puro de organizacion, sin persistir manifiesto ni journal.
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    carpeta_destino = Path(destino).expanduser().resolve() if destino else base / 'Organizados'
    if str(carpeta_destino) == str(base):
        carpeta_destino = base / 'Organizados'
    archivos = recolectar_archivos(base, ignorar_onedrive, edad_dias)
    archivos = [ruta for ruta in archivos if carpeta_destino not in ruta.resolve().parents]
    plan = construir_plan(base, carpeta_destino, archivos)
    return {
        'herramienta': 'organize',
        'accion': 'analizar',
        'manifest': plan['manifest'],
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


def escanear_organize(
    raiz: Path,
    destino: Path | None = None,
    edad_dias: int = 0,
    ignorar_onedrive: bool = True,
) -> dict:
    # Construye el plan, guarda su manifiesto persistente y registra el escaneo.
    analisis = analizar_organize(raiz, destino, edad_dias, ignorar_onedrive)
    base = Path(analisis['raiz'])
    inicio = time.perf_counter()
    id_ejec = runlog.iniciar_ejecucion('organize', 'plan', espacio_trabajo=str(base))
    wid = modulo_workspace.workspace_id(base)
    ruta_plan = safety.guardar_plan(
        id_ejec, 'organize', analisis['manifest'], workspace_id=wid, workspace_root=str(base)
    )
    runlog.registrar_ejecucion(
        'organize', ['plan'], inicio, 0, 0, 'plan',
        espacio_trabajo=str(base), id_plan=id_ejec, id_ejecucion=id_ejec,
    )
    resultado = dict(analisis)
    resultado['accion'] = 'plan'
    resultado['plan_persistente'] = str(ruta_plan)
    return resultado


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


def _autorizar_por_archivo(siempre: bool):
    # Hook de autorizacion del ejecutor unico que delega cada paso en _confirmar.
    estado = {'siempre': siempre}

    def autorizar(accion: dict) -> bool:
        pregunta = dict(accion)
        respuesta = _confirmar(pregunta, estado['siempre'])
        if pregunta.get('_todos'):
            # La respuesta t del usuario cambia el resto de la tanda a aceptadas.
            estado['siempre'] = True
        return respuesta

    return autorizar


def aplicar_organize(
    raiz: Path,
    destino: Path | None = None,
    edad_dias: int = 0,
    ignorar_onedrive: bool = True,
    todos: bool = False,
    por_archivo: bool = False,
    plan_persistente: Path | None = None,
    dry_run: bool = False,
) -> dict:
    # Aplica (o simula) un manifiesto por el ejecutor unico, sin reescanear si ya existe.
    if not dry_run:
        safety.verificar_escritura('organizar archivos')
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    carpeta_destino = Path(destino).expanduser().resolve() if destino else base / 'Organizados'
    if str(carpeta_destino) == str(base):
        carpeta_destino = base / 'Organizados'
    if por_archivo and not todos and not dry_run:
        import sys

        if not sys.stdin.isatty():
            raise ErrorOrganizar('sin --todos ni tty no se puede confirmar archivo por archivo')
    ruta_plan = Path(plan_persistente).expanduser().resolve() if plan_persistente else None
    if ruta_plan is not None and not ruta_plan.is_file():
        raise ErrorOrganizar(f'no existe el plan {ruta_plan}')
    acciones = None
    if ruta_plan is None and dry_run:
        archivos = recolectar_archivos(base, ignorar_onedrive, edad_dias)
        archivos = [ruta for ruta in archivos if carpeta_destino not in ruta.resolve().parents]
        plan_local = construir_plan(base, carpeta_destino, archivos)
        acciones = plan_local['manifest']
    if ruta_plan is None and not dry_run:
        escaneo = escanear_organize(base, destino, edad_dias, ignorar_onedrive)
        ruta_plan = Path(escaneo['plan_persistente'])
    autorizar = None if (todos or dry_run) else _autorizar_por_archivo(False)
    if dry_run:
        if acciones is not None:
            resultado = safety._simular_acciones(acciones, 'organize', base, autorizar=autorizar)
        else:
            resultado = safety.simular_manifiesto(
                ruta_plan, 'organize', espacio_trabajo=str(base), autorizar=autorizar
            )
    else:
        resultado = safety.aplicar_manifiesto(
            ruta_plan, 'organize', espacio_trabajo=str(base), autorizar=autorizar
        )
    movidos = resultado['movidos']
    fallidos = resultado['fallidos']
    estado = 'simulado' if dry_run else ('correcto' if not fallidos else 'error')
    return {
        'herramienta': 'organize',
        'accion': 'aplicar',
        'estado': estado,
        'codigo': resultado['codigo'],
        'raiz': str(base),
        'destino': str(carpeta_destino),
        'total_movidos': len(movidos),
        'total_bytes': sum(int(a.get('tamano', 0)) for a in movidos),
        'movidos': movidos,
        'fallidos': fallidos,
        'estado_plan': resultado['estado_plan'],
        'id_ejecucion': resultado['id_ejecucion'],
        'plan_persistente': str(ruta_plan) if ruta_plan is not None else '',
        'fecha': datetime.now(UTC).isoformat(),
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
        'dry_run': dry_run,
        'estado_identidad': resultado.get('estado_identidad', 'sin_identidad'),
    }
