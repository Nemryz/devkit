# Paquete de detectores de ecosistemas del workspace.
# Registro estatico: sin sistema de plugins ni carga dinamica.
from __future__ import annotations

from collections.abc import Callable

# Cada detector recibe (raiz: Path, carpeta: Path, topes: dict) y devuelve
# (proyecto_dict o None, lista_de_avisos).
Detector = Callable[[object, object, dict], tuple[object, list]]

REGISTRO: list[tuple[str, Detector]] = []


def registrar(nombre: str, funcion: Detector) -> None:
    REGISTRO.append((nombre, funcion))


def detectores_registrados() -> list[str]:
    return [nombre for nombre, _ in REGISTRO]
