# Extraccion de texto con Tesseract en modo de solo lectura.
from __future__ import annotations

import os
import statistics
import time
from pathlib import Path

from devkit.core import markdown as modulo_markdown
from devkit.core import paths, runlog, safety
from devkit.errors import ErrorOCR

EXTENSIONES_IMAGEN = {'.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.webp'}
EXTENSIONES_DOC = EXTENSIONES_IMAGEN | {'.pdf'}


def _tesseract() -> str | None:
    # Devuelve la ruta de tesseract.exe en su ubicacion habitual de Windows.
    import shutil

    ruta = shutil.which('tesseract')
    if ruta:
        return ruta
    candidatos = (
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    )
    for candidato in candidatos:
        if Path(candidato).is_file():
            return candidato
    return None


def validar_raiz(raiz: Path | str) -> Path:
    # Comprueba que la raiz exista y sea una carpeta.
    ruta = Path(raiz).expanduser().resolve()
    if not ruta.is_dir():
        raise ErrorOCR(f'la raiz no existe o no es carpeta {ruta}')
    return ruta


def _es_onedrive(ruta: Path) -> bool:
    return paths.es_onedrive(ruta)


def recolectar_archivos(raiz: Path, ignorar_onedrive: bool = True) -> list[Path]:
    # Recorre sin seguir enlaces y devuelve PDFs e imagenes de la raiz.
    base = validar_raiz(raiz)
    archivos: list[Path] = []
    protegidas = {'.git', '__pycache__', 'node_modules'}
    for carpeta, subcarpetas, entradas in os.walk(base, followlinks=False):
        ruta_carpeta = Path(carpeta)
        subcarpetas[:] = sorted(
            n for n in subcarpetas if n not in protegidas and not (ruta_carpeta / n).is_symlink()
        )
        partes = ruta_carpeta.relative_to(base).parts
        if partes and any(parte in protegidas for parte in partes):
            continue
        for nombre in sorted(entradas):
            ruta = ruta_carpeta / nombre
            if ruta.is_symlink() or ruta.is_junction():
                continue
            if ruta.suffix.lower() not in EXTENSIONES_DOC:
                continue
            if ignorar_onedrive and _es_onedrive(ruta):
                continue
            archivos.append(ruta)
    archivos.sort()
    return archivos


def _calcular_confianza(datos: list[dict]) -> dict:
    # Resume las confianzas de palabras en media, minima y conteo.
    valores = [int(d['conf']) for d in datos if int(d.get('conf', 0)) >= 0]
    if not valores:
        return {'media': 0.0, 'minima': 0, 'palabras': 0}
    return {
        'media': round(statistics.mean(valores), 1),
        'minima': min(valores),
        'palabras': len(valores),
    }


def _ocr_imagen(ruta: Path, idioma: str) -> dict:
    # Ejecuta Tesseract sobre una imagen y devuelve texto y confianza.
    import pytesseract
    from PIL import Image

    ruta_tess = _tesseract()
    if ruta_tess is None:
        raise ErrorOCR('tesseract.exe no encontrado, instalalo o ponlo en el PATH')
    pytesseract.pytesseract.tesseract_cmd = ruta_tess
    imagen = Image.open(ruta)
    texto = pytesseract.image_to_string(imagen, lang=idioma)
    datos = pytesseract.image_to_data(
        imagen, lang=idioma, config='--psm 6', output_type=pytesseract.Output.DICT
    )
    pares = zip(datos['text'], datos['conf'], strict=False)
    registros = [{'palabra': w, 'conf': int(c)} for w, c in pares]
    confianza = _calcular_confianza(registros)
    paginas = [
        {'pagina': 1, 'confianza_media': confianza['media'], 'palabras': confianza['palabras']}
    ]
    return {
        'ruta': str(ruta),
        'tipo': 'imagen',
        'texto': texto.strip(),
        'caracteres': len(texto.strip()),
        'palabras': len(texto.split()),
        'confianza': confianza,
        'paginas': paginas,
        'idioma': idioma,
    }


