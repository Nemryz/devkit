# Pruebas del extractor OCR en solo lectura.
import pytest

from devkit.errors import ErrorOCR, ErrorSoloLectura
from devkit.tools import ocr


def crear_imagen(ruta, texto="Hola"):
    from PIL import Image, ImageDraw

    ruta.parent.mkdir(parents=True, exist_ok=True)
    imagen = Image.new("RGB", (800, 200), "white")
    dibujo = ImageDraw.Draw(imagen)
    dibujo.text((10, 10), texto, fill="black")
    imagen.save(str(ruta), "PNG")
    return ruta


def test_validar_raiz_rechaza_inexistente(tmp_path):
    with pytest.raises(ErrorOCR):
        ocr.validar_raiz(tmp_path / "no-existe")


def test_validar_raiz_acepta(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    assert ocr.validar_raiz(tmp_path) == tmp_path.resolve()


def test_recolectar_solo_imagenes_pdf(tmp_path):
    crear_imagen(tmp_path / "foto.png")
    (tmp_path / "nota.txt").write_text("texto", encoding="utf-8")
    (tmp_path / "doc.pdf").write_bytes(b"%PDF-")
    archivos = ocr.recolectar_archivos(tmp_path, True)
    nombres = [r.name for r in archivos]
    assert "foto.png" in nombres
    assert "doc.pdf" in nombres
    assert "nota.txt" not in nombres


def test_recolectar_respeta_onedrive(tmp_path, monkeypatch):
    crear_imagen(tmp_path / "foto.png")
    monkeypatch.setenv("OneDrive", str(tmp_path))
    assert ocr.recolectar_archivos(tmp_path, True) == []
    assert len(ocr.recolectar_archivos(tmp_path, False)) >= 1


def test_escanear_devuelve_metricas(estado_temporal, tmp_path):
    pytest.importorskip("pytesseract")
    crear_imagen(tmp_path / "foto.png", "Hola")
    resultado = ocr.escanear_ocr(tmp_path, "spa", True)
    assert resultado["herramienta"] == "ocr"
    assert resultado["total_ok"] >= 1
    assert resultado["total_palabras"] >= 0


def test_escanear_solo_lectura_no_escribe(estado_temporal, tmp_path):
    pytest.importorskip("pytesseract")
    ruta = crear_imagen(tmp_path / "foto.png", "Hola")
    antes = ruta.stat().st_mtime
    ocr.escanear_ocr(tmp_path, "spa", True)
    assert ruta.stat().st_mtime == antes


def test_exportar_genera_nota_origen_ocr(estado_temporal, tmp_path):
    pytest.importorskip("pytesseract")
    crear_imagen(tmp_path / "doc.png", "Hola mundo")
    resultado = ocr.exportar_ocr(tmp_path, tmp_path / "salida", "spa")
    assert resultado["total_generadas"] >= 1
    notas = list((tmp_path / "salida").glob("*.md"))
    assert len(notas) == 1
    texto = notas[0].read_text(encoding="utf-8")
    assert "origen: ocr" in texto


def test_exportar_bloqueado_solo_lectura(estado_temporal, tmp_path, monkeypatch):
    crear_imagen(tmp_path / "doc.png")
    monkeypatch.setenv("DEVKIT_READONLY", "1")
    with pytest.raises(ErrorSoloLectura):
        ocr.exportar_ocr(tmp_path, tmp_path / "salida", "spa")


def test_escanear_rechaza_raiz_invalida(tmp_path):
    with pytest.raises(ErrorOCR):
        ocr.escanear_ocr(tmp_path / "no-existe")
