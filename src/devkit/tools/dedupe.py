# Deteccion de duplicados exactos con plan previo y papelera de Windows.
from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

from devkit.core import paths, runlog, safety
from devkit.core import workspace as modulo_workspace
from devkit.errors import ErrorDuplicados

# Carpetas que nunca entran en el escaneo, igual que en trim.
CARPETAS_PROTEGIDAS = {'.git', '.devkit', '.idea', '.venv', '.vscode', 'src', 'tests'}
# Tropieza por defecto para no mover mas de esto en una sola pasada.
TOPE_BYTES = 1024 * 1024 * 1024
# Primeros bytes que se leen para el pre hash parcial.
PREHASH_BYTES = 8192
# Bloque de lectura para el hash completo.
BLOQUE_HASH = 1024 * 1024


def validar_raiz(raiz: Path | str) -> Path:
    # Comprueba que la raiz exista y que no sea una unidad completa.
    ruta = Path(raiz).expanduser().resolve()
    if not ruta.is_dir():
        raise ErrorDuplicados(f'la raiz no existe o no es carpeta {ruta}')
    if str(ruta) == str(ruta.anchor):
        raise ErrorDuplicados(f'la raiz no puede ser la unidad completa {ruta}')
    return ruta


def _esta_protegida(raiz: Path, ruta: Path) -> bool:
    # Una ruta queda protegida si alguna de sus partes es una carpeta prohibida.
    if ruta == raiz:
        return False
    return any(parte in CARPETAS_PROTEGIDAS for parte in ruta.relative_to(raiz).parts)


def _extension(ruta: Path) -> str:
    # Normaliza la extension para agrupar el ahorro por tipo en el resumen.
    sufijo = ruta.suffix.lower()
    return sufijo if sufijo else 'sin extension'


def _crear_hasher():
    # Importa blake3 de forma perezosa para no ralentizar dev --help.
    from blake3 import blake3

    return blake3()


def prehash(ruta: Path) -> str:
    # Calcula el hash de los primeros bytes para descartar falsos positivos.
    hasher = _crear_hasher()
    try:
        with ruta.open('rb') as archivo:
            bloque = archivo.read(PREHASH_BYTES)
    except OSError as fallo:
        raise ErrorDuplicados(f'no se puede leer {ruta} porque {fallo}') from fallo
    hasher.update(bloque)
    return hasher.hexdigest()


def hash_completo(ruta: Path) -> str:
    # Calcula el hash completo por bloques para confirmar duplicados exactos.
    hasher = _crear_hasher()
    try:
        with ruta.open('rb') as archivo:
            while True:
                bloque = archivo.read(BLOQUE_HASH)
                if not bloque:
                    break
                hasher.update(bloque)
    except OSError as fallo:
        raise ErrorDuplicados(f'no se puede leer {ruta} porque {fallo}') from fallo
    return hasher.hexdigest()


def recolectar_archivos(raiz: Path, ignorar_onedrive: bool, edad_dias: int) -> list[Path]:
    # Recorre sin seguir enlaces y devuelve los archivos dentro de la raiz.
    base = validar_raiz(raiz)
    corte = time.time() - edad_dias * 86400
    archivos: list[Path] = []
    for carpeta, subcarpetas, entradas in os.walk(base, followlinks=False):
        ruta_carpeta = Path(carpeta)
        # No se desciende a carpetas protegidas como .git o src.
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
            if datos.st_mtime >= corte:
                continue
            if ignorar_onedrive and paths.es_onedrive(ruta):
                continue
            archivos.append(ruta)
    archivos.sort()
    return archivos


def _agrupar_por_tamano(archivos: list[Path]) -> dict:
    # Descarta tamanos unicos para no calcular hashes sin necesidad.
    por_tamano: dict[int, list[Path]] = {}
    for ruta in archivos:
        try:
            tamano = ruta.stat().st_size
        except OSError:
            continue
        por_tamano.setdefault(tamano, []).append(ruta)
    return {tamano: lista for tamano, lista in por_tamano.items() if len(lista) > 1}


