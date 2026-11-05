# Prueba de integracion del comando ocr de punta a punta.
import json
import os

import pytest
from typer.testing import CliRunner

from devkit.cli import app
from devkit.errors import ErrorOCR
from devkit.tools import ocr

SIN_TESSERACT = pytest.mark.skipif(
    not os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    reason="Tesseract no disponible",
)

EJECUTOR = CliRunner()


def crear_imagen(ruta, texto="Hola"):
    from PIL import Image, ImageDraw

    ruta.parent.mkdir(parents=True, exist_ok=True)
    imagen = Image.new("RGB", (800, 200), "white")
    dibujo = ImageDraw.Draw(imagen)
    dibujo.text((10, 10), texto, fill="black")
    imagen.save(str(ruta), "PNG")
    return ruta


@SIN_TESSERACT
def test_comando_escanear_responde_json(estado_temporal, tmp_path):
    crear_imagen(tmp_path / "foto.png", "Hola")
    env = {"DEVKIT_ESTADO": str(tmp_path / "estado")}
    resultado = EJECUTOR.invoke(app, ["ocr", "escanear", str(tmp_path)], env=env)
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos["herramienta"] == "ocr"
    assert datos["accion"] == "escanear"


@SIN_TESSERACT
def test_comando_exportar(estado_temporal, tmp_path):
    crear_imagen(tmp_path / "foto.png", "Hola")
    env = {"DEVKIT_ESTADO": str(tmp_path / "estado")}
    salida = tmp_path / "OCR"
    resultado = EJECUTOR.invoke(
        app, ["ocr", "exportar", str(tmp_path), "--destino", str(salida)], env=env
    )
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos["total_generadas"] >= 1


def test_escanear_rechaza_raiz_invalida(tmp_path):
    with pytest.raises(ErrorOCR):
        ocr.validar_raiz(tmp_path / "no-existe")
