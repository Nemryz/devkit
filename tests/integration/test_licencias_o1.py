# Pruebas de regresion del bloque O1: licencia, distribucion y version.
import subprocess
import sys
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from devkit.cli import app

RAIZ = Path(__file__).resolve().parents[2]
EJECUTOR = CliRunner()


def _dependencias_centrales() -> list[str]:
    datos = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))
    resultado = []
    for d in datos['project']['dependencies']:
        nombre = d.split('[')[0].split('>')[0].split('<')[0].split('=')[0].split('!')[0].strip()
        resultado.append(nombre)
    return resultado


def _extras() -> dict[str, list[str]]:
    datos = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))
    resultado: dict[str, list[str]] = {}
    for nombre, deps in datos['project']['optional-dependencies'].items():
        limpios = []
        for d in deps:
            limpio = d.split('[')[0].split('>')[0].split('<')[0].split('=')[0].split('!')[0].strip()
            limpios.append(limpio)
        resultado[nombre] = limpios
    return resultado


def test_pymupdf_no_esta_en_dependencias_centrales():
    assert 'pymupdf' not in _dependencias_centrales()


def test_pymupdf_esta_en_extra_ocr():
    extras = _extras()
    assert 'pymupdf' in extras.get('ocr', [])


def test_ebooklib_no_esta_en_ningun_extra():
    extras = _extras()
    for nombre, deps in extras.items():
        assert 'ebooklib' not in deps, f'ebooklib sigue en el extra {nombre}'


def test_version_coincide_con_etiqueta():
    datos = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))
    version_paquete = datos['project']['version']
    assert version_paquete == '1.2.0'


def test_version_lee_metadata():
    from devkit import __version__

    assert __version__ == '1.2.0'


def test_dev_version_responde():
    resultado = EJECUTOR.invoke(app, ['--version'])
    assert resultado.exit_code == 0
    assert '1.2.0' in resultado.stdout


def test_license_existe():
    assert (RAIZ / 'LICENSE').is_file()
    assert (RAIZ / 'NOTICE').is_file()


def test_adr_existe():
    assert (RAIZ / 'docs' / 'adr' / '0001-distribucion-y-licencias.md').is_file()


def test_third_party_existe():
    assert (RAIZ / 'THIRD_PARTY.md').is_file()


def test_auditoria_nucleo_pasa():
    resultado = subprocess.run(
        [sys.executable, str(RAIZ / 'scripts' / 'auditar_licencias.py'), '--nucleo'],
        capture_output=True,
        text=True,
        cwd=str(RAIZ),
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_auditoria_extras_reporta_pymupdf():
    resultado = subprocess.run(
        [sys.executable, str(RAIZ / 'scripts' / 'auditar_licencias.py'), '--extras'],
        capture_output=True,
        text=True,
        cwd=str(RAIZ),
    )
    salida = resultado.stdout + resultado.stderr
    assert 'pymupdf' in salida.lower()
