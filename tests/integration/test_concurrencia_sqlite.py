# Pruebas de concurrencia sobre el indice SQLite de un mismo espacio de trabajo.
import subprocess
import sys
from sqlite3 import connect

from devkit.tools import index as modulo_index

CODIGO_ESPACIO = (
    'import sys, time\n'
    'from pathlib import Path\n'
    'from devkit.tools import index as modulo_index\n'
    'raiz = Path(sys.argv[1])\n'
    'etiqueta = sys.argv[2]\n'
    'for i in range(4):\n'
    '    nombre = "nota_" + etiqueta + "_" + str(i) + ".md"\n'
    '    nota = raiz / nombre\n'
    '    nota.write_text("---\\ntitulo: " + etiqueta + " " + str(i) + "\\ncreado: 2026-11-05\\n'
    '---\\n\\ntexto " + etiqueta + " " + str(i) + "\\n", encoding="utf-8")\n'
    '    time.sleep(0.02)\n'
    '    modulo_index.actualizar_indice(raiz)\n'
)


def test_dos_procesos_actualizan_el_indice_sin_corromperlo(tmp_path, monkeypatch):
    notas = tmp_path / 'notas'
    notas.mkdir()
    inicial = notas / 'nota_inicial.md'
    inicial.write_text(
        '---\ntitulo: Inicial\ncreado: 2026-11-05\n---\n\ntexto de prueba inicial\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('DEVKIT_ESTADO', str(tmp_path / 'estado'))
    assert modulo_index.construir_indice(notas)['codigo'] == 0
    proceso1 = subprocess.Popen(
        [sys.executable, '-c', CODIGO_ESPACIO, str(notas), 'uno'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    proceso2 = subprocess.Popen(
        [sys.executable, '-c', CODIGO_ESPACIO, str(notas), 'dos'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    salida1, fallo1 = proceso1.communicate()
    salida2, fallo2 = proceso2.communicate()
    assert proceso1.returncode == 0, f'{salida1} {fallo1}'
    assert proceso2.returncode == 0, f'{salida2} {fallo2}'
    # Las nueve notas de ambos espacios llegaron al mismo indice serializado.
    revision = modulo_index.buscar(str(notas), 'texto', None, 50)
    assert revision['codigo'] == 0
    assert revision['total'] == 9
    conexion = connect(str(modulo_index.ruta_indice(notas, crear=False)))
    assert conexion.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    conexion.close()
