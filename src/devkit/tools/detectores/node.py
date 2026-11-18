# Detector de proyectos Node/JavaScript/TypeScript.
from __future__ import annotations

import json
import re

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


def _parsear_pnpm_workspace(texto):
    # Parser minimo: solo listas simples de rutas bajo 'packages:'.
    miembros = []
    en_packages = False
    for linea in texto.splitlines():
        stripped = linea.strip()
        if stripped == "packages:":
            en_packages = True
            continue
        if en_packages:
            if not linea.startswith(" ") and not linea.startswith("\t"):
                en_packages = False
                continue
            m = re.match(r'\s*-\s*[\'"]?([^\'"]+)[\'"]?', stripped)
            if m:
                miembros.append(m.group(1))
            elif stripped and not stripped.startswith("#"):
                # estructura no reconocible
                return None
    return miembros


def detectar(raiz, carpeta, topes):
    avisos = []
    manifestos = []
    nombres_paquete = {}
    dependencias = []
    miembros_workspace = []

    package_json = carpeta / "package.json"
    if package_json.is_file():
        manifestos.append("package.json")
        texto, aviso = _leer_texto(package_json, LIMITE_MANIFIESTO)
        if aviso:
            avisos.append(aviso)
        else:
            try:
                datos = json.loads(texto)
                nombre = datos.get("name")
                if nombre:
                    nombres_paquete["node"] = str(nombre)
                for alcance_key, alcance in (
                    ("dependencies", "ejecucion"),
                    ("devDependencies", "desarrollo"),
                    ("peerDependencies", "peer"),
                    ("optionalDependencies", "opcional"),
                ):
                    for dep, ver in (datos.get(alcance_key) or {}).items():
                        dependencias.append(
                            {
                                "nombre": str(dep),
                                "ecosistema": "node",
                                "alcance": alcance,
                                "confianza": "declarada",
                                "version_requerida": str(ver),
                                "version_resuelta": None,
                            }
                        )
                # workspaces
                ws = datos.get("workspaces")
                if isinstance(ws, list):
                    miembros_workspace.extend(ws)
                elif isinstance(ws, dict) and isinstance(ws.get("packages"), list):
                    miembros_workspace.extend(ws["packages"])
            except (json.JSONDecodeError, ValueError) as fallo:
                avisos.append(_aviso("MANIFIESTO_INVALIDO", "fatal", "package.json", str(fallo)))

    pnpm_ws = carpeta / "pnpm-workspace.yaml"
    if pnpm_ws.is_file():
        manifestos.append("pnpm-workspace.yaml")
        texto, aviso = _leer_texto(pnpm_ws, LIMITE_MANIFIESTO)
        if aviso:
            avisos.append(aviso)
        else:
            parsed = _parsear_pnpm_workspace(texto)
            if parsed is None:
                avisos.append(
                    _aviso(
                        "CAMPO_INVALIDO",
                        "informativo",
                        "pnpm-workspace.yaml",
                        "estructura no reconocible",
                    )
                )
            else:
                miembros_workspace.extend(parsed)

    # lockfiles
    package_lock = carpeta / "package-lock.json"
    if package_lock.is_file() and package_lock.stat().st_size <= LIMITE_LOCKFILE:
        try:
            datos = json.loads(package_lock.read_text(encoding="utf-8"))
            paquetes = datos.get("packages", {}) or datos.get("dependencies", {})
            for dep in dependencias:
                # buscar en lock
                for clave, info in paquetes.items() if isinstance(paquetes, dict) else []:
                    if clave.endswith(dep["nombre"]) or clave == "node_modules/" + dep["nombre"]:
                        ver = info.get("version") if isinstance(info, dict) else None
                        if ver:
                            dep["version_resuelta"] = str(ver)
                            dep["confianza"] = "resuelta"
        except (OSError, json.JSONDecodeError):
            pass

    pnpm_lock = carpeta / "pnpm-lock.yaml"
    if pnpm_lock.is_file() and pnpm_lock.stat().st_size <= LIMITE_LOCKFILE:
        try:
            texto = pnpm_lock.read_text(encoding="utf-8")
            # parser minimo: buscar "nombre: version" en seccion packages
            for dep in dependencias:
                m = re.search(r"'" + re.escape(dep["nombre"]) + r"@([^']+)'", texto)
                if m:
                    dep["version_resuelta"] = m.group(1)
                    dep["confianza"] = "resuelta"
        except OSError:
            pass

    if not manifestos:
        return None, avisos
    if any(a["severidad"] == "fatal" for a in avisos):
        return None, avisos

    proyecto = {
        "ecosistema": "node",
        "nombres_paquete": nombres_paquete,
        "archivos_manifesto": manifestos,
        "dependencias": dependencias,
        "miembros_workspace": miembros_workspace,
    }
    return proyecto, avisos


registrar("node", detectar)
