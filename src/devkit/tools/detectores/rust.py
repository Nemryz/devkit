# Detector de proyectos Rust.
from __future__ import annotations

import tomllib

from devkit.tools.detectores import registrar

LIMITE_MANIFIESTO = 2 * 1024 * 1024
LIMITE_LOCKFILE = 16 * 1024 * 1024


def _aviso(codigo, severidad, ruta, detalle):
    return {"codigo": codigo, "severidad": severidad, "ruta_relativa": ruta, "detalle": detalle}


def _leer_texto(ruta, limite):
    try:
        if ruta.stat().st_size > limite:
            return None, _aviso(
                "MANIFIESTO_DEMASIADO_GRANDE", "fatal", str(ruta), f"{ruta.stat().st_size} bytes"
            )
        return ruta.read_text(encoding="utf-8"), None
    except OSError as fallo:
        return None, _aviso("MANIFIESTO_NO_LEGIBLE", "fatal", str(ruta), str(fallo))


def detectar(raiz, carpeta, topes):
    avisos = []
    manifestos = []
    nombres_paquete = {}
    dependencias = []
    miembros_workspace = []

    cargo_toml = carpeta / "Cargo.toml"
    if cargo_toml.is_file():
        manifestos.append("Cargo.toml")
        texto, aviso = _leer_texto(cargo_toml, LIMITE_MANIFIESTO)
        if aviso:
            avisos.append(aviso)
        else:
            try:
                datos = tomllib.loads(texto)
                paquete = datos.get("package", {})
                nombre = paquete.get("name")
                if nombre:
                    nombres_paquete["rust"] = str(nombre)
                for seccion, alcance in (
                    ("dependencies", "ejecucion"),
                    ("dev-dependencies", "prueba"),
                    ("build-dependencies", "construccion"),
                ):
                    for dep, spec in (datos.get(seccion) or {}).items():
                        dependencias.append(
                            {
                                "nombre": str(dep),
                                "ecosistema": "rust",
                                "alcance": alcance,
                                "confianza": "declarada",
                                "version_requerida": str(spec),
                                "version_resuelta": None,
                            }
                        )
                # workspace members
                ws = datos.get("workspace", {})
                members = ws.get("members", []) if isinstance(ws, dict) else []
                miembros_workspace.extend(members)
            except (tomllib.TOMLDecodeError, ValueError) as fallo:
                avisos.append(_aviso("MANIFIESTO_INVALIDO", "fatal", "Cargo.toml", str(fallo)))

    cargo_lock = carpeta / "Cargo.lock"
    if cargo_lock.is_file() and cargo_lock.stat().st_size <= LIMITE_LOCKFILE:
        try:
            texto = cargo_lock.read_text(encoding="utf-8")
            lock = tomllib.loads(texto)
            for pkg in lock.get("package", []):
                nombre = pkg.get("name")
                version = pkg.get("version")
                if nombre and version:
                    for dep in dependencias:
                        if dep["nombre"].lower() == str(nombre).lower():
                            dep["version_resuelta"] = str(version)
                            dep["confianza"] = "resuelta"
        except (OSError, tomllib.TOMLDecodeError):
            pass

    if not manifestos:
        return None, avisos
    if any(a["severidad"] == "fatal" for a in avisos):
        return None, avisos

    proyecto = {
        "ecosistema": "rust",
        "nombres_paquete": nombres_paquete,
        "archivos_manifesto": manifestos,
        "dependencias": dependencias,
        "miembros_workspace": miembros_workspace,
    }
    return proyecto, avisos


registrar("rust", detectar)
