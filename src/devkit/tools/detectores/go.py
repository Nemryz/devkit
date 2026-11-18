# Detector de proyectos Go.
from __future__ import annotations

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


def detectar(raiz, carpeta, topes):
    avisos = []
    manifestos = []
    nombres_paquete = {}
    dependencias = []

    go_mod = carpeta / "go.mod"
    if go_mod.is_file():
        manifestos.append("go.mod")
        texto, aviso = _leer_texto(go_mod, LIMITE_MANIFIESTO)
        if aviso:
            avisos.append(aviso)
        else:
            m = re.search(r"^module\s+(\S+)", texto, re.MULTILINE)
            if m:
                nombres_paquete["go"] = m.group(1)
            for m in re.finditer(r"^\s*(\S+)\s+v(\S+)(.*)$", texto, re.MULTILINE):
                dep_name = m.group(1)
                version = m.group(2)
                resto = m.group(3)
                if dep_name in ("go", "toolchain", "require", "module"):
                    continue
                if dep_name.startswith("//"):
                    continue
                confianza = "inferida" if "// indirect" in resto else "declarada"
                dependencias.append(
                    {
                        "nombre": dep_name,
                        "ecosistema": "go",
                        "alcance": "ejecucion",
                        "confianza": confianza,
                        "version_requerida": "v" + version,
                        "version_resuelta": None,
                    }
                )
            # go.sum (resuelve versiones)
            go_sum = carpeta / "go.sum"
            if go_sum.is_file() and go_sum.stat().st_size <= LIMITE_LOCKFILE:
                try:
                    sum_texto = go_sum.read_text(encoding="utf-8")
                    for dep in dependencias:
                        m = re.search(re.escape(dep["nombre"]) + r"\s+v(\S+)", sum_texto)
                        if m:
                            dep["version_resuelta"] = "v" + m.group(1)
                            dep["confianza"] = "resuelta"
                except OSError:
                    pass

    if not manifestos:
        return None, avisos
    if any(a["severidad"] == "fatal" for a in avisos):
        return None, avisos

    proyecto = {
        "ecosistema": "go",
        "nombres_paquete": nombres_paquete,
        "archivos_manifesto": manifestos,
        "dependencias": dependencias,
        "miembros_workspace": [],
    }
    return proyecto, avisos


registrar("go", detectar)