def _elegir_conservar(candidatos: list[Path]) -> Path:
    # Conserva la ruta mas corta y, a igualdad, el archivo mas antiguo.
    def clave(ruta: Path):
        try:
            modificado = ruta.stat().st_mtime
        except OSError:
            modificado = 0
        return (len(str(ruta)), modificado, str(ruta))

    return sorted(candidatos, key=clave)[0]


def construir_grupos(archivos: list[Path]) -> list[dict]:
    # Confirma cada grupo con hash completo y propone conservar un archivo.
    por_tamano = _agrupar_por_tamano(archivos)
    grupos: list[dict] = []
    for tamano, candidatos in sorted(por_tamano.items()):
        # Pre hash para descartar mismo tamano sin mismo contenido.
        por_prehash: dict[str, list[Path]] = {}
        for ruta in candidatos:
            por_prehash.setdefault(prehash(ruta), []).append(ruta)
        for pre, lista in por_prehash.items():
            if len(lista) < 2:
                continue
            por_hash: dict[str, list[Path]] = {}
            for ruta in lista:
                por_hash.setdefault(hash_completo(ruta), []).append(ruta)
            for digest, lista_hash in por_hash.items():
                if len(lista_hash) < 2:
                    continue
                guardar = _elegir_conservar(lista_hash)
                duplicados = [str(ruta) for ruta in sorted(lista_hash) if ruta != guardar]
                ahorro = tamano * len(duplicados)
                grupos.append(
                    {
                        'hash': digest,
                        'prehash': pre,
                        'extension': _extension(guardar),
                        'conservar': str(guardar),
                        'duplicados': duplicados,
                        'total_copias': len(lista_hash),
                        'tamano': tamano,
                        'ahorro_bytes': ahorro,
                    }
                )
    grupos.sort(key=lambda grupo: (-grupo['ahorro_bytes'], grupo['hash']))
    return grupos


def construir_plan(grupos: list[dict], tope: int = TOPE_BYTES) -> dict:
    # Pasa los grupos a acciones ordenadas por ahorro y aplica el tope.
    acciones = []
    total = 0
    omitidos = 0
    por_extension: dict[str, dict] = {}
    for grupo in grupos:
        ext = grupo['extension']
        if ext not in por_extension:
            por_extension[ext] = {'extension': ext, 'grupos': 0, 'ahorro_bytes': 0, 'copias': 0}
        por_extension[ext]['grupos'] += 1
        por_extension[ext]['copias'] += grupo['total_copias']
        por_extension[ext]['ahorro_bytes'] += grupo['ahorro_bytes']
        for ruta in grupo['duplicados']:
            if total + grupo['tamano'] > tope:
                omitidos += 1
                continue
            total += grupo['tamano']
            try:
                modificado = Path(ruta).stat().st_mtime
            except OSError:
                modificado = 0
            try:
                firma_contenido = safety.hash_contenido(Path(ruta))
            except OSError:
                firma_contenido = None
            acciones.append(
                {
                    'tipo': 'papelera',
                    'origen': ruta,
                    'conservar': grupo['conservar'],
                    'tamano': grupo['tamano'],
                    'mtime': modificado,
                    'hash': firma_contenido,
                    'extension': ext,
                }
            )
    resumen = sorted(por_extension.values(), key=lambda item: -item['ahorro_bytes'])
    return {
        'acciones': acciones,
        'total': len(acciones),
        'total_bytes': total,
        'omitidos': omitidos,
        'resumen_extension': resumen,
    }


def analizar_dedupe(
    raiz: Path,
    edad_dias: int = 30,
    ignorar_onedrive: bool = True,
    tope: int = TOPE_BYTES,
) -> dict:
    # Analisis puro de duplicados, sin persistir manifiesto ni journal.
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    archivos = recolectar_archivos(base, ignorar_onedrive, edad_dias)
    grupos = construir_grupos(archivos)
    plan = construir_plan(grupos, tope)
    return {
        'herramienta': 'dedupe',
        'accion': 'analizar',
        'estado': 'correcto',
        'codigo': 0,
        'raiz': str(base),
        'total_archivos': len(archivos),
        'total_grupos': len(grupos),
        'total': plan['total'],
        'total_bytes': plan['total_bytes'],
        'omitidos': plan['omitidos'],
        'resumen_extension': plan['resumen_extension'],
        'grupos': grupos,
        'acciones': plan['acciones'],
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }


