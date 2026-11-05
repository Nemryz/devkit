# Limpieza de caches y artefactos con plan previo y papelera de Windows.
from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

from devkit.core import runlog, safety
from devkit.errors import ErrorLimpieza

# Carpetas que se consideran limpiables por defecto en cualquier proyecto.
CARPETAS_LIMPIABLES = {
    '.mypy_cache',
    '.pytest_cache',
    '.ruff_cache',
    '__pycache__',
    'build',
    'dist',
    'htmlcov',
    'node_modules',
}
# Carpetas que nunca entran en el plan, aunque el usuario las pida por error.
CARPETAS_PROTEGIDAS = {'.git', '.idea', '.venv', '.vscode', 'src', 'tests'}
# Sufijos de archivo que se consideran artefactos generados.
SUFIJOS_TEMPORALES = {'.log', '.pyc', '.pyo', '.tmp'}
# Tropieza por defecto para no mover mas de esto en una sola pasada.
TOPE_BYTES = 512 * 1024 * 1024


def validar_raiz(raiz: Path | str) -> Path:
    # Comprueba que la raiz exista y que no sea una unidad completa.
    ruta = Path(raiz).expanduser().resolve()
    if not ruta.is_dir():
        raise ErrorLimpieza(f'la raiz no existe o no es carpeta {ruta}')
    if str(ruta) == str(ruta.anchor):
        raise ErrorLimpieza(f'la raiz no puede ser la unidad completa {ruta}')
    return ruta


def _esta_protegida(raiz: Path, ruta: Path) -> bool:
    # Una ruta queda protegida si alguna de sus partes es una carpeta prohibida.
    if ruta == raiz:
        return False
    return any(parte in CARPETAS_PROTEGIDAS for parte in ruta.relative_to(raiz).parts)


def calcular_tamano(ruta: Path) -> int:
    # Suma el tamano en bytes sin seguir enlaces para no atravesar volumenes.
    if ruta.is_file() and not ruta.is_symlink():
        try:
            return ruta.stat().st_size
        except OSError:
            return 0
    total = 0
    for carpeta, subcarpetas, archivos in os.walk(ruta, followlinks=False):
        subcarpetas[:] = [n for n in subcarpetas if not Path(carpeta, n).is_symlink()]
        for nombre in archivos:
            candidato = Path(carpeta, nombre)
            if candidato.is_symlink() or candidato.is_junction():
                continue
            try:
                total += candidato.stat().st_size
            except OSError:
                continue
    return total


def _es_temporal(nombre: str) -> bool:
    # Detecta archivos generados por sufijo, como registros o temporales.
    return Path(nombre).suffix.lower() in SUFIJOS_TEMPORALES


def escanear(raiz: Path, incluir_venv: bool = False, edad_dias: int = 7) -> list[dict]:
    # Recorre sin seguir enlaces y devuelve los candidatos ordenados por ruta.
    base = validar_raiz(raiz)
    permitidas = set(CARPETAS_LIMPIABLES)
    if incluir_venv:
        permitidas.add('.venv')
    corte = time.time() - edad_dias * 86400
    candidatos: list[dict] = []
    for carpeta, subcarpetas, archivos in os.walk(base, followlinks=False):
        ruta_carpeta = Path(carpeta)
        # No se desciende a carpetas protegidas como .git o src.
        conservadas = []
        for nombre in sorted(subcarpetas):
            ruta_sub = ruta_carpeta / nombre
            if ruta_sub.is_symlink() or ruta_sub.is_junction():
                continue
            if nombre in CARPETAS_PROTEGIDAS and not (incluir_venv and nombre == '.venv'):
                continue
            conservadas.append(nombre)
        subcarpetas[:] = conservadas
        partes = ruta_carpeta.relative_to(base).parts
        dentro_protegida = bool(partes) and any(p in CARPETAS_PROTEGIDAS for p in partes)
        if dentro_protegida and not (ruta_carpeta.name == '.venv' and incluir_venv):
            continue
        if ruta_carpeta.name in permitidas:
            try:
                modificado = ruta_carpeta.stat().st_mtime
            except OSError:
                modificado = 0
            if modificado < corte:
                candidatos.append(
                    {
                        'ruta': str(ruta_carpeta),
                        'tipo': 'carpeta',
                        'motivo': f'cache {ruta_carpeta.name}',
                        'tamano': calcular_tamano(ruta_carpeta),
                    }
                )
            # Al marcar la carpeta entera no se recorre su interior.
            subcarpetas[:] = []
            continue
        for nombre in sorted(archivos):
            ruta = ruta_carpeta / nombre
            if ruta.is_symlink() or ruta.is_junction() or not _es_temporal(nombre):
                continue
            if _esta_protegida(base, ruta):
                continue
            try:
                modificado = ruta.stat().st_mtime
            except OSError:
                continue
            if modificado >= corte:
                continue
            candidatos.append(
                {
                    'ruta': str(ruta),
                    'tipo': 'archivo',
                    'motivo': f'temporal {ruta.suffix.lower()}',
                    'tamano': ruta.stat().st_size,
                }
            )
    candidatos.sort(key=lambda item: item['ruta'])
    return candidatos


