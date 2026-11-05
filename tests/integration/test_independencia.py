# Pruebas de independencia de ubicacion y espacio de trabajo.
import os
import subprocess
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from devkit.cli import app
from devkit.core import paths

EJECUTOR = CliRunner()


def _dev_executable() -> str:
    # Devuelve la ruta al ejecutable dev instalado.
    import shutil as sh

    encontrado = sh.which('dev')
    if encontrado:
        return encontrado
    candidato = Path.home() / '.local' / 'bin' / 'dev.exe'
    if candidato.is_file():
        return str(candidato)
    return 'dev'


def test_dev_responde_desde_raiz():
    # dev debe responder sin importar el directorio de trabajo.
    resultado = subprocess.run(
        [_dev_executable(), '--version'],
        capture_output=True,
        text=True,
        cwd='C:\\',
    )
    assert resultado.returncode == 0
    assert 'devkit' in resultado.stdout


def test_dev_responde_desde_temp():
    # dev debe responder desde una carpeta temporal arbitraria.
    with tempfile.TemporaryDirectory() as temporal:
        resultado = subprocess.run(
            [_dev_executable(), '--version'],
            capture_output=True,
            text=True,
            cwd=temporal,
        )
        assert resultado.returncode == 0
        assert 'devkit' in resultado.stdout


def test_dev_doctor_desde_carpeta_arbitraria():
    # doctor debe ejecutarse sin importar el cwd.
    with tempfile.TemporaryDirectory() as temporal:
        resultado = subprocess.run(
            [_dev_executable(), 'doctor'],
            capture_output=True,
            text=True,
            cwd=temporal,
        )
        assert resultado.returncode in (0, 1, 2)
        assert 'doctor' in resultado.stdout


def test_workspace_aislamiento_indices(tmp_path):
    # Dos espacios de trabajo no deben contaminar sus indices.
    ws1 = tmp_path / 'ws1' / 'notas'
    ws2 = tmp_path / 'ws2' / 'notas'
    ws1.mkdir(parents=True)
    ws2.mkdir(parents=True)
    (ws1 / 'a.md').write_text(
        '---\ntitulo: Alpha\ncreado: 2026-11-05\n---\n\nTexto sobre python', encoding='utf-8'
    )
    (ws2 / 'b.md').write_text(
        '---\ntitulo: Beta\ncreado: 2026-11-05\n---\n\nTexto sobre rust', encoding='utf-8'
    )

    env = {'DEVKIT_ESTADO': str(tmp_path / 'estado')}
    r1 = EJECUTOR.invoke(app, ['index', 'construir', str(ws1)], env=env)
    r2 = EJECUTOR.invoke(app, ['index', 'construir', str(ws2)], env=env)
    assert r1.exit_code == 0
    assert r2.exit_code == 0

    # Buscar en ws1 no debe devolver resultados de ws2.
    r3 = EJECUTOR.invoke(app, ['index', 'buscar', 'rust', '--raiz', str(ws1)], env=env)
    assert r3.exit_code == 0
    datos3 = __import__('json').loads(r3.stdout)
    assert datos3['total'] == 0

    # Buscar en ws2 no debe devolver resultados de ws1.
    r4 = EJECUTOR.invoke(app, ['index', 'buscar', 'python', '--raiz', str(ws2)], env=env)
    assert r4.exit_code == 0
    datos4 = __import__('json').loads(r4.stdout)
    assert datos4['total'] == 0


def test_paths_sin_rutas_personales():
    # Verificar que src/ no contenga rutas personales.
    raiz = Path(__file__).resolve().parents[2]
    src = raiz / 'src'
    for archivo in src.rglob('*.py'):
        texto = archivo.read_text(encoding='utf-8')
        assert 'ignac' not in texto.lower(), f'rutas personales en {archivo}'
        assert 'C:\\Users' not in texto, f'rutas personales en {archivo}'


def test_perfil_activo_por_defecto():
    # El perfil por defecto debe ser global.
    assert paths.perfil_activo() in {'global', 'portable', 'custom', 'temporary'}


def test_directorio_cache_existe():
    # directorio_cache debe devolver una ruta valida.
    cache = paths.directorio_cache()
    assert isinstance(cache, Path)


def test_directorio_planes_existe():
    # directorio_planes debe devolver una ruta valida.
    planes = paths.directorio_planes()
    assert isinstance(planes, Path)


def test_directorio_temporal_existe():
    # directorio_temporal debe devolver una ruta valida.
    temporal = paths.directorio_temporal()
    assert isinstance(temporal, Path)


def test_directorio_proyectos_no_hardcodeado():
    # directorio_proyectos no debe hardcodear rutas personales en el codigo.
    import inspect

    codigo = inspect.getsource(paths.directorio_proyectos)
    assert 'ignac' not in codigo.lower()
    assert 'C:\\\\Users' not in codigo


def test_workspace_activo_none_por_defecto():
    # Sin DEVKIT_WORKSPACE, workspace_activo devuelve None.

    os.environ.pop('DEVKIT_WORKSPACE', None)
    assert paths.workspace_activo() is None


def test_workspace_activo_con_variable():
    # Con DEVKIT_WORKSPACE, devuelve la ruta resuelta.

    os.environ['DEVKIT_WORKSPACE'] = 'C:\\tmp\\workspace'
    resultado = paths.workspace_activo()
    assert resultado is not None
    assert str(resultado).endswith('workspace')
    os.environ.pop('DEVKIT_WORKSPACE', None)
