# Detector de ecosistemas diferidos: emite ECOSISTEMA_NO_SOPORTADO como aviso informativo.
from __future__ import annotations

from devkit.tools.detectores import registrar

MARCADORES = {
    "pubspec.yaml": "dart",
    "mix.exs": "elixir",
    "Package.swift": "swift",
    "CMakeLists.txt": "cpp",
    "meson.build": "cpp",
    "Makefile": "cpp",
}


def detectar(raiz, carpeta, topes):
    avisos = []
    for marcador, eco in MARCADORES.items():
        if (carpeta / marcador).is_file():
            avisos.append(
                {
                    "codigo": "ECOSISTEMA_NO_SOPORTADO",
                    "severidad": "informativo",
                    "ruta_relativa": marcador,
                    "detalle": f"ecosistema {eco} diferido",
                }
            )
    # No devuelve proyecto; solo avisos.
    return None, avisos


registrar("deferido", detectar)
