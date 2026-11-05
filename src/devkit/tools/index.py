# Indice SQLite con FTS5 sobre notas Markdown.
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from devkit.core import markdown as modulo_markdown
from devkit.core import paths, runlog, safety
from devkit.errors import ErrorIndex

NOMBRE_BD = 'index.sqlite'


def validar_raiz(raiz: Path | str) -> Path:
    # Comprueba que la raiz de notas exista y sea una carpeta.
    ruta = Path(raiz).expanduser().resolve()
    if not ruta.is_dir():
        raise ErrorIndex(f'la raiz no existe o no es carpeta {ruta}')
    return ruta


def raiz_efectiva(raiz: Path | None = None) -> Path:
    # Precedencia del espacio de trabajo: raiz dada, DEVKIT_WORKSPACE, luego el directorio actual.
    if raiz is not None:
        return validar_raiz(raiz)
    activo = paths.workspace_activo()
    if activo is not None:
        return validar_raiz(activo)
    return validar_raiz(Path.cwd())


def ruta_indice(raiz: Path | None = None, crear: bool = True) -> Path:
    # El indice vive dentro del espacio de trabajo si se proporciona raiz.
    if raiz is not None:
        base = Path(raiz).expanduser().resolve()
        carpeta_devkit = base / '.devkit'
        if crear:
            try:
                carpeta_devkit.mkdir(parents=True, exist_ok=True)
            except OSError as fallo:
                raise ErrorIndex(
                    f'no se puede crear la carpeta de indice en {base} porque {fallo}'
                ) from fallo
        elif not carpeta_devkit.is_dir():
            raise ErrorIndex(f'no existe el indice de {base}, ejecuta index construir')
        return carpeta_devkit / NOMBRE_BD
    return paths.directorio_estado() / NOMBRE_BD


