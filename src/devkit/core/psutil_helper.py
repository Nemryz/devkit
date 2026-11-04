# Importacion perezosa de psutil para que dev --help cargue rapido.
from __future__ import annotations


def cargar_psutil():
    # Lo aplica el modulo de salud y doctor sin pagar el coste en --help.
    import psutil

    return psutil


def resumen_memoria():
    # Devuelve lo basico de memoria para el informe sin montar tablas.
    psutil = cargar_psutil()
    memoria = psutil.virtual_memory()
    return {
        'total_gb': round(memoria.total / (1024**3), 2),
        'disponible_gb': round(memoria.available / (1024**3), 2),
        'uso_pct': memoria.percent,
    }
