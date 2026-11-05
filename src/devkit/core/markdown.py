# Parser minimalista de frontmatter para notas Markdown.
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any


def parsear_frontmatter(texto: str) -> tuple[dict[str, Any], str]:
    # Extrae el bloque entre --- y devuelve el resto del cuerpo.
    texto = texto.lstrip('\ufeff')
    if not texto.startswith('---\n') and not texto.startswith('---\r\n'):
        return {}, texto
    fin = texto.find('\n---', 3)
    if fin == -1:
        return {}, texto
    bloque = texto[4:fin].strip()
    cuerpo = texto[fin + 4:].lstrip('\n').lstrip('\r')
    datos: dict[str, Any] = {}
    for linea in bloque.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith('#'):
            continue
        if ':' not in linea:
            continue
        clave, _, valor = linea.partition(':')
        clave = clave.strip()
        valor = valor.strip()
        if valor.startswith('[') and valor.endswith(']'):
            interno = valor[1:-1]
            elementos = [
                item.strip().strip('"').strip("'") for item in interno.split(',') if item.strip()
            ]
            datos[clave] = elementos
        elif valor.lower() in {'true', 'false'}:
            datos[clave] = valor.lower() == 'true'
        else:
            datos[clave] = valor
    return datos, cuerpo


def validar_metadatos(datos: dict[str, Any]) -> list[str]:
    # Devuelve la lista de errores de campos obligatorios y tipos.
    errores = []
    if not datos.get('titulo'):
        errores.append('falta el campo titulo')
    creado = datos.get('creado')
    if not creado:
        errores.append('falta el campo creado')
    else:
        try:
            datetime.strptime(str(creado), '%Y-%m-%d')
        except ValueError:
            errores.append('creado debe tener formato YYYY-MM-DD')
    if 'etiquetas' in datos and not isinstance(datos['etiquetas'], list):
        errores.append('etiquetas debe ser una lista')
    if 'estado' in datos and datos['estado'] not in {'borrador', 'activo', 'archivado'}:
        errores.append('estado solo admite borrador, activo o archivado')
    if 'origen' in datos and datos['origen'] not in {'manual', 'ocr', 'scrape', 'importado'}:
        errores.append('origen solo admite manual, ocr, scrape o importado')
    return errores


def slugify(texto: str) -> str:
    # Convierte un titulo en un nombre de archivo seguro y estable.
    base = texto.lower()
    for caracter in 'áéíóúüñ':
        equivalente = {
            'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u', 'ñ': 'n'
        }[caracter]
        base = base.replace(caracter, equivalente)
    base = re.sub(r'[^a-z0-9]+', '-', base).strip('-')
    return base or 'nota'


def generar_nombre(titulo: str, carpeta: Path) -> Path:
    # Encuentra un nombre libre con slug y sufijo numerico si hace falta.
    slug = slugify(titulo)
    fecha = datetime.now().strftime('%Y-%m-%d')
    candidato = carpeta / f'{fecha}-{slug}.md'
    contador = 2
    while candidato.exists():
        candidato = carpeta / f'{fecha}-{slug}-{contador}.md'
        contador += 1
    return candidato


def enlaces_rotos(texto: str, base: Path) -> list[str]:
    # Detecta enlaces [texto](ruta.md) que no apunten a un archivo real.
    patron = re.compile(r'\[[^\]]*\]\(([^)]+)\)')
    rotos = []
    for destino in patron.findall(texto):
        if (
            destino.startswith('http://')
            or destino.startswith('https://')
            or destino.startswith('#')
        ):
            continue
        ruta = (base / destino.split('#', 1)[0]).resolve()
        try:
            ruta.relative_to(base.resolve())
        except ValueError:
            rotos.append(destino)
            continue
        if not ruta.is_file():
            rotos.append(destino)
    return rotos


def frontmatter_a_texto(datos: dict[str, Any]) -> str:
    # Serializa los metadatos a bloque YAML sencillo y estable.
    lineas = ['---']
    for clave, valor in datos.items():
        if isinstance(valor, list):
            lineas.append(f'{clave}: [{", ".join(str(item) for item in valor)}]')
        elif isinstance(valor, bool):
            lineas.append(f'{clave}: {"true" if valor else "false"}')
        else:
            lineas.append(f'{clave}: {valor}')
    lineas.append('---')
    return '\n'.join(lineas)


def construir_nota(
    titulo: str,
    cuerpo: str,
    etiquetas: list[str],
    estado: str,
    origen: str = 'manual',
) -> str:
    # Arma la nota completa con frontmatter y cuerpo.
    datos = {
        'titulo': titulo,
        'creado': datetime.now().strftime('%Y-%m-%d'),
        'etiquetas': etiquetas,
        'estado': estado,
        'origen': origen,
    }
    bloque = frontmatter_a_texto(datos)
    return f'{bloque}\n\n{cuerpo.strip()}\n'


def revisar_nota(ruta: Path, base: Path) -> dict:
    # Devuelve errores y avisos para un archivo Markdown concreto.
    try:
        texto = ruta.read_text(encoding='utf-8')
    except OSError as fallo:
        return {'ruta': str(ruta), 'errores': [f'no se puede leer {fallo}'], 'avisos': []}
    datos, cuerpo = parsear_frontmatter(texto)
    errores = validar_metadatos(datos)
    rotos = enlaces_rotos(texto, base)
    for roto in rotos:
        errores.append(f'enlace roto {roto}')
    avisos = []
    if not cuerpo.strip():
        avisos.append('cuerpo vacio')
    return {'ruta': str(ruta), 'errores': errores, 'avisos': avisos}