def _bloquear_reconstruccion(destino: Path):
    # Cerrojo entre procesos para que dos reconstrucciones no compitan por el temporal.

    class _Cerrojo:
        def __init__(self, ruta_cerrojo: Path):
            self.ruta_cerrojo = ruta_cerrojo
            self.descriptor = None
            self.con_cerrojo = False

        def __enter__(self):
            self.ruta_cerrojo.parent.mkdir(parents=True, exist_ok=True)
            self.descriptor = os.open(
                str(self.ruta_cerrojo),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_BINARY', 0),
            )
            try:
                import msvcrt

                os.lseek(self.descriptor, 0, os.SEEK_SET)
                msvcrt.locking(self.descriptor, msvcrt.LK_LOCK, 1)
                self.con_cerrojo = True
            except (ImportError, OSError):
                self.con_cerrojo = False
            return self

        def __exit__(self, *args):
            if self.descriptor is not None:
                if self.con_cerrojo:
                    try:
                        import msvcrt

                        os.lseek(self.descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(self.descriptor, msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                os.close(self.descriptor)
            return False

    return _Cerrojo(destino.with_name(destino.name + '.lock'))


def _abrir(ruta: Path) -> sqlite3.Connection:
    # Abre la base con FTS5 habilitado y crea las tablas si faltan.
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # El timeout serializa procesos simultaneos en lugar de fallar con base bloqueada.
    conexion = sqlite3.connect(str(ruta), timeout=5.0)
    # WAL permite lecturas concurrentes durante la escritura de otro proceso.
    conexion.execute('PRAGMA journal_mode=WAL')
    conexion.execute(
        'CREATE VIRTUAL TABLE IF NOT EXISTS notas_fts USING fts5('
        'titulo, cuerpo, ruta, tokenize="unicode61")'
    )
    conexion.execute(
        'CREATE TABLE IF NOT EXISTS notas (id INTEGER PRIMARY KEY, ruta TEXT UNIQUE, '
        'titulo TEXT, creado TEXT, palabras INTEGER, mtime REAL)'
    )
    conexion.commit()
    return conexion


def _extraer_nota(ruta: Path) -> tuple[str, str, int, float]:
    # Lee la nota y devuelve titulo, cuerpo, numero de palabras y mtime.
    texto = ruta.read_text(encoding='utf-8')
    datos, cuerpo = modulo_markdown.parsear_frontmatter(texto)
    titulo = str(datos.get('titulo', '')).strip()
    if not titulo:
        titulo = ruta.stem
    return titulo, cuerpo, len(cuerpo.split()), ruta.stat().st_mtime


def construir_indice(raiz: Path) -> dict:
    # Reconstruye el indice completo a partir de las notas existentes.
    # La construccion se hace en un archivo temporal que se valida antes de
    # sustituir el indice anterior, para no perderlo si algo falla a mitad.
    safety.verificar_escritura('construir indice')
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    destino = ruta_indice(raiz)
    temporal = destino.with_name(f'{destino.name}.{uuid.uuid4().hex}.tmp')
    # Limpia restos de una construccion anterior interrumpida.
    for sufijo in ('', '-wal', '-shm', '-journal'):
        with suppress(OSError):
            Path(str(temporal) + sufijo).unlink()
    insertados = 0
    actualizados = 0
    try:
        with _bloquear_reconstruccion(destino):
            conexion = _abrir(temporal)
            try:
                for ruta in sorted(base.rglob('*.md')):
                    protegidas = {'.git', 'node_modules', '__pycache__'}
                    if any(parte in protegidas for parte in ruta.relative_to(base).parts):
                        continue
                    try:
                        titulo, cuerpo, palabras, mtime = _extraer_nota(ruta)
                    except OSError:
                        continue
                    conexion.execute(
                        'INSERT INTO notas (ruta, titulo, creado, palabras, mtime) '
                        'VALUES (?, ?, ?, ?, ?)',
                        (str(ruta), titulo, str(datetime.now(UTC).date()), palabras, mtime),
                    )
                    conexion.execute(
                        'INSERT INTO notas_fts (titulo, cuerpo, ruta) VALUES (?, ?, ?)',
                        (titulo, cuerpo, str(ruta)),
                    )
                    insertados += 1
                conexion.commit()
                # Fuerza el checkpoint y abandona el modo WAL para no dejar sidecars.
                conexion.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                conexion.execute('PRAGMA journal_mode=DELETE')
                conexion.commit()
                comprobacion = conexion.execute('PRAGMA integrity_check').fetchone()
                if comprobacion is None or comprobacion[0] != 'ok':
                    raise ErrorIndex('el indice reconstruido no supera integrity_check')
            finally:
                conexion.close()
            # Sustituye el indice anterior de forma atomica; limpia sidecars viejos.
            for sufijo in ('-wal', '-shm', '-journal'):
                with suppress(OSError):
                    Path(str(destino) + sufijo).unlink()
            os.replace(str(temporal), str(destino))
    except (OSError, ErrorIndex) as fallo:
        for sufijo in ('', '-wal', '-shm', '-journal'):
            with suppress(OSError):
                Path(str(temporal) + sufijo).unlink()
        detalle = f'no se pudo construir el indice {destino} porque {fallo}'
        raise ErrorIndex(detalle) from fallo
    runlog.registrar_ejecucion(
        'index', ['construir'], inicio, 0, 0, 'construir', espacio_trabajo=str(base)
    )
    return {
        'herramienta': 'index',
        'accion': 'construir',
        'estado': 'correcto',
        'codigo': 0,
        'raiz': str(base),
        'indice': str(destino),
        'total_notas': insertados,
        'total_actualizadas': actualizados,
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }


def buscar(raiz: Path | None, termino: str, estado: str | None = None, limite: int = 20) -> dict:
    # Consulta FTS5 y devuelve fragmentos con el termino resaltado.
    inicio = time.perf_counter()
    # Sin raiz el indice se resuelve en el workspace activo o en el directorio actual.
    destino = ruta_indice(raiz_efectiva(raiz), crear=False)
    if not destino.is_file():
        raise ErrorIndex(f'no existe el indice en {destino}, ejecuta index construir')
    conexion = sqlite3.connect(str(destino))
    consulta = (
        'SELECT ruta, titulo, snippet(notas_fts, 1, "[", "]", "...", 12) '
        'FROM notas_fts WHERE notas_fts MATCH ? LIMIT ?'
    )
    try:
        filas = conexion.execute(consulta, (termino, limite)).fetchall()
    except sqlite3.OperationalError as fallo:
        raise ErrorIndex(f'consulta invalida {fallo}') from fallo
    finally:
        conexion.close()
    resultados = [
        {'ruta': fila[0], 'titulo': fila[1], 'fragmento': fila[2]} for fila in filas
    ]
    return {
        'herramienta': 'index',
        'accion': 'buscar',
        'estado': 'correcto',
        'codigo': 0,
        'termino': termino,
        'total': len(resultados),
        'resultados': resultados,
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }


def actualizar_indice(raiz: Path) -> dict:
    # Reconstruye solo las notas cuyo mtime cambio o que son nuevas.
    safety.verificar_escritura('actualizar indice')
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    destino = ruta_indice(raiz)
    conexion = _abrir(destino)
    actualizados = 0
    insertados = 0
    # Transaccion inmediata para que el SELECT y el INSERT no compitan entre procesos.
    conexion.execute('BEGIN IMMEDIATE')
    for ruta in sorted(base.rglob('*.md')):
        protegidas = {'.git', 'node_modules', '__pycache__'}
        if any(parte in protegidas for parte in ruta.relative_to(base).parts):
            continue
        try:
            titulo, cuerpo, palabras, mtime = _extraer_nota(ruta)
        except OSError:
            continue
        fila = conexion.execute(
            'SELECT mtime FROM notas WHERE ruta = ?', (str(ruta),)
        ).fetchone()
        if fila and fila[0] == mtime:
            continue
        if fila:
            conexion.execute('DELETE FROM notas WHERE ruta = ?', (str(ruta),))
            conexion.execute('DELETE FROM notas_fts WHERE ruta = ?', (str(ruta),))
            actualizados += 1
        else:
            insertados += 1
        conexion.execute(
            'INSERT INTO notas (ruta, titulo, creado, palabras, mtime) VALUES (?, ?, ?, ?, ?)',
            (str(ruta), titulo, str(datetime.now(UTC).date()), palabras, mtime),
        )
        conexion.execute(
            'INSERT INTO notas_fts (titulo, cuerpo, ruta) VALUES (?, ?, ?)',
            (titulo, cuerpo, str(ruta)),
        )
    # Elimina las notas que ya no existen.
    existentes = {str(ruta) for ruta in base.rglob('*.md')}
    for (ruta,) in conexion.execute('SELECT ruta FROM notas').fetchall():
        if ruta not in existentes:
            conexion.execute('DELETE FROM notas WHERE ruta = ?', (ruta,))
            conexion.execute('DELETE FROM notas_fts WHERE ruta = ?', (ruta,))
    conexion.commit()
    total = conexion.execute('SELECT COUNT(*) FROM notas').fetchone()[0]
    conexion.close()
    runlog.registrar_ejecucion(
        'index', ['actualizar'], inicio, 0, 0, 'actualizar', espacio_trabajo=str(base)
    )
    return {
        'herramienta': 'index',
        'accion': 'actualizar',
        'estado': 'correcto',
        'codigo': 0,
        'raiz': str(base),
        'indice': str(destino),
        'total_notas': total,
        'insertados': insertados,
        'actualizados': actualizados,
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }


def exportar_indice(ruta_bd: Path, salida: Path) -> dict:
    # Exporta el indice a JSON para revisarlo fuera de SQLite.
    inicio = time.perf_counter()
    if not ruta_bd.is_file():
        raise ErrorIndex(f'no existe el indice en {ruta_bd}')
    conexion = sqlite3.connect(str(ruta_bd))
    filas = conexion.execute('SELECT ruta, titulo, creado, palabras FROM notas').fetchall()
    conexion.close()
    datos = [
        {'ruta': fila[0], 'titulo': fila[1], 'creado': fila[2], 'palabras': fila[3]}
        for fila in filas
    ]
    salida.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    return {
        'herramienta': 'index',
        'accion': 'exportar',
        'estado': 'correcto',
        'codigo': 0,
        'indice': str(ruta_bd),
        'salida': str(salida),
        'total': len(datos),
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }
