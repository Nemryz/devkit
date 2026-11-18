# Orquestacion del mapa del workspace: deteccion, relaciones y serializacion.
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

from devkit.core import paths
from devkit.errors import ErrorWorkspace

# Topes por defecto (variante holgada, confirmada 2026-11-16).
TOPES_DEFAULT = {
    "manifiesto_bytes": 2 * 1024 * 1024,
    "lockfile_bytes": 16 * 1024 * 1024,
    "proyectos": 1000,
    "dependencias": 4000,
    "relaciones": 10000,
    "avisos": 400,
    "profundidad": 12,
}

# Directorios que no se recorren.
OMITIDOS = {
    ".devkit",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "target",
    "dist",
    "build",
}

# Archivos marcadores de ecosistemas para detectar si un directorio es un proyecto.
MARCADORES_PROYECTO = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "Gemfile",
    "pubspec.yaml",
    "mix.exs",
    "Package.swift",
    "CMakeLists.txt",
    "meson.build",
    "Makefile",
}





@dataclass
class Dependencia:
    nombre: str
    ecosistema: str
    alcance: str
    confianza: str
    version_requerida: str = ""
    version_resuelta: str | None = None


@dataclass
class Relacion:
    id: str
    tipo: str
    origen: str
    destino: str


@dataclass
class Aviso:
    codigo: str
    severidad: str
    ruta_relativa: str
    detalle: str


@dataclass
class Proyecto:
    id: str
    ruta_relativa: str
    ecosistema: str
    nombres_paquete: dict[str, str] = field(default_factory=dict)
    archivos_manifesto: list[str] = field(default_factory=list)
    dependencias: list[Dependencia] = field(default_factory=list)
    onedrive: bool = False
    miembros_workspace: list[str] = field(default_factory=list)


@dataclass
class MapaWorkspace:
    raiz: str
    onedrive: bool
    proyectos: list[Proyecto] = field(default_factory=list)
    relaciones: list[Relacion] = field(default_factory=list)
    avisos: list[Aviso] = field(default_factory=list)
    truncado: bool = False
    resumen: dict = field(default_factory=dict)


def _id_estable(prefijo: str, identidad: str) -> str:
    return prefijo + "_" + hashlib.blake2b(identidad.encode("utf-8"), digest_size=8).hexdigest()


def _es_onedrive(ruta: Path) -> bool:
    return paths.es_onedrive(ruta)


def _recorrer(raiz: Path, profundidad: int) -> list[Path]:
    # Recorre el arbol sin seguir enlaces/junctions, respetando profundidad.
    resultado: list[Path] = []
    base = raiz.resolve()
    # BFS por niveles
    nivel_actual = [base]
    visitados = set()
    for _nivel in range(profundidad):
        siguiente: list[Path] = []
        for carpeta in nivel_actual:
            if carpeta in visitados:
                continue
            visitados.add(carpeta)
            resultado.append(carpeta)
            try:
                for entrada in sorted(carpeta.iterdir(), key=lambda p: p.name):
                    if not entrada.is_dir():
                        continue
                    if entrada.name in OMITIDOS:
                        continue
                    if entrada.is_symlink() or entrada.is_junction():
                        continue
                    siguiente.append(entrada)
            except (OSError, PermissionError):
                continue
        nivel_actual = siguiente
        if not nivel_actual:
            break
    # Incluir raiz si no se incluyo
    if base not in resultado:
        resultado.insert(0, base)
    return resultado


def detectar_workspace(
    raiz: Path | str | None = None,
    profundidad: int = 0,
    limite: int = 0,
    con_workspace: bool = True,
) -> dict:
    if profundidad <= 0:
        profundidad = TOPES_DEFAULT["profundidad"]
    if profundidad > 100:
        profundidad = 100

    raiz_resuelta = paths.resolver_raiz(raiz)
    if not raiz_resuelta.is_dir():
        raise ErrorWorkspace("RAIZ_NO_ES_CARPETA")

    onedrive = _es_onedrive(raiz_resuelta)
    mapa = MapaWorkspace(raiz=str(raiz_resuelta), onedrive=onedrive)

    # Importar detectores (registro)
    import devkit.tools.detectores.deferido  # noqa: F401
    import devkit.tools.detectores.go  # noqa: F401
    import devkit.tools.detectores.node  # noqa: F401
    import devkit.tools.detectores.p2  # noqa: F401
    import devkit.tools.detectores.python  # noqa: F401
    import devkit.tools.detectores.rust  # noqa: F401
    from devkit.tools.detectores import REGISTRO

    topes = dict(TOPES_DEFAULT)

    carpetas = _recorrer(raiz_resuelta, profundidad)

    # Detectar proyectos por carpeta
    proyectos_por_carpeta: dict[str, dict] = {}
    avisos_globales: list[Aviso] = []

    for carpeta in carpetas:
        if not carpeta.is_dir():
            continue
        # Comprobar si es un directorio con marcador de proyecto
        tiene_marcador = (
            any((carpeta / m).exists() for m in MARCADORES_PROYECTO)
            or (carpeta / ".obsidian").is_dir()
        )
        if (
            not tiene_marcador
            and carpeta != raiz_resuelta
            and not (carpeta / "mkdocs.yml").is_file()
            and not (carpeta / "mkdocs.yaml").is_file()
            and not list(carpeta.glob("docusaurus.config.*"))
        ):
            continue
        # Ejecutar detectores
        proyecto_combinado = None
        avisos_carpeta = []
        for _nombre, detector in REGISTRO:
            try:
                proj, avs = detector(raiz_resuelta, carpeta, topes)
            except Exception as fallo:
                avs = [
                    {
                        "codigo": "MANIFIESTO_INVALIDO",
                        "severidad": "fatal",
                        "ruta_relativa": str(carpeta),
                        "detalle": str(fallo),
                    }
                ]
                proj = None
            for av in avs or []:
                avisos_carpeta.append(
                    Aviso(
                        codigo=av["codigo"],
                        severidad=av["severidad"],
                        ruta_relativa=av.get("ruta_relativa", ""),
                        detalle=av.get("detalle", ""),
                    )
                )
            if proj is not None:
                if proyecto_combinado is None:
                    proyecto_combinado = proj
                else:
                    # Poliglota unificado: fusionar
                    proyecto_combinado["nombres_paquete"].update(proj.get("nombres_paquete", {}))
                    proyecto_combinado["archivos_manifesto"].extend(
                        proj.get("archivos_manifesto", [])
                    )
                    proyecto_combinado["dependencias"].extend(proj.get("dependencias", []))
                    if proj.get("miembros_workspace"):
                        proyecto_combinado.setdefault("miembros_workspace", []).extend(
                            proj["miembros_workspace"]
                        )

        if proyecto_combinado is None and not avisos_carpeta:
            continue
        if proyecto_combinado is not None:
            rel = (
                str(carpeta.relative_to(raiz_resuelta)).replace("\\", "/")
                if carpeta != raiz_resuelta
                else ""
            )
            if rel == ".":
                rel = ""
            # onedrive
            od = _es_onedrive(carpeta)
            # topes de proyectos
            if len(mapa.proyectos) >= topes["proyectos"]:
                avisos_carpeta.append(
                    Aviso(
                        codigo="LIMITE_ALCANZADO",
                        severidad="parcial",
                        ruta_relativa=rel,
                        detalle="tope de proyectos alcanzado",
                    )
                )
                mapa.truncado = True
                # no añadir mas proyectos
                mapa.avisos.extend(avisos_carpeta)
                continue
            pid = _id_estable("p", rel if rel else str(raiz_resuelta))
            # dependencias como objetos
            deps_objs = []
            for d in proyecto_combinado.get("dependencias", []):
                if (
                    len([x for p in mapa.proyectos for x in p.dependencias]) + len(deps_objs)
                    >= topes["dependencias"]
                ):
                    avisos_carpeta.append(
                        Aviso(
                            codigo="LIMITE_ALCANZADO",
                            severidad="parcial",
                            ruta_relativa=rel,
                            detalle="tope de dependencias alcanzado",
                        )
                    )
                    mapa.truncado = True
                    break
                deps_objs.append(
                    Dependencia(
                        nombre=d.get("nombre", ""),
                        ecosistema=d.get("ecosistema", ""),
                        alcance=d.get("alcance", "ejecucion"),
                        confianza=d.get("confianza", "declarada"),
                        version_requerida=d.get("version_requerida", ""),
                        version_resuelta=d.get("version_resuelta"),
                    )
                )
            proyecto = Proyecto(
                id=pid,
                ruta_relativa=rel,
                ecosistema=proyecto_combinado.get("ecosistema", "desconocido"),
                nombres_paquete=proyecto_combinado.get("nombres_paquete", {}),
                archivos_manifesto=proyecto_combinado.get("archivos_manifesto", []),
                dependencias=deps_objs,
                onedrive=od,
                miembros_workspace=proyecto_combinado.get("miembros_workspace", []),
            )
            # Override ecosistema if poliglota (multiple manifests) -> keep primary but store all?
            # For poliglota, we keep the first ecosystem as primary; nombres_paquete has all.
            if (
                len(proyecto_combinado.get("archivos_manifesto", [])) > 1
                and len(proyecto_combinado.get("nombres_paquete", {})) > 1
            ):
                proyecto.ecosistema = "poliglota"
            proyectos_por_carpeta[rel] = {"proyecto": proyecto, "raw": proyecto_combinado}
            mapa.proyectos.append(proyecto)
        mapa.avisos.extend(avisos_carpeta)

    # Ahora detectar relaciones
    # miembro_de: segun miembros_workspace de cada proyecto
    # anidado_en: proyecto dentro de directorio de otro proyecto
    # depende_de_proyecto: nombre de dependencia coincide con nombres_paquete de otro proyecto

    # Index de nombres_paquete -> proyecto
    nombre_a_proyectos: dict[str, list[Proyecto]] = {}
    for p in mapa.proyectos:
        for _eco, nom in (p.nombres_paquete or {}).items():
            nombre_a_proyectos.setdefault(str(nom), []).append(p)

    # miembro_de
    for p in mapa.proyectos:
        raw = None
        for _rel, info in proyectos_por_carpeta.items():
            if info["proyecto"].id == p.id:
                raw = info["raw"]
                break
        members = (raw or {}).get("miembros_workspace", []) if raw else []
        # resolver miembros (globs simples)
        for member_glob in members:
            # buscar carpetas que coincidan
            for candidato in mapa.proyectos:
                if candidato.id == p.id:
                    continue
                # miembro si su ruta esta bajo un glob
                if _coincide_member(candidato.ruta_relativa, member_glob, p.ruta_relativa):
                    _agregar_relacion(mapa, "miembro_de", candidato.id, p.id, topes)

    # anidado_en
    for p in mapa.proyectos:
        for q in mapa.proyectos:
            if p.id == q.id:
                continue
            if (
                p.ruta_relativa
                and q.ruta_relativa
                and p.ruta_relativa.startswith(q.ruta_relativa + "/")
            ):
                # p esta anidado en q
                _agregar_relacion(mapa, "anidado_en", p.id, q.id, topes)

    # depende_de_proyecto
    for p in mapa.proyectos:
        for dep in p.dependencias:
            candidatos = nombre_a_proyectos.get(
                dep.nombre.split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip(), []
            )
            # tambien probar nombre sin version
            if not candidatos:
                # buscar por nombre base
                for nom, projs in nombre_a_proyectos.items():
                    if nom.lower() == dep.nombre.split("[")[0].strip().lower():
                        candidatos = projs
                        break
            if not candidatos:
                continue
            if len(candidatos) > 1:
                avisos_globales.append(
                    Aviso(
                        codigo="DEPENDENCIA_AMBIGUA",
                        severidad="parcial",
                        ruta_relativa=p.ruta_relativa,
                        detalle=f"{dep.nombre} coincide con {len(candidatos)} proyectos",
                    )
                )
            for cand in candidatos:
                if cand.id == p.id:
                    continue
                # NOMBRE_PAQUETE_DUPLICADO si el nombre aparece en mas de un proyecto
                if len(candidatos) > 1:
                    avisos_globales.append(
                        Aviso(
                            codigo="NOMBRE_PAQUETE_DUPLICADO",
                            severidad="informativo",
                            ruta_relativa=p.ruta_relativa,
                            detalle=f"nombre de paquete duplicado: {dep.nombre}",
                        )
                    )
                _agregar_relacion(mapa, "depende_de_proyecto", p.id, cand.id, topes)

    # avisos globales (MIEMBRO_NO_ENCONTRADO se detecta en miembro_de implicitamente)
    mapa.avisos.extend(avisos_globales)

    # Ciclos en depende_de_proyecto
    _detectar_ciclos(mapa)

    # Truncado de avisos
    if len(mapa.avisos) > topes["avisos"]:
        mapa.avisos = mapa.avisos[: topes["avisos"]]
        mapa.truncado = True

    # Resumen
    mapa.resumen = {
        "proyectos": len(mapa.proyectos),
        "relaciones": len(mapa.relaciones),
        "avisos": len(mapa.avisos),
    }

    return _serializar(mapa)


def _coincide_member(ruta_relativa: str, patron: str, base_rel: str) -> bool:
    # Coincidencia simple de glob para miembros de workspace.
    import fnmatch

    # Normalizar: el patron es relativo a la raiz del workspace
    candidato = ruta_relativa if ruta_relativa else ""
    # Si patron contiene *, usar fnmatch sobre la ruta relativa
    if "*" in patron or "?" in patron:
        return fnmatch.fnmatch(candidato, patron) or fnmatch.fnmatch(candidato, patron.lstrip("./"))
    # Patron exacto de directorio
    patron_limpio = patron.strip().rstrip("/")
    if patron_limpio.startswith("./"):
        patron_limpio = patron_limpio[2:]
    return candidato == patron_limpio or candidato.startswith(patron_limpio + "/")


def _agregar_relacion(
    mapa: MapaWorkspace, tipo: str, origen: str, destino: str, topes: dict
) -> None:
    # Deduplicacion por (tipo, origen, destino).
    clave = (tipo, origen, destino)
    for r in mapa.relaciones:
        if (r.tipo, r.origen, r.destino) == clave:
            return
    if len(mapa.relaciones) >= topes["relaciones"]:
        mapa.truncado = True
        return
    rid = _id_estable("r", f"{tipo}:{origen}:{destino}")
    mapa.relaciones.append(Relacion(id=rid, tipo=tipo, origen=origen, destino=destino))


def _detectar_ciclos(mapa: MapaWorkspace) -> None:
    # DFS sobre depende_de_proyecto para detectar ciclos.
    adj: dict[str, list[str]] = {p.id: [] for p in mapa.proyectos}
    for r in mapa.relaciones:
        if r.tipo == "depende_de_proyecto":
            adj.setdefault(r.origen, []).append(r.destino)
    visitado = set()
    en_pila = set()
    ciclos_reportados = set()

    def dfs(nodo, pila):
        visitado.add(nodo)
        en_pila.add(nodo)
        for vecino in adj.get(nodo, []):
            if vecino not in visitado:
                dfs(vecino, pila + [vecino])
            elif vecino in en_pila:
                # ciclo detectado
                ciclo = tuple(sorted([nodo, vecino]))
                if ciclo not in ciclos_reportados:
                    ciclos_reportados.add(ciclo)
                    mapa.avisos.append(
                        Aviso(
                            codigo="CICLO_DE_PROYECTOS",
                            severidad="informativo",
                            ruta_relativa="",
                            detalle=f"ciclo entre {nodo} y {vecino}",
                        )
                    )
        en_pila.discard(nodo)

    for nodo in list(adj.keys()):
        if nodo not in visitado:
            dfs(nodo, [nodo])


def _serializar(mapa: MapaWorkspace) -> dict:
    proyectos = []
    for p in mapa.proyectos:
        proyectos.append(
            {
                "id": p.id,
                "ruta_relativa": p.ruta_relativa,
                "ecosistema": p.ecosistema,
                "nombres_paquete": p.nombres_paquete,
                "archivos_manifesto": p.archivos_manifesto,
                "dependencias": [asdict(d) for d in p.dependencias],
                "onedrive": p.onedrive,
                "miembros_workspace": p.miembros_workspace,
            }
        )
    relaciones = [asdict(r) for r in mapa.relaciones]
    avisos = [asdict(a) for a in mapa.avisos]
    return {
        "raiz": mapa.raiz,
        "onedrive": mapa.onedrive,
        "proyectos": proyectos,
        "relaciones": relaciones,
        "avisos": avisos,
        "truncado": mapa.truncado,
        "resumen": mapa.resumen,
    }
