# Gestor de notas Markdown con frontmatter validado.
from __future__ import annotations

import time
from pathlib import Path

from devkit.core import markdown as modulo_markdown
from devkit.core import runlog, safety
from devkit.errors import ErrorIdea

ESTADOS_VALIDOS = {'borrador', 'activo', 'archivado'}


def validar_raiz(raiz: Path | str) -> Path:
    # Comprueba que la raiz de notas exista y sea una carpeta.
    ruta = Path(raiz).expanduser().resolve()
    if not ruta.is_dir():
        raise ErrorIdea(f'la raiz no existe o no es carpeta {ruta}')
    return ruta


def crear_nota(
    raiz: Path,
    titulo: str,
    cuerpo: str,
    etiquetas: list[str] | None = None,
    estado: str = 'borrador',
) -> dict:
    # Crea una nota con frontmatter validado y nombre estable.
    safety.verificar_escritura('crear nota')
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    etiquetas = etiquetas or []
    if estado not in ESTADOS_VALIDOS:
        raise ErrorIdea(f'estado no permitido {estado}')
    # Aviso de duplicado por titulo sin bloquear la creacion.
    duplicado = False
    for existente in base.rglob('*.md'):
        try:
            datos, _ = modulo_markdown.parsear_frontmatter(existente.read_text(encoding='utf-8'))
        except OSError:
            continue
        if datos.get('titulo') == titulo:
            duplicado = True
            break
    ruta = modulo_markdown.generar_nombre(titulo, base)
    contenido = modulo_markdown.construir_nota(titulo, cuerpo, etiquetas, estado)
    ruta.write_text(contenido, encoding='utf-8')
    resultado = {
        'herramienta': 'idea',
        'accion': 'crear',
        'estado': 'correcto',
        'codigo': 0,
        'raiz': str(base),
        'ruta': str(ruta),
        'titulo': titulo,
        'etiquetas': etiquetas,
        'estado_nota': estado,
        'duplicado': duplicado,
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }
    runlog.registrar_ejecucion('idea', ['crear', titulo], inicio, 0, 0, 'crear')
    return resultado


def revisar_notas(raiz: Path) -> dict:
    # Recorre todas las notas y devuelve errores y avisos sin tocar el disco.
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    resultados = []
    total_errores = 0
    for ruta in sorted(base.rglob('*.md')):
        protegidas = {'.git', 'node_modules', '__pycache__'}
        if any(parte in protegidas for parte in ruta.relative_to(base).parts):
            continue
        resumen = modulo_markdown.revisar_nota(ruta, base)
        if resumen['errores']:
            total_errores += len(resumen['errores'])
        resultados.append(resumen)
    estado = 'correcto' if total_errores == 0 else 'error'
    codigo = 0 if total_errores == 0 else 2
    runlog.registrar_ejecucion('idea', ['revisar'], inicio, codigo, 0, estado)
    return {
        'herramienta': 'idea',
        'accion': 'revisar',
        'estado': estado,
        'codigo': codigo,
        'raiz': str(base),
        'total_notas': len(resultados),
        'total_errores': total_errores,
        'resultados': resultados,
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }


def listar_notas(raiz: Path, estado: str | None = None) -> dict:
    # Resume las notas con su frontmatter para listado rapido.
    base = validar_raiz(raiz)
    elementos = []
    for ruta in sorted(base.rglob('*.md')):
        protegidas = {'.git', 'node_modules', '__pycache__'}
        if any(parte in protegidas for parte in ruta.relative_to(base).parts):
            continue
        try:
            texto = ruta.read_text(encoding='utf-8')
        except OSError:
            continue
        datos, cuerpo = modulo_markdown.parsear_frontmatter(texto)
        if estado and datos.get('estado') != estado:
            continue
        elementos.append(
            {
                'ruta': str(ruta),
                'titulo': datos.get('titulo', ''),
                'creado': datos.get('creado', ''),
                'etiquetas': datos.get('etiquetas', []),
                'estado': datos.get('estado', ''),
                'palabras': len(cuerpo.split()),
            }
        )
    return {
        'herramienta': 'idea',
        'accion': 'listar',
        'estado': 'correcto',
        'codigo': 0,
        'raiz': str(base),
        'total': len(elementos),
        'notas': elementos,
    }
