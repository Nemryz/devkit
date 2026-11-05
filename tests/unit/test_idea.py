# Pruebas del parser de frontmatter y del modulo de notas.
import os

import pytest

from devkit.core import markdown
from devkit.errors import ErrorSoloLectura
from devkit.tools import idea


def test_parsear_frontmatter_extrae_datos():
    texto = (
        '---\ntitulo: Hola\ncreado: 2026-11-05\netiquetas: [a, b]\n'
        'estado: activo\n---\n\nCuerpo'
    )
    datos, cuerpo = markdown.parsear_frontmatter(texto)
    assert datos['titulo'] == 'Hola'
    assert datos['creado'] == '2026-11-05'
    assert datos['etiquetas'] == ['a', 'b']
    assert datos['estado'] == 'activo'
    assert 'Cuerpo' in cuerpo


def test_parsear_sin_frontmatter_devuelve_vacio():
    datos, cuerpo = markdown.parsear_frontmatter('Solo texto')
    assert datos == {}
    assert 'Solo texto' in cuerpo


def test_validar_metadatos_detecta_faltantes():
    errores = markdown.validar_metadatos({})
    assert 'falta el campo titulo' in errores
    assert 'falta el campo creado' in errores


def test_validar_metadatos_valida_fecha():
    assert 'creado debe tener formato YYYY-MM-DD' in markdown.validar_metadatos(
        {'titulo': 'x', 'creado': 'ayer'}
    )


def test_validar_metadatos_estado_invalido():
    assert 'estado solo admite borrador, activo o archivado' in markdown.validar_metadatos(
        {'titulo': 'x', 'creado': '2026-11-05', 'estado': 'otro'}
    )


def test_slugify_con_tildes():
    assert markdown.slugify('Año nuevo — proyecto') == 'ano-nuevo-proyecto'


def test_slugify_vacio_devuelve_nota():
    assert markdown.slugify('!!!') == 'nota'


def test_generar_nombre_evita_colisiones(tmp_path):
    (tmp_path / '2026-01-01-hola.md').write_text('x', encoding='utf-8')
    # Forzar la fecha para que coincida con el prefijo de hoy.
    import datetime

    hoy = datetime.date.today().isoformat()
    (tmp_path / f'{hoy}-hola.md').write_text('x', encoding='utf-8')
    ruta = markdown.generar_nombre('hola', tmp_path)
    assert ruta.name.startswith(hoy)
    assert 'hola-2' in ruta.name


def test_enlaces_rotos_detecta_inexistente(tmp_path):
    base = tmp_path / 'notas'
    base.mkdir()
    texto = 'ver [otro](otro.md) y [absoluto](no-existe.md)'
    rotos = markdown.enlaces_rotos(texto, base)
    assert 'otro.md' in rotos
    assert 'no-existe.md' in rotos


def test_enlaces_rotos_ignora_http_y_ancla():
    base = os.path.join(os.sep, 'tmp', 'notas')
    rotos = markdown.enlaces_rotos('[a](https://x.com) [b](#seccion)', base)
    assert rotos == []


def test_construir_nota_incluye_frontmatter():
    nota = markdown.construir_nota('Titulo', 'Cuerpo', ['a', 'b'], 'activo')
    assert 'titulo: Titulo' in nota
    assert 'etiquetas: [a, b]' in nota
    assert 'Cuerpo' in nota


def test_revisar_nota_detecta_cuerpo_vacio(tmp_path):
    base = tmp_path / 'notas'
    base.mkdir()
    (base / 'vacia.md').write_text(
        '---\ntitulo: Vacia\ncreado: 2026-11-05\n---\n', encoding='utf-8'
    )
    resultado = markdown.revisar_nota(base / 'vacia.md', base)
    assert resultado['errores'] == []
    assert 'cuerpo vacio' in resultado['avisos']


def test_crear_nota_genera_archivo(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    resultado = idea.crear_nota(raiz, 'Mi idea', 'Contenido', ['devkit'], 'activo')
    assert resultado['herramienta'] == 'idea'
    ruta = raiz / os.path.basename(resultado['ruta'])
    assert ruta.is_file()
    assert 'Mi idea' in ruta.read_text(encoding='utf-8')


def test_crear_nota_avisa_duplicado(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    idea.crear_nota(raiz, 'Idea repetida', 'Primera')
    segundo = idea.crear_nota(raiz, 'Idea repetida', 'Segunda')
    assert segundo['duplicado'] is True


def test_revisar_notas_detecta_errores(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    (raiz / 'mala.md').write_text('sin frontmatter', encoding='utf-8')
    (raiz / 'buena.md').write_text(
        '---\ntitulo: Buena\ncreado: 2026-11-05\n---\n\nCuerpo', encoding='utf-8'
    )
    resultado = idea.revisar_notas(raiz)
    assert resultado['total_errores'] >= 1
    assert resultado['estado'] == 'error'


def test_revisar_notas_todo_correcto(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    (raiz / 'buena.md').write_text(
        '---\ntitulo: Buena\ncreado: 2026-11-05\n---\n\nCuerpo', encoding='utf-8'
    )
    resultado = idea.revisar_notas(raiz)
    assert resultado['estado'] == 'correcto'
    assert resultado['codigo'] == 0


def test_listar_notas_filtra_por_estado(estado_temporal, tmp_path):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    (raiz / 'a.md').write_text(
        '---\ntitulo: A\ncreado: 2026-11-05\nestado: activo\n---\n\nCuerpo', encoding='utf-8'
    )
    (raiz / 'b.md').write_text(
        '---\ntitulo: B\ncreado: 2026-11-05\nestado: borrador\n---\n\nCuerpo', encoding='utf-8'
    )
    resultado = idea.listar_notas(raiz, 'activo')
    assert resultado['total'] == 1
    assert resultado['notas'][0]['titulo'] == 'A'


def test_crear_nota_bloqueada_solo_lectura(estado_temporal, tmp_path, monkeypatch):
    raiz = tmp_path / 'notas'
    raiz.mkdir()
    monkeypatch.setenv('DEVKIT_READONLY', '1')
    with pytest.raises(ErrorSoloLectura):
        idea.crear_nota(raiz, 'X', 'Cuerpo')