def construir_plan(candidatos: list[dict], tope: int = TOPE_BYTES) -> dict:
    # Ordena por tamano descendente y corta cuando se alcanza el tope.
    ordenados = sorted(candidatos, key=lambda item: item['tamano'], reverse=True)
    seleccion = []
    total = 0
    for candidato in ordenados:
        if total + candidato['tamano'] > tope:
            continue
        seleccion.append(candidato)
        total += candidato['tamano']
    acciones = [
        {'origen': a['ruta'], 'destino': '', 'tipo': 'papelera', 'tamano': a['tamano']}
        for a in seleccion
    ]
    return {
        'acciones': seleccion,
        'manifest': acciones,
        'total': len(seleccion),
        'total_bytes': total,
        'omitidos': len(ordenados) - len(seleccion),
    }


def _mover_a_papelera(ruta: Path) -> None:
    # La unica escritura destructiva pasa por send2trash tras verificar lectura.
    # En tests se hace monkeypatch sobre esta funcion, por eso se mantiene.
    import send2trash

    try:
        send2trash.send2trash(str(ruta))
    except OSError as fallo:
        raise ErrorLimpieza(f'no se pudo mover a papelera {ruta} porque {fallo}') from fallo


def escanear_trim(raiz: Path, incluir_venv: bool = False, edad_dias: int = 7) -> dict:
    # Construye el plan sin tocar el disco y lo registra en el journal.
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    candidatos = escanear(base, incluir_venv, edad_dias)
    plan = construir_plan(candidatos)
    runlog.registrar_ejecucion('trim', ['escanear'], inicio, 0, 0, 'escanear')
    # Guarda el manifiesto persistente para aplicar sin reescanear en Bloque D.
    from devkit.core import runlog as _rl

    id_ejec = _rl.iniciar_ejecucion('trim', 'escanear')
    ruta_plan = safety.guardar_plan(id_ejec, 'trim', plan['manifest'])
    return {
        'herramienta': 'trim',
        'accion': 'escanear',
        'estado': 'correcto',
        'codigo': 0,
        'raiz': str(base),
        'total': plan['total'],
        'total_bytes': plan['total_bytes'],
        'omitidos': plan['omitidos'],
        'acciones': plan['acciones'],
        'plan_persistente': str(ruta_plan),
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }


def aplicar_trim(raiz: Path, incluir_venv: bool = False, edad_dias: int = 7) -> dict:
    # Ejecuta el plan moviendo cada candidato a la papelera de Windows.
    # En Bloque D se valida contra el manifiesto persistente sin reescanear.
    safety.verificar_escritura('limpiar caches')
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    candidatos = escanear(base, incluir_venv, edad_dias)
    plan = construir_plan(candidatos)
    from devkit.core import runlog as _rl

    id_ejec = _rl.iniciar_ejecucion('trim', 'aplicar')
    ruta_plan = safety.guardar_plan(id_ejec, 'trim', plan['manifest'])
    validacion = safety._validar_arbol(plan)
    if validacion:
        estado = 'error'
        codigo = 2
        runlog.registrar_ejecucion('trim', ['aplicar'], inicio, codigo, 0, estado)
        return {
            'herramienta': 'trim',
            'accion': 'aplicar',
            'estado': estado,
            'codigo': codigo,
            'raiz': str(base),
            'total_movidos': 0,
            'total_bytes': 0,
            'movidos': [],
            'fallidos': validacion,
            'plan_persistente': str(ruta_plan),
            'fecha': datetime.now(UTC).isoformat(),
            'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
        }
    movidos = []
    fallidos = []
    for accion in plan['acciones']:
        ruta = Path(accion['ruta'])
        try:
            _mover_a_papelera(ruta)
            movidos.append(accion)
        except ErrorLimpieza as fallo:
            fallidos.append({'ruta': str(ruta), 'detalle': str(fallo)})
    estado = 'correcto' if not fallidos else 'error'
    codigo = 0 if estado == 'correcto' else 2
    runlog.registrar_ejecucion('trim', ['aplicar'], inicio, codigo, 0, estado)
    return {
        'herramienta': 'trim',
        'accion': 'aplicar',
        'estado': estado,
        'codigo': codigo,
        'raiz': str(base),
        'total_movidos': len(movidos),
        'total_bytes': sum(item['tamano'] for item in movidos),
        'movidos': movidos,
        'fallidos': fallidos,
        'fecha': datetime.now(UTC).isoformat(),
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }
