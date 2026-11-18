# Detector de proyectos Python.
from __future__ import annotations

import tomllib
from pathlib import Path

from devkit.tools.detectores import registrar

LIMITE_MANIFIESTO = 2 * 1024 * 1024  # 2 MiB
LIMITE_LOCKFILE = 16 * 1024 * 1024  # 16 MiB


def _aviso(codigo: str, severidad: str, ruta: str, detalle: str) -> dict:
    return {"codigo": codigo, "severidad": severidad, "ruta_relativa": ruta, "detalle": detalle}


def _leer_texto(ruta: Path, limite: int) -> tuple[str | None, dict | None]:
    try:
        if ruta.stat().st_size > limite:
            return None, _aviso(
                "MANIFIESTO_DEMASIADO_GRANDE", "fatal", str(ruta), f"{ruta.stat().st_size} bytes"
            )
        return ruta.read_text(encoding="utf-8"), None
    except OSError as fallo:
        return None, _aviso("MANIFIESTO_NO_LEGIBLE", "fatal", str(ruta), str(fallo))


def detectar(raiz: Path, carpeta: Path, topes: dict) -> tuple[dict | None, list[dict]]:
    avisos: list[dict] = []
    rel = str(carpeta.relative_to(raiz)).replace("\\", "/") if carpeta != raiz else "."
    if rel == ".":
        rel = ""
    manifestos: list[str] = []
    nombres_paquete: dict[str, str] = {}
    dependencias: list[dict] = []

    # pyproject.toml (primario)
    pyproject = carpeta / "pyproject.toml"
    if pyproject.is_file():
        manifestos.append("pyproject.toml")
        texto, aviso = _leer_texto(pyproject, LIMITE_MANIFIESTO)
        if aviso:
            avisos.append(aviso)
        else:
            try:
                datos = tomllib.loads(texto)
                proyecto = datos.get("project", {})
                nombre = proyecto.get("name")
                if nombre:
                    nombres_paquete["python"] = str(nombre)
                # dependencias principales
                for dep in proyecto.get("dependencies", []) or []:
                    dependencias.append(
                        {
                            "nombre": str(dep),
                            "ecosistema": "python",
                            "alcance": "ejecucion",
                            "confianza": "declarada",
                            "version_requerida": str(dep),
                            "version_resuelta": None,
                        }
                    )
                # extras
                for extra, deps in (proyecto.get("optional-dependencies") or {}).items():
                    alcance = "prueba" if extra in ("test", "dev", "testing") else "opcional"
                    for dep in deps or []:
                        dependencias.append(
                            {
                                "nombre": str(dep),
                                "ecosistema": "python",
                                "alcance": alcance,
                                "confianza": "declarada",
                                "version_requerida": str(dep),
                                "version_resuelta": None,
                            }
                        )
                # build-system requires
                build_reqs = (datos.get("build-system") or {}).get("requires", [])
                for dep in build_reqs or []:
                    dependencias.append(
                        {
                            "nombre": str(dep),
                            "ecosistema": "python",
                            "alcance": "construccion",
                            "confianza": "declarada",
                            "version_requerida": str(dep),
                            "version_resuelta": None,
                        }
                    )
            except (tomllib.TOMLDecodeError, ValueError) as fallo:
                avisos.append(_aviso("MANIFIESTO_INVALIDO", "fatal", "pyproject.toml", str(fallo)))

    # setup.py (solo lectura, nunca se ejecuta)
    setup_py = carpeta / "setup.py"
    if setup_py.is_file():
        manifestos.append("setup.py")
        texto, aviso = _leer_texto(setup_py, LIMITE_MANIFIESTO)
        if aviso:
            avisos.append(aviso)
        else:
            # extraccion conservadora por patrones
            import re

            for m in re.finditer(r"name\s*=\s*['\"]([^'\"]+)['\"]", texto):
                if "python" not in nombres_paquete:
                    nombres_paquete["python"] = m.group(1)
            for m in re.finditer(r"install_requires\s*=\s*\[([^\]]*)\]", texto, re.DOTALL):
                for dep in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)):
                    dependencias.append(
                        {
                            "nombre": dep,
                            "ecosistema": "python",
                            "alcance": "ejecucion",
                            "confianza": "declarada",
                            "version_requerida": dep,
                            "version_resuelta": None,
                        }
                    )

    # setup.cfg
    setup_cfg = carpeta / "setup.cfg"
    if setup_cfg.is_file():
        manifestos.append("setup.cfg")
        texto, aviso = _leer_texto(setup_cfg, LIMITE_MANIFIESTO)
        if aviso:
            avisos.append(aviso)
        else:
            import configparser

            cfg = configparser.ConfigParser()
            try:
                cfg.read_string(texto)
                if cfg.has_option("metadata", "name") and "python" not in nombres_paquete:
                    nombres_paquete["python"] = cfg.get("metadata", "name")
                if cfg.has_option("options", "install_requires"):
                    for dep in cfg.get("options", "install_requires").splitlines():
                        dep = dep.strip()
                        if dep:
                            dependencias.append(
                                {
                                    "nombre": dep,
                                    "ecosistema": "python",
                                    "alcance": "ejecucion",
                                    "confianza": "declarada",
                                    "version_requerida": dep,
                                    "version_resuelta": None,
                                }
                            )
            except configparser.Error as fallo:
                avisos.append(_aviso("MANIFIESTO_INVALIDO", "fatal", "setup.cfg", str(fallo)))

    # requirements*.txt
    for req_file in sorted(carpeta.glob("requirements*.txt")):
        manifestos.append(req_file.name)
        texto, aviso = _leer_texto(req_file, LIMITE_MANIFIESTO)
        if aviso:
            avisos.append(aviso)
            continue
        for linea in texto.splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or linea.startswith("-"):
                continue
            dependencias.append(
                {
                    "nombre": linea,
                    "ecosistema": "python",
                    "alcance": "ejecucion",
                    "confianza": "declarada",
                    "version_requerida": linea,
                    "version_resuelta": None,
                }
            )

    # uv.lock (resuelve versiones de directas)
    uv_lock = carpeta / "uv.lock"
    if uv_lock.is_file() and uv_lock.stat().st_size <= LIMITE_LOCKFILE:
        try:
            texto = uv_lock.read_text(encoding="utf-8")
            lock = tomllib.loads(texto)
            for pkg in lock.get("package", []):
                nombre = pkg.get("name")
                version = pkg.get("version")
                if nombre and version:
                    for dep in dependencias:
                        if (
                            dep["nombre"]
                            .split("[")[0]
                            .split("=")[0]
                            .split(">")[0]
                            .split("<")[0]
                            .strip()
                            .lower()
                            == str(nombre).lower()
                        ):
                            dep["version_resuelta"] = str(version)
                            dep["confianza"] = "resuelta"
        except (OSError, tomllib.TOMLDecodeError):
            pass

    if not manifestos:
        return None, avisos

    # Si hay fatal, el proyecto se omite (no se devuelve)
    if any(a["severidad"] == "fatal" for a in avisos):
        return None, avisos

    proyecto = {
        "ecosistema": "python",
        "nombres_paquete": nombres_paquete,
        "archivos_manifesto": manifestos,
        "dependencias": dependencias,
    }
    return proyecto, avisos


registrar("python", detectar)
