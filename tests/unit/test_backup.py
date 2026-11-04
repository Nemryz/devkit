# Pruebas de las funciones auxiliares del modulo de respaldos.
import pytest

from devkit.errors import ErrorClave, ErrorRespaldo
from devkit.tools import backup


def test_encontrar_siete_devuelve_una_ruta_o_nada():
    encontrado = backup.encontrar_siete()
    assert encontrado is None or encontrado.is_file()


def test_nombre_respaldo_sanea_la_etiqueta():
    nombre = backup.nombre_respaldo('copia de notas / 2026')
    assert ' ' not in nombre
    assert '/' not in nombre
    assert nombre.endswith('-copiadenotas2026')


def test_nombre_respaldo_sin_etiqueta_solo_tiene_marca():
    nombre = backup.nombre_respaldo('')
    assert len(nombre) == 15
    assert nombre[8] == '-'


def test_validar_origenes_rechaza_archivo(tmp_path):
    archivo = tmp_path / 'archivo.txt'
    archivo.write_text('x', encoding='utf-8')
    with pytest.raises(ErrorRespaldo):
        backup.validar_origenes([archivo])


def test_validar_origenes_rechaza_lista_vacia():
    with pytest.raises(ErrorRespaldo):
        backup.validar_origenes([])


def test_validar_destino_rechaza_carpeta_interna(tmp_path):
    origen = tmp_path / 'notas'
    origen.mkdir()
    with pytest.raises(ErrorRespaldo):
        backup.validar_destino(origen / 'respaldos', [origen])


def test_validar_destino_crea_la_carpeta(tmp_path):
    origen = tmp_path / 'notas'
    origen.mkdir()
    destino = backup.validar_destino(tmp_path / 'respaldos', [origen])
    assert destino.is_dir()


def test_recolectar_archivos_excluye_carpetas_conocidas(tmp_path):
    origen = tmp_path / 'notas'
    (origen / '.git').mkdir(parents=True)
    (origen / '.git' / 'ignorar.txt').write_text('x', encoding='utf-8')
    (origen / 'sub').mkdir()
    (origen / 'sub' / 'nota.md').write_text('hola', encoding='utf-8')
    registros, pares = backup.recolectar_archivos([origen])
    rutas = [registro['ruta'] for registro in registros]
    assert rutas == ['notas/sub/nota.md']
    assert len(pares) == 1


def test_recolectar_archivos_calcula_hash(tmp_path):
    origen = tmp_path / 'notas'
    origen.mkdir()
    archivo = origen / 'uno.txt'
    archivo.write_text('contenido', encoding='utf-8')
    registros, _ = backup.recolectar_archivos([origen])
    assert registros[0]['sha256'] == backup.calcular_sha256(archivo)
    assert registros[0]['tamano'] == 9


def test_obtener_clave_lee_el_archivo(tmp_path):
    archivo = tmp_path / 'clave.txt'
    archivo.write_text('secreto\nsegunda linea', encoding='utf-8')
    assert backup.obtener_clave(str(archivo)) == 'secreto'


def test_obtener_clave_rechaza_archivo_vacio(tmp_path):
    archivo = tmp_path / 'clave.txt'
    archivo.write_text('\n', encoding='utf-8')
    with pytest.raises(ErrorClave):
        backup.obtener_clave(str(archivo))


def test_obtener_clave_rechaza_archivo_inexistente(tmp_path):
    with pytest.raises(ErrorClave):
        backup.obtener_clave(str(tmp_path / 'no-existe.txt'))


def test_obtener_clave_usa_la_variable(monkeypatch):
    monkeypatch.setenv('DEVKIT_CLAVE', 'desde-entorno')
    assert backup.obtener_clave(None) == 'desde-entorno'


def test_obtener_clave_falla_sin_fuentes(monkeypatch):
    monkeypatch.delenv('DEVKIT_CLAVE', raising=False)
    with pytest.raises(ErrorClave):
        backup.obtener_clave(None)


def test_comparar_detecta_faltantes_y_alterados(tmp_path):
    base = tmp_path / 'base'
    base.mkdir()
    (base / 'uno.txt').write_text('uno', encoding='utf-8')
    manifiesto = {
        'archivos': [
            {'ruta': 'uno.txt', 'sha256': backup.calcular_sha256(base / 'uno.txt')},
            {'ruta': 'dos.txt', 'sha256': 'x'},
        ]
    }
    resultado = backup.comparar(base, manifiesto)
    assert resultado['correctos'] == 1
    assert resultado['faltantes'] == ['dos.txt']
    assert resultado['alterados'] == []