def _ocr_pdf(ruta: Path, idioma: str) -> dict:
    # Renderiza el PDF con PyMuPDF y pasa cada pagina por Tesseract.
    import fitz
    import pytesseract
    from PIL import Image

    ruta_tess = _tesseract()
    if ruta_tess is None:
        raise ErrorOCR('tesseract.exe no encontrado, instalalo o ponlo en el PATH')
    pytesseract.pytesseract.tesseract_cmd = ruta_tess
    documento = fitz.open(str(ruta))
    textos = []
    paginas = []
    for numero, pagina in enumerate(documento, start=1):
        pix = pagina.get_pixmap(dpi=150)
        imagen = Image.frombytes('RGB', [pix.w, pix.h], pix.samples)
        texto = pytesseract.image_to_string(imagen, lang=idioma)
        datos = pytesseract.image_to_data(
            imagen, lang=idioma, config='--psm 6', output_type=pytesseract.Output.DICT
        )
        pares = zip(datos['text'], datos['conf'], strict=False)
        registros = [{'palabra': w, 'conf': int(c)} for w, c in pares]
        confianza = _calcular_confianza(registros)
        textos.append(texto.strip())
        paginas.append(
            {
                'pagina': numero,
                'confianza_media': confianza['media'],
                'palabras': confianza['palabras'],
            }
        )
    texto_comun = '\n\n'.join(textos)
    medias = [p['confianza_media'] for p in paginas] if paginas else [0.0]
    minutos = [p['palabras'] for p in paginas] if paginas else [0]
    confianza = {
        'media': round(statistics.mean(medias), 1) if medias else 0.0,
        'minima': 0 if not medias else int(min(medias)),
        'palabras': sum(minutos),
    }
    return {
        'ruta': str(ruta),
        'tipo': 'pdf',
        'texto': texto_comun,
        'caracteres': len(texto_comun),
        'palabras': len(texto_comun.split()),
        'confianza': confianza,
        'paginas': paginas,
        'idioma': idioma,
    }


def escanear_ocr(raiz: Path, idioma: str = 'spa', ignorar_onedrive: bool = True) -> dict:
    # Extrae texto sin tocar el disco y devuelve metricas por archivo.
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    archivos = recolectar_archivos(base, ignorar_onedrive)
    resultados = []
    fallidos = []
    for ruta in archivos:
        try:
            if ruta.suffix.lower() == '.pdf':
                resultado = _ocr_pdf(ruta, idioma)
            else:
                resultado = _ocr_imagen(ruta, idioma)
            # Añade mtime para el manifiesto sin mutar el archivo.
            resultado['mtime'] = ruta.stat().st_mtime
            resultados.append(resultado)
        except Exception as fallo:  # noqa: BLE001
            fallidos.append({'ruta': str(ruta), 'detalle': str(fallo)})
    total_palabras = sum(r['palabras'] for r in resultados)
    medias = [r['confianza']['media'] for r in resultados] if resultados else [0.0]
    estado = 'correcto' if not fallidos else 'error'
    codigo = 0 if not fallidos else 2
    runlog.registrar_ejecucion('ocr', ['escanear'], inicio, codigo, 0, estado)
    return {
        'herramienta': 'ocr',
        'accion': 'escanear',
        'estado': estado,
        'codigo': codigo,
        'raiz': str(base),
        'total_archivos': len(archivos),
        'total_ok': len(resultados),
        'total_fallidos': len(fallidos),
        'total_palabras': total_palabras,
        'confianza_media': round(statistics.mean(medias), 1) if medias else 0.0,
        'resultados': resultados,
        'fallidos': fallidos,
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }


def exportar_ocr(raiz: Path, destino: Path | None = None, idioma: str = 'spa') -> dict:
    # Genera notas con origen ocr listas para idea e index.
    safety.verificar_escritura('exportar OCR')
    inicio = time.perf_counter()
    base = validar_raiz(raiz)
    carpeta_destino = Path(destino).expanduser().resolve() if destino else base / 'OCR'
    carpeta_destino.mkdir(parents=True, exist_ok=True)
    escaneo = escanear_ocr(base, idioma, True)
    generadas = []
    for resultado in escaneo['resultados']:
        ruta_origen = Path(resultado['ruta'])
        titulo = ruta_origen.stem
        ruta_nota = modulo_markdown.generar_nombre(titulo, carpeta_destino)
        contenido = modulo_markdown.construir_nota(
            titulo, resultado['texto'] or '(sin texto)', [], 'borrador', 'ocr'
        )
        ruta_nota.write_text(contenido, encoding='utf-8')
        generadas.append({'origen': str(ruta_origen), 'nota': str(ruta_nota)})
    runlog.registrar_ejecucion('ocr', ['exportar'], inicio, 0, 0, 'exportar')
    return {
        'herramienta': 'ocr',
        'accion': 'exportar',
        'estado': 'correcto',
        'codigo': 0,
        'raiz': str(base),
        'destino': str(carpeta_destino),
        'total_generadas': len(generadas),
        'generadas': generadas,
        'duracion_ms': round((time.perf_counter() - inicio) * 1000, 1),
    }
