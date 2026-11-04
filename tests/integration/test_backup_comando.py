# Prueba de integracion del comando backup de punta a punta.
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devkit.cli import app
from devkit.errors import ErrorRespaldo, ErrorSoloLectura
from devkit.tools import backup

EJECUTOR = CliRunner()
SIN_SIETE = pytest.mark.skipif(backup.encontrar_siete() is None, reason='7z no disponible')


@pytest.fixture
def arbol_origen(tmp_path):
    # Construye un arbol con acentos, espacios, carpeta vacia y una carpeta excluida.
    raiz = tmp_path / 'notas'
    (raiz / 'sub').mkdir(parents=True)
    (raiz / 'acentos').mkdir()
    (raiz / '.git').mkdir()
    (raiz / 'uno.md').write_text('contenido uno', encoding='utf-8')
    (raiz / 'sub' / 'dos con espacio.txt').write_text('contenido dos', encoding='utf-8')
    (raiz / 'acentos' / 'diseño.md').write_text('diseño', encoding='utf-8')
    (raiz / 'vacio.txt').write_text('', encoding='utf-8')
    (raiz / '.git' / 'ignorar.txt').write_text('no debe entrar', encoding='utf-8')
    return raiz


@SIN_SIETE
def test_crear_respaldo_genera_manifiesto(arbol_origen, tmp_path, estado_temporal):
    destino = tmp_path / 'respaldos'
    resultado = backup.crear_respaldo([arbol_origen], destino, 'prueba', 'clave-secreta', True)
    assert resultado['estado'] == 'correcto'
    carpeta = Path(resultado['carpeta'])
    assert (carpeta / 'manifiesto.json').is_file()
    assert (carpeta / 'respaldo.tar.7z').is_file()
    manifiesto = backup.leer_manifiesto(carpeta)
    assert manifiesto['total_archivos'] == 4
    assert manifiesto['cifrado'] is True
    rutas = [item['ruta'] for item in manifiesto['archivos']]
    assert all('.git/' not in ruta for ruta in rutas)


@SIN_SIETE
def test_verificar_respaldo_correcto(arbol_origen, tmp_path, estado_temporal):
    destino = tmp_path / 'respaldos'
    creado = backup.crear_respaldo([arbol_origen], destino, 'prueba', 'clave-secreta', True)
    resultado = backup.verificar_respaldo(Path(creado['carpeta']), 'clave-secreta')
    assert resultado['estado'] == 'correcto'
    assert resultado['correctos'] == 4
    assert resultado['faltantes'] == []
    assert resultado['alterados'] == []


@SIN_SIETE
def test_verificar_detecta_alteracion(arbol_origen, tmp_path, estado_temporal):
    destino = tmp_path / 'respaldos'
    creado = backup.crear_respaldo([arbol_origen], destino, 'prueba', 'clave-secreta', True)
    carpeta = Path(creado['carpeta'])
    ruta_manifiesto = carpeta / 'manifiesto.json'
    datos = json.loads(ruta_manifiesto.read_text(encoding='utf-8'))
    datos['archivos'][0]['sha256'] = '0' * 64
    ruta_manifiesto.write_text(json.dumps(datos), encoding='utf-8')
    resultado = backup.verificar_respaldo(carpeta, 'clave-secreta')
    assert resultado['estado'] == 'error'
    assert len(resultado['alterados']) == 1


@SIN_SIETE
def test_verificar_falla_con_clave_incorrecta(arbol_origen, tmp_path, estado_temporal):
    destino = tmp_path / 'respaldos'
    creado = backup.crear_respaldo([arbol_origen], destino, 'prueba', 'clave-secreta', True)
    with pytest.raises(ErrorRespaldo):
        backup.verificar_respaldo(Path(creado['carpeta']), 'clave-incorrecta')


@SIN_SIETE
def test_restaurar_devuelve_los_archivos(arbol_origen, tmp_path, estado_temporal):
    destino = tmp_path / 'respaldos'
    creado = backup.crear_respaldo([arbol_origen], destino, 'prueba', 'clave-secreta', True)
    restaurado = tmp_path / 'restaurado'
    resultado = backup.restaurar_respaldo(Path(creado['carpeta']), restaurado, 'clave-secreta')
    assert resultado['estado'] == 'correcto'
    assert resultado['correctos'] == 4
    assert (restaurado / 'notas' / 'uno.md').read_text(encoding='utf-8') == 'contenido uno'
    assert (restaurado / 'notas' / 'acentos' / 'diseño.md').read_text(encoding='utf-8') == 'diseño'


@SIN_SIETE
def test_restaurar_rechaza_destino_ocupado(arbol_origen, tmp_path, estado_temporal):
    destino = tmp_path / 'respaldos'
    creado = backup.crear_respaldo([arbol_origen], destino, 'prueba', 'clave-secreta', True)
    ocupado = tmp_path / 'ocupado'
    ocupado.mkdir()
    (ocupado / 'existente.txt').write_text('x', encoding='utf-8')
    with pytest.raises(ErrorRespaldo):
        backup.restaurar_respaldo(Path(creado['carpeta']), ocupado, 'clave-secreta')


@SIN_SIETE
def test_crear_sin_cifrado_no_pide_clave(arbol_origen, tmp_path, estado_temporal):
    destino = tmp_path / 'respaldos'
    creado = backup.crear_respaldo([arbol_origen], destino, 'simple', None, False)
    resultado = backup.verificar_respaldo(Path(creado['carpeta']), None)
    assert resultado['estado'] == 'correcto'


@SIN_SIETE
def test_listar_respaldos_resume_la_carpeta(arbol_origen, tmp_path, estado_temporal):
    destino = tmp_path / 'respaldos'
    backup.crear_respaldo([arbol_origen], destino, 'uno', 'clave-secreta', True)
    resultado = backup.listar_respaldos(destino)
    assert resultado['total'] == 1
    assert resultado['respaldos'][0]['etiqueta'] == 'uno'


def test_crear_bloqueado_en_solo_lectura(arbol_origen, tmp_path, estado_temporal, monkeypatch):
    monkeypatch.setenv('DEVKIT_READONLY', '1')
    with pytest.raises(ErrorSoloLectura):
        backup.crear_respaldo([arbol_origen], tmp_path / 'respaldos', 'prueba', 'clave', True)


@SIN_SIETE
def test_comando_crear_responde_json(arbol_origen, tmp_path):
    destino = tmp_path / 'respaldos'
    clave = tmp_path / 'clave.txt'
    clave.write_text('clave-secreta\n', encoding='utf-8')
    resultado = EJECUTOR.invoke(
        app,
        [
            'backup',
            'crear',
            '--origen',
            str(arbol_origen),
            '--destino',
            str(destino),
            '--clave',
            str(clave),
            '--etiqueta',
            'cli',
        ],
        env={'DEVKIT_ESTADO': str(tmp_path / 'estado')},
    )
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['herramienta'] == 'backup'
    assert datos['accion'] == 'crear'
    assert datos['total_archivos'] == 4