def escanear_dedupe(
    raiz: Path,
    edad_dias: int = 30,
    ignorar_onedrive: bool = True,
    tope: int = TOPE_BYTES,
) -> dict:
    # Construye el plan, guarda su manifiesto persistente y registra el escaneo.
    analisis = analizar_dedupe(raiz, edad_dias, ignorar_onedrive, tope)
    base = Path(analisis['raiz'])
    inicio = time.perf_counter()
    id_ejec = runlog.iniciar_ejecucion('dedupe', 'escanear', espacio_trabajo=str(base))
    wid = modulo_workspace.workspace_id(base)
    ruta_plan = safety.guardar_plan(
        id_ejec, 'dedupe', analisis['acciones'], workspace_id=wid, workspace_root=str(base)
    )
    runlog.registrar_ejecucion(
        'dedupe', ['escanear'], inicio, 0, 0, 'escanear',
        espacio_trabajo=str(base), id_plan=id_ejec, id_ejecucion=id_ejec,
    )
    resultado = dict(analisis)
    resultado['accion'] = 'escanear'
    resultado['plan_persistente'] = str(ruta_plan)
    return resultado


def aplicar_dedupe(
    raiz: Path,
    edad_dias: int = 30,
    ignorar_onedrive: bool = True,
    tope: int = TOPE_BYTES,
    plan: Path | None = None,
    dry_run: bool = False,
    reanudar: bool = False,
) -> dict:
    # Aplica (o simula) un manifiesto por el ejecutor unico, sin reescanear si ya existe.
    if not dry_run:
        safety.verificar_escritura('mover duplicados')
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    ruta_plan = Path(plan).expanduser().resolve() if plan is not None else None
    if ruta_plan is not None and not ruta_plan.is_file():
        raise ErrorDuplicados(f'no existe el plan {ruta_plan}')
    acciones = None
    if ruta_plan is None and dry_run:
        archivos = recolectar_archivos(base, ignorar_onedrive, edad_dias)
        grupos = construir_grupos(archivos)
        plan_obj = construir_plan(grupos, tope)
        acciones = plan_obj['acciones']
    if ruta_plan is None and not dry_run:
        escaneo = escanear_dedupe(base, edad_dias, ignorar_onedrive, tope)
        ruta_plan = Path(escaneo['plan_persistente'])
    if dry_run:
        if acciones is not None:
            resultado = safety._simular_acciones(acciones, 'dedupe', base, autorizar=None)
        else:
            resultado = safety.simular_manifiesto(ruta_plan, 'dedupe', espacio_trabajo=str(base))
    else:
        resultado = safety.aplicar_manifiesto(ruta_plan, 'dedupe', espacio_trabajo=str(base))
    movidos = resultado['movidos']
    estado = 'simulado' if dry_run else ('correcto' if not resultado['fallidos'] else 'error')
    return {
        'herramienta': 'dedupe',
        'accion': 'aplicar',
        'estado': estado,
        'codigo': resultado['codigo'],
        'raiz': str(base),
        'total_movidos': len(movidos),
        'total_bytes': sum(int(a.get('tamano', 0)) for a in movidos),
        'movidos': movidos,
        'fallidos': resultado['fallidos'],
        'estado_plan': resultado['estado_plan'],
        'id_ejecucion': resultado['id_ejecucion'],
        'plan_persistente': str(ruta_plan) if ruta_plan is not None else '',
        'fecha': datetime.now(UTC).isoformat(),
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
        'dry_run': dry_run,
        'estado_identidad': resultado.get('estado_identidad', 'sin_identidad'),
    }
