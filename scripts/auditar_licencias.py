# Auditoria de licencias de dependencias de DevKit.
from __future__ import annotations

import argparse
import importlib.metadata
import sys
import tomllib
from pathlib import Path

# Licencias copyleft que no deben aparecer en dependencias centrales.
COPYLEFT = {
    'AGPL-3.0',
    'GPL-2.0',
    'GPL-3.0',
    'LGPL-2.1',
    'LGPL-3.0',
    'EUPL-1.2',
}

# Mapa de licencia por nombre de paquete para auditoria sin instalacion.
LICENCIAS_CONOCIDAS: dict[str, str] = {
    'typer': 'MIT',
    'rich': 'MIT',
    'psutil': 'BSD-3-Clause',
    'pydantic': 'MIT',
    'orjson': 'Apache-2.0 / MIT',
    'blake3': 'CC0 / Apache-2.0',
    'send2trash': 'BSD-3-Clause',
    'pytesseract': 'Apache-2.0',
    'pillow': 'MIT-CMU (HPND)',
    'platformdirs': 'MIT',
    'pymupdf': 'AGPL-3.0 o comercial',
    'python-docx': 'MIT',
    'readability-lxml': 'Apache-2.0',
    'pandas': 'BSD-3-Clause',
    'pyarrow': 'Apache-2.0',
    'pytest': 'MIT',
    'pytest-cov': 'MIT',
    'ruff': 'MIT',
    'mypy': 'Apache-2.0',
}

EXTRAS = {'fs', 'docs', 'ocr', 'data'}


def _leer_pyproject(ruta: Path) -> dict:
    return tomllib.loads(ruta.read_text(encoding='utf-8'))


def _nombre_paquete(entrada: str) -> str:
    # Formato: "nombre[extra]>=version; extra == '...'"
    parte = entrada.split(';')[0].strip()
    for sep in ('[', '>', '<', '=', '!', ' '):
        parte = parte.split(sep)[0]
    return parte.strip()


def _dependencias_directas(datos: dict) -> list[str]:
    return [_nombre_paquete(d) for d in datos['project']['dependencies']]


def _dependencias_extra(datos: dict, extra: str) -> list[str]:
    opcionales = datos['project'].get('optional-dependencies', {})
    return [_nombre_paquete(d) for d in opcionales.get(extra, [])]


def _licencia(paquete: str) -> str:
    if paquete in LICENCIAS_CONOCIDAS:
        return LICENCIAS_CONOCIDAS[paquete]
    # Fallback a metadatos instalados.
    try:
        meta = importlib.metadata.metadata(paquete)
    except importlib.metadata.PackageNotFoundError:
        return 'desconocida'
    clasificador = meta.get_all('Classifier') or []
    for linea in clasificador:
        if linea.startswith('License ::'):
            return linea.rsplit('::', 1)[-1].strip()
    licencia = meta.get('License')
    return licencia.strip() if licencia else 'desconocida'


def _es_copyleft(licencia: str) -> bool:
    return any(c in licencia for c in COPYLEFT)


def auditar_nucleo(datos: dict) -> tuple[bool, list[str]]:
    hallazgos: list[str] = []
    for paquete in _dependencias_directas(datos):
        licencia = _licencia(paquete)
        if _es_copyleft(licencia):
            hallazgos.append(f'{paquete}: {licencia}')
    return (not hallazgos, hallazgos)


def auditar_extras(datos: dict) -> dict[str, list[str]]:
    resultado: dict[str, list[str]] = {}
    for extra in EXTRAS:
        hallazgos: list[str] = []
        for paquete in _dependencias_extra(datos, extra):
            licencia = _licencia(paquete)
            if _es_copyleft(licencia):
                hallazgos.append(f'{paquete}: {licencia}')
        resultado[extra] = hallazgos
    return resultado


def main() -> int:
    parser = argparse.ArgumentParser(description='Auditoria de licencias de DevKit')
    parser.add_argument('--nucleo', action='store_true', help='Auditar solo dependencias centrales')
    parser.add_argument('--extras', action='store_true', help='Auditar extras opcionales')
    parser.add_argument('--todo', action='store_true', help='Auditar nucleo y extras')
    args = parser.parse_args()

    if not (args.nucleo or args.extras or args.todo):
        args.todo = True

    ruta = Path(__file__).resolve().parents[1] / 'pyproject.toml'
    datos = _leer_pyproject(ruta)

    codigo_salida = 0

    if args.nucleo or args.todo:
        ok, hallazgos = auditar_nucleo(datos)
        if ok:
            print('Nucleo: sin licencias copyleft.')
        else:
            print('Nucleo: HALLAZGOS')
            for h in hallazgos:
                print(f'  - {h}')
            codigo_salida = 1

    if args.extras or args.todo:
        extras = auditar_extras(datos)
        for extra, hallazgos in extras.items():
            if hallazgos:
                print(f'Extra {extra}:')
                for h in hallazgos:
                    print(f'  - {h} (transitorio, ver ADR 0001)')
            else:
                print(f'Extra {extra}: sin licencias copyleft.')

    return codigo_salida


if __name__ == '__main__':
    sys.exit(main())
