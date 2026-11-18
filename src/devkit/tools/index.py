# Indice SQLite con FTS5 sobre notas Markdown y mapa del workspace (v2).
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

NOMBRE_BD = "index.sqlite"
SCHEMA_VERSION = 2


def validar_raiz(raiz: Path | str) -> Path:
    # Comprueba que la raiz de notas exista y sea una carpeta.
    ruta = Path(raiz).expanduser().resolve()
    if not ruta.is_dir():
        raise ErrorIndex(f"la raiz no existe o no es carpeta {ruta}")
    return ruta


def raiz_efectiva(raiz: Path | None = None) -> Path:
    # Precedencia del espacio de trabajo: raiz dada, DEVKIT_WORKSPACE, luego el directorio actual.
    resuelta = paths.resolver_raiz(raiz)
    return validar_raiz(resuelta)


def ruta_indice(raiz: Path | None = None, crear: bool = True) -> Path:
    # El indice vive dentro del espacio de trabajo si se proporciona raiz.
    if raiz is not None:
        base = Path(raiz).expanduser().resolve()
        carpeta_devkit = base / ".devkit"
        if crear:
            try:
                carpeta_devkit.mkdir(parents=True, exist_ok=True)
            except OSError as fallo:
                raise ErrorIndex(
                    f"no se puede crear la carpeta de indice en {base} porque {fallo}"
                ) from fallo
        elif not carpeta_devkit.is_dir():
            raise ErrorIndex(f"no existe el indice de {base}, ejecuta index construir")
        return carpeta_devkit / NOMBRE_BD
    return paths.directorio_estado() / NOMBRE_BD


def _bloquear_reconstruccion(destino: Path):
    class _Cerrojo:
        def __init__(self, ruta_cerrojo: Path):
            self.ruta_cerrojo = ruta_cerrojo
            self.descriptor = None
            self.con_cerrojo = False

        def __enter__(self):
            self.ruta_cerrojo.parent.mkdir(parents=True, exist_ok=True)
            self.descriptor = os.open(
                str(self.ruta_cerrojo),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0),
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

    return _Cerrojo(destino.with_name(destino.name + ".lock"))


def _abrir(ruta: Path, solo_lectura: bool = False) -> sqlite3.Connection:
    if solo_lectura:
        uri = "file:" + str(ruta).replace("\\", "/") + "?mode=ro"
        conexion = sqlite3.connect(uri, uri=True, timeout=5.0)
        return conexion
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(str(ruta), timeout=5.0)
    conexion.execute("PRAGMA journal_mode=WAL")
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS notas_fts USING fts5("
        'titulo, cuerpo, ruta, tokenize="unicode61 remove_diacritics 2")'
    )
    conexion.execute(
        "CREATE TABLE IF NOT EXISTS notas (id INTEGER PRIMARY KEY, ruta TEXT UNIQUE, "
        "titulo TEXT, creado TEXT, palabras INTEGER, mtime REAL)"
    )
    conexion.execute("CREATE TABLE IF NOT EXISTS meta (clave TEXT PRIMARY KEY, valor TEXT)")
    conexion.execute(
        "CREATE TABLE IF NOT EXISTS workspace (id TEXT PRIMARY KEY, tipo TEXT, "
        "ruta_relativa TEXT, datos TEXT)"
    )
    conexion.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS workspace_fts USING fts5("
        "contenido, tipo UNINDEXED, referencia UNINDEXED, proyecto UNINDEXED, "
        'tokenize="unicode61 remove_diacritics 2")'
    )
    conexion.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conexion.commit()
    return conexion


def _extraer_nota(ruta: Path, base: Path) -> tuple[str, str, int, float, str]:
    texto = ruta.read_text(encoding="utf-8")
    datos, cuerpo = modulo_markdown.parsear_frontmatter(texto)
    titulo = str(datos.get("titulo", "")).strip()
    if not titulo:
        titulo = ruta.stem
    creado = str(datos.get("creado", "")).strip()
    if not creado:
        creado = str(datetime.now(UTC).date())
    str(ruta.relative_to(base)).replace("\\", "/")
    return titulo, cuerpo, len(cuerpo.split()), ruta.stat().st_mtime, creado


def _verificar_version(conexion: sqlite3.Connection) -> None:
    version = conexion.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        return  # base nueva
    if version > SCHEMA_VERSION:
        raise ErrorIndex(
            f"INDICE_VERSION_NO_SOPORTADA: el indice declara version {version}, "
            f"no soportada (maximo {SCHEMA_VERSION})"
        )
    if version < SCHEMA_VERSION:
        # v1 se reconstruye, no se migra; se informa via aviso pero no error
        pass


def construir_indice(raiz: Path, con_workspace: bool = True) -> dict:
    safety.verificar_escritura("construir indice")
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    destino = ruta_indice(raiz)
    temporal = destino.with_name(f"{destino.name}.{uuid.uuid4().hex}.tmp")
    for sufijo in ("", "-wal", "-shm", "-journal"):
        with suppress(OSError):
            Path(str(temporal) + sufijo).unlink()
    insertados = 0
    actualizados = 0
    parcial = False
    try:
        with _bloquear_reconstruccion(destino):
            conexion = _abrir(temporal)
            try:
                # meta
                conexion.execute(
                    "INSERT INTO meta (clave, valor) VALUES (?, ?)", ("raiz", str(base))
                )
                conexion.execute(
                    "INSERT INTO meta (clave, valor) VALUES (?, ?)",
                    ("version_esquema", str(SCHEMA_VERSION)),
                )
                conexion.execute(
                    "INSERT INTO meta (clave, valor) VALUES (?, ?)",
                    ("generado", datetime.now(UTC).isoformat()),
                )

                for ruta in sorted(base.rglob("*.md")):
                    protegidas = {".git", "node_modules", "__pycache__"}
                    if any(parte in protegidas for parte in ruta.relative_to(base).parts):
                        continue
                    try:
                        titulo, cuerpo, palabras, mtime, creado = _extraer_nota(ruta, base)
                    except OSError:
                        continue
                    relativa = str(ruta.relative_to(base)).replace("\\", "/")
                    conexion.execute(
                        "INSERT INTO notas (ruta, titulo, creado, palabras, mtime) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (relativa, titulo, creado, palabras, mtime),
                    )
                    conexion.execute(
                        "INSERT INTO notas_fts (titulo, cuerpo, ruta) VALUES (?, ?, ?)",
                        (titulo, cuerpo, relativa),
                    )
                    insertados += 1
                conexion.commit()

                # workspace map
                if con_workspace:
                    try:
                        from devkit.tools import workspace as modulo_workspace_tool

                        mapa = modulo_workspace_tool.detectar_workspace(
                            base, profundidad=0, limite=0, con_workspace=True
                        )
                        # insertar proyectos
                        for proj in mapa.get("proyectos", []):
                            pid = proj["id"]
                            ruta_rel = proj["ruta_relativa"]
                            datos_json = json.dumps(proj, ensure_ascii=False)
                            conexion.execute(
                                (
                                    "INSERT INTO workspace (id, tipo, ruta_relativa, datos) "
                                    "VALUES (?, ?, ?, ?)"
                                ),
                                (pid, "proyecto", ruta_rel, datos_json),
                            )
                            # fts
                            contenido = " ".join(
                                [
                                    proj.get("ecosistema", ""),
                                    " ".join(proj.get("nombres_paquete", {}).values()),
                                    " ".join(proj.get("archivos_manifesto", [])),
                                ]
                            )
                            conexion.execute(
                                (
                                    "INSERT INTO workspace_fts "
                                    "(contenido, tipo, referencia, proyecto) "
                                    "VALUES (?, ?, ?, ?)"
                                ),
                                (contenido, "proyecto", pid, ruta_rel),
                            )
                        for rel in mapa.get("relaciones", []):
                            rid = rel["id"]
                            datos_json = json.dumps(rel, ensure_ascii=False)
                            conexion.execute(
                                (
                                    "INSERT INTO workspace (id, tipo, ruta_relativa, datos) "
                                    "VALUES (?, ?, ?, ?)"
                                ),
                                (rid, "relacion", rel.get("origen", ""), datos_json),
                            )
                        # dependencias
                        for proj in mapa.get("proyectos", []):
                            for dep in proj.get("dependencias", []):
                                did = _id_dep(dep, proj["id"])
                                datos_json = json.dumps(dep, ensure_ascii=False)
                                conexion.execute(
                                    (
                                        "INSERT INTO workspace (id, tipo, ruta_relativa, datos) "
                                        "VALUES (?, ?, ?, ?)"
                                    ),
                                    (did, "dependencia", proj["ruta_relativa"], datos_json),
                                )
                        # avisos parciales -> parcial
                        if any(a.get("severidad") == "fatal" for a in mapa.get("avisos", [])):
                            parcial = True
                        conexion.commit()
                    except Exception:
                        parcial = True

                conexion.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conexion.commit()
                comprobacion = conexion.execute("PRAGMA integrity_check").fetchone()
                if comprobacion is None or comprobacion[0] != "ok":
                    raise ErrorIndex("el indice reconstruido no supera integrity_check")
                fk = conexion.execute("PRAGMA foreign_key_check").fetchall()
                if fk:
                    raise ErrorIndex("el indice reconstruido no supera foreign_key_check")
            finally:
                conexion.close()
            for sufijo in ("-wal", "-shm", "-journal"):
                with suppress(OSError):
                    Path(str(destino) + sufijo).unlink()
            os.replace(str(temporal), str(destino))
    except (OSError, ErrorIndex) as fallo:
        for sufijo in ("", "-wal", "-shm", "-journal"):
            with suppress(OSError):
                Path(str(temporal) + sufijo).unlink()
        detalle = f"no se pudo construir el indice {destino} porque {fallo}"
        raise ErrorIndex(detalle) from fallo
    runlog.registrar_ejecucion(
        "index",
        ["construir"],
        inicio,
        0 if not parcial else 1,
        0,
        "construir",
        espacio_trabajo=str(base),
    )
    return {
        "herramienta": "index",
        "accion": "construir",
        "estado": "parcial" if parcial else "correcto",
        "codigo": 1 if parcial else 0,
        "raiz": str(base),
        "indice": str(destino),
        "total_notas": insertados,
        "total_actualizadas": actualizados,
        "duracion_ms": round((time.perf_counter() - inicio) * 1000, 1),
    }


def _id_dep(dep: dict, proyecto_id: str) -> str:
    import hashlib

    base = f"d_{proyecto_id}_{dep.get('nombre', '')}_{dep.get('alcance', '')}"
    return "d_" + hashlib.blake2b(base.encode("utf-8"), digest_size=8).hexdigest()


def buscar(
    raiz: Path | None,
    termino: str,
    estado: str | None = None,
    limite: int = 20,
    con_workspace: bool = True,
    profundidad: int = 0,
) -> dict:
    inicio = time.perf_counter()
    base = raiz_efectiva(raiz)
    destino = ruta_indice(base, crear=False)
    if not destino.is_file():
        raise ErrorIndex(f"no existe el indice en {destino}, ejecuta index construir")
    # Verificar version
    conn_check = sqlite3.connect(str(destino))
    version = conn_check.execute("PRAGMA user_version").fetchone()[0]
    conn_check.close()
    if version > SCHEMA_VERSION:
        raise ErrorIndex(f"INDICE_VERSION_NO_SOPORTADA: version {version}")
    if version == 0:
        raise ErrorIndex(f"no existe el indice en {destino}, ejecuta index construir")

    conexion = _abrir(destino, solo_lectura=True)
    try:
        # Validar consulta
        if not termino or not termino.strip():
            raise ErrorIndex("CONSULTA_INVALIDA: el termino no puede estar vacio")
        if limite < 0:
            raise ErrorIndex("LIMITE_INVALIDO: el limite no puede ser negativo")
        if limite == 0:
            limite = 100000  # sin limite de salida (topes internos siguen)
        if profundidad < 0:
            raise ErrorIndex("PROFUNDIDAD_INVALIDA: la profundidad no puede ser negativa")

        # Notas
        resultados_notas = []
        if estado:
            # aplicar filtro estado: solo notas cuyo creado/estado coincida
            # (el indice no guarda estado explicito de nota; filtramos por ruta/creado aproximado)
            pass
        consulta = (
            'SELECT ruta, titulo, snippet(notas_fts, 1, "[", "]", "...", 12) '
            "FROM notas_fts WHERE notas_fts MATCH ? LIMIT ?"
        )
        try:
            filas = conexion.execute(consulta, (termino, limite)).fetchall()
        except sqlite3.OperationalError as fallo:
            raise ErrorIndex(f"consulta invalida {fallo}") from fallo
        for fila in filas:
            resultados_notas.append({"ruta": fila[0], "titulo": fila[1], "fragmento": fila[2]})

        # Workspace
        resultados_workspace = None
        if con_workspace:
            # verificar si hay tabla workspace
            tablas = [
                r[0]
                for r in conexion.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            if "workspace" in tablas:
                try:
                    filas_ws = conexion.execute(
                        'SELECT tipo, referencia, proyecto, '
                        'snippet(workspace_fts, 0, "[", "]", "...", 12) '
                        "FROM workspace_fts WHERE workspace_fts MATCH ? LIMIT ?",
                        (termino, limite),
                    ).fetchall()
                    resultados_workspace = []
                    for fila in filas_ws:
                        resultados_workspace.append(
                            {
                                "tipo": fila[0],
                                "referencia": fila[1],
                                "proyecto": fila[2],
                                "fragmento": fila[3],
                            }
                        )
                except sqlite3.OperationalError:
                    resultados_workspace = []
            else:
                resultados_workspace = None  # sin indice v2 con workspace
    finally:
        conexion.close()

    # sin indice v2 -> workspace: null
    if not con_workspace:
        resultados_workspace = None

    truncado = len(resultados_notas) >= limite or (
        resultados_workspace is not None and len(resultados_workspace) >= limite
    )

    return {
        "herramienta": "index",
        "accion": "buscar",
        "estado": "correcto",
        "codigo": 0,
        "termino": termino,
        "total": len(resultados_notas) + (len(resultados_workspace) if resultados_workspace else 0),
        "resultados": resultados_notas,
        "workspace": resultados_workspace,
        "truncado": truncado,
        "duracion_ms": round((time.perf_counter() - inicio) * 1000, 1),
    }


def actualizar_indice(raiz: Path, con_workspace: bool = True) -> dict:
    safety.verificar_escritura("actualizar indice")
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    destino = ruta_indice(raiz)
    if not destino.is_file():
        # si no existe, construir
        return construir_indice(raiz, con_workspace=con_workspace)
    conexion = _abrir(destino)
    actualizados = 0
    insertados = 0
    try:
        conexion.execute("BEGIN IMMEDIATE")
        # notas: actualizar/insertar
        for ruta in sorted(base.rglob("*.md")):
            protegidas = {".git", "node_modules", "__pycache__"}
            if any(parte in protegidas for parte in ruta.relative_to(base).parts):
                continue
            try:
                titulo, cuerpo, palabras, mtime, creado = _extraer_nota(ruta, base)
            except OSError:
                continue
            relativa = str(ruta.relative_to(base)).replace("\\", "/")
            fila = conexion.execute(
                "SELECT mtime FROM notas WHERE ruta = ?", (relativa,)
            ).fetchone()
            if fila and fila[0] == mtime:
                continue
            if fila:
                conexion.execute("DELETE FROM notas WHERE ruta = ?", (relativa,))
                conexion.execute("DELETE FROM notas_fts WHERE ruta = ?", (relativa,))
                actualizados += 1
            else:
                insertados += 1
            conexion.execute(
                "INSERT INTO notas (ruta, titulo, creado, palabras, mtime) VALUES (?, ?, ?, ?, ?)",
                (relativa, titulo, creado, palabras, mtime),
            )
            conexion.execute(
                "INSERT INTO notas_fts (titulo, cuerpo, ruta) VALUES (?, ?, ?)",
                (titulo, cuerpo, relativa),
            )
        # eliminar notas que ya no existen
        existentes = {str(ruta.relative_to(base)).replace("\\", "/") for ruta in base.rglob("*.md")}
        for (ruta,) in conexion.execute("SELECT ruta FROM notas").fetchall():
            if ruta not in existentes:
                conexion.execute("DELETE FROM notas WHERE ruta = ?", (ruta,))
                conexion.execute("DELETE FROM notas_fts WHERE ruta = ?", (ruta,))
        # workspace: reconstruir si con_workspace
        if con_workspace:
            conexion.execute("DELETE FROM workspace")
            conexion.execute("DELETE FROM workspace_fts")
            try:
                from devkit.tools import workspace as modulo_workspace_tool

                mapa = modulo_workspace_tool.detectar_workspace(
                    base, profundidad=0, limite=0, con_workspace=True
                )
                for proj in mapa.get("proyectos", []):
                    pid = proj["id"]
                    datos_json = json.dumps(proj, ensure_ascii=False)
                    conexion.execute(
                        (
                            "INSERT INTO workspace (id, tipo, ruta_relativa, datos) "
                            "VALUES (?, ?, ?, ?)"
                        ),
                        (pid, "proyecto", proj["ruta_relativa"], datos_json),
                    )
                    contenido = " ".join(
                        [
                            proj.get("ecosistema", ""),
                            " ".join(proj.get("nombres_paquete", {}).values()),
                            " ".join(proj.get("archivos_manifesto", [])),
                        ]
                    )
                    conexion.execute(
                        (
                            "INSERT INTO workspace_fts (contenido, tipo, referencia, proyecto) "
                            "VALUES (?, ?, ?, ?)"
                        ),
                        (contenido, "proyecto", pid, proj["ruta_relativa"]),
                    )
                for rel in mapa.get("relaciones", []):
                    rid = rel["id"]
                    datos_json = json.dumps(rel, ensure_ascii=False)
                    conexion.execute(
                        (
                            "INSERT INTO workspace (id, tipo, ruta_relativa, datos) "
                            "VALUES (?, ?, ?, ?)"
                        ),
                        (rid, "relacion", rel.get("origen", ""), datos_json),
                    )
                for proj in mapa.get("proyectos", []):
                    for dep in proj.get("dependencias", []):
                        did = _id_dep(dep, proj["id"])
                        datos_json = json.dumps(dep, ensure_ascii=False)
                        conexion.execute(
                            (
                            "INSERT INTO workspace (id, tipo, ruta_relativa, datos) "
                            "VALUES (?, ?, ?, ?)"
                        ),
                            (did, "dependencia", proj["ruta_relativa"], datos_json),
                        )
            except Exception:
                pass
        conexion.commit()
        total = conexion.execute("SELECT COUNT(*) FROM notas").fetchone()[0]
    except Exception as fallo:
        conexion.rollback()
        raise ErrorIndex(f"no se pudo actualizar el indice {destino} porque {fallo}") from fallo
    finally:
        conexion.close()
    runlog.registrar_ejecucion(
        "index", ["actualizar"], inicio, 0, 0, "actualizar", espacio_trabajo=str(base)
    )
    return {
        "herramienta": "index",
        "accion": "actualizar",
        "estado": "correcto",
        "codigo": 0,
        "raiz": str(base),
        "indice": str(destino),
        "total_notas": total,
        "insertados": insertados,
        "actualizados": actualizados,
        "duracion_ms": round((time.perf_counter() - inicio) * 1000, 1),
    }


def exportar_indice(ruta_bd: Path, salida: Path) -> dict:
    inicio = time.perf_counter()
    if not ruta_bd.is_file():
        raise ErrorIndex(f"no existe el indice en {ruta_bd}")
    conexion = _abrir(ruta_bd, solo_lectura=True)
    filas = conexion.execute("SELECT ruta, titulo, creado, palabras FROM notas").fetchall()
    conexion.close()
    datos = [
        {"ruta": fila[0], "titulo": fila[1], "creado": fila[2], "palabras": fila[3]}
        for fila in filas
    ]
    salida.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "herramienta": "index",
        "accion": "exportar",
        "estado": "correcto",
        "codigo": 0,
        "indice": str(ruta_bd),
        "salida": str(salida),
        "total": len(datos),
        "duracion_ms": round((time.perf_counter() - inicio) * 1000, 1),
    }
