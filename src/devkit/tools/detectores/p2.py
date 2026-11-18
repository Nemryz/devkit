# Detectores de ecosistemas P2 (JVM, .NET, PHP, Ruby) y marcadores de documentacion.
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

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


def _detectar_jvm(carpeta):
    avisos = []
    manifestos = []
    nombres = {}
    dependencias = []
    pom = carpeta / "pom.xml"
    if pom.is_file():
        manifestos.append("pom.xml")
        texto, aviso = _leer_texto(pom, LIMITE_MANIFIESTO)
        if aviso:
            avisos.append(aviso)
        else:
            try:
                root = ET.fromstring(texto)
                ns = {"m": "http://maven.apache.org/POM/4.0.0"}
                artifact = root.find("m:artifactId", ns)
                if artifact is None:
                    artifact = root.find("artifactId")
                if artifact is not None and artifact.text:
                    nombres["jvm"] = artifact.text.strip()
                for dep in root.iter("dependency"):
                    dep.find("groupId")
                    aid = dep.find("artifactId")
                    ver = dep.find("version")
                    if aid is not None and aid.text:
                        dependencias.append(
                            {
                                "nombre": aid.text.strip(),
                                "ecosistema": "jvm",
                                "alcance": "ejecucion",
                                "confianza": "declarada",
                                "version_requerida": (
                                    ver.text.strip() if ver is not None and ver.text else ""
                                ),
                                "version_resuelta": None,
                            }
                        )
            except ET.ParseError as fallo:
                avisos.append(_aviso("MANIFIESTO_INVALIDO", "fatal", "pom.xml", str(fallo)))
    # build.gradle (deteccion sin dependencias)
    for nombre_gradle in ("build.gradle", "build.gradle.kts"):
        g = carpeta / nombre_gradle
        if g.is_file():
            manifestos.append(nombre_gradle)
            texto, aviso = _leer_texto(g, LIMITE_MANIFIESTO)
            if aviso:
                avisos.append(aviso)
            else:
                m = re.search(r"rootProject\.name\s*=\s*['\"]([^'\"]+)['\"]", texto)
                if m and "jvm" not in nombres:
                    nombres["jvm"] = m.group(1)
                # group/name fallback
                if "jvm" not in nombres:
                    m = re.search(r"archivesBaseName\s*=\s*['\"]([^'\"]+)['\"]", texto)
                    if m:
                        nombres["jvm"] = m.group(1)
    if not manifestos:
        return None, avisos
    if any(a["severidad"] == "fatal" for a in avisos):
        return None, avisos
    return {
        "ecosistema": "jvm",
        "nombres_paquete": nombres,
        "archivos_manifesto": manifestos,
        "dependencias": dependencias,
        "miembros_workspace": [],
    }, avisos


def _detectar_dotnet(carpeta):
    avisos = []
    manifestos = []
    nombres = {}
    dependencias = []
    for csproj in carpeta.glob("*.csproj"):
        manifestos.append(csproj.name)
        texto, aviso = _leer_texto(csproj, LIMITE_MANIFIESTO)
        if aviso:
            avisos.append(aviso)
            continue
        try:
            root = ET.fromstring(texto)
            # nombre del proyecto
            name_el = root.find("PropertyGroup/AssemblyName")
            if name_el is None:
                name_el = root.find("PropertyGroup/RootNamespace")
            if name_el is not None and name_el.text:
                nombres["dotnet"] = name_el.text.strip()
            elif not nombres.get("dotnet"):
                nombres["dotnet"] = csproj.stem
            for ref in root.iter("PackageReference"):
                inc = ref.get("Include")
                ver = ref.get("Version")
                if inc:
                    dependencias.append(
                        {
                            "nombre": inc,
                            "ecosistema": "dotnet",
                            "alcance": "ejecucion",
                            "confianza": "declarada",
                            "version_requerida": ver or "",
                            "version_resuelta": None,
                        }
                    )
        except ET.ParseError as fallo:
            avisos.append(_aviso("MANIFIESTO_INVALIDO", "fatal", csproj.name, str(fallo)))
    if not manifestos:
        return None, avisos
    if any(a["severidad"] == "fatal" for a in avisos):
        return None, avisos
    if "dotnet" not in nombres and manifestos:
        nombres["dotnet"] = Path(manifestos[0]).stem
    return {
        "ecosistema": "dotnet",
        "nombres_paquete": nombres,
        "archivos_manifesto": manifestos,
        "dependencias": dependencias,
        "miembros_workspace": [],
    }, avisos


def _detectar_php(carpeta):
    avisos = []
    manifestos = []
    nombres = {}
    dependencias = []
    composer = carpeta / "composer.json"
    if composer.is_file():
        manifestos.append("composer.json")
        texto, aviso = _leer_texto(composer, LIMITE_MANIFIESTO)
        if aviso:
            avisos.append(aviso)
        else:
            try:
                datos = json.loads(texto)
                nombre = datos.get("name")
                if nombre:
                    nombres["php"] = str(nombre)
                for dep, ver in (datos.get("require") or {}).items():
                    dependencias.append(
                        {
                            "nombre": str(dep),
                            "ecosistema": "php",
                            "alcance": "ejecucion",
                            "confianza": "declarada",
                            "version_requerida": str(ver),
                            "version_resuelta": None,
                        }
                    )
                for dep, ver in (datos.get("require-dev") or {}).items():
                    dependencias.append(
                        {
                            "nombre": str(dep),
                            "ecosistema": "php",
                            "alcance": "desarrollo",
                            "confianza": "declarada",
                            "version_requerida": str(ver),
                            "version_resuelta": None,
                        }
                    )
            except (json.JSONDecodeError, ValueError) as fallo:
                avisos.append(_aviso("MANIFIESTO_INVALIDO", "fatal", "composer.json", str(fallo)))
    if not manifestos:
        return None, avisos
    if any(a["severidad"] == "fatal" for a in avisos):
        return None, avisos
    return {
        "ecosistema": "php",
        "nombres_paquete": nombres,
        "archivos_manifesto": manifestos,
        "dependencias": dependencias,
        "miembros_workspace": [],
    }, avisos


def _detectar_ruby(carpeta):
    avisos = []
    manifestos = []
    nombres = {}
    dependencias = []
    gemfile = carpeta / "Gemfile"
    if gemfile.is_file():
        manifestos.append("Gemfile")
        texto, aviso = _leer_texto(gemfile, LIMITE_MANIFIESTO)
        if aviso:
            avisos.append(aviso)
        else:
            # nombre del proyecto: no está en Gemfile; usar nombre de carpeta
            nombres["ruby"] = carpeta.name
            for m in re.finditer(r"gem\s+['\"]([^'\"]+)['\"]", texto):
                dependencias.append(
                    {
                        "nombre": m.group(1),
                        "ecosistema": "ruby",
                        "alcance": "ejecucion",
                        "confianza": "declarada",
                        "version_requerida": "",
                        "version_resuelta": None,
                    }
                )
    if not manifestos:
        return None, avisos
    if any(a["severidad"] == "fatal" for a in avisos):
        return None, avisos
    return {
        "ecosistema": "ruby",
        "nombres_paquete": nombres,
        "archivos_manifesto": manifestos,
        "dependencias": dependencias,
        "miembros_workspace": [],
    }, avisos


def _detectar_marcador_docs(carpeta):
    avisos = []
    manifestos = []
    if (carpeta / ".obsidian").is_dir():
        manifestos.append(".obsidian")
    if (carpeta / "mkdocs.yml").is_file():
        manifestos.append("mkdocs.yml")
    if (carpeta / "mkdocs.yaml").is_file():
        manifestos.append("mkdocs.yaml")
    for cfg in carpeta.glob("docusaurus.config.*"):
        manifestos.append(cfg.name)
    if not manifestos:
        return None, avisos
    return {
        "ecosistema": "docs",
        "nombres_paquete": {},
        "archivos_manifesto": manifestos,
        "dependencias": [],
        "miembros_workspace": [],
        "tipo": "marcador",
    }, avisos


def detectar_jvm(raiz, carpeta, topes):
    return _detectar_jvm(carpeta)


def detectar_dotnet(raiz, carpeta, topes):
    return _detectar_dotnet(carpeta)


def detectar_php(raiz, carpeta, topes):
    return _detectar_php(carpeta)


def detectar_ruby(raiz, carpeta, topes):
    return _detectar_ruby(carpeta)


def detectar_docs(raiz, carpeta, topes):
    return _detectar_marcador_docs(carpeta)


registrar("jvm", detectar_jvm)
registrar("dotnet", detectar_dotnet)
registrar("php", detectar_php)
registrar("ruby", detectar_ruby)
registrar("docs", detectar_docs)
