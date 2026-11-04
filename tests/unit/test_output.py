# Pruebas del formato de salida comun.
import json

import pytest

from devkit.core import output
from devkit.errors import ErrorFormato


def test_serializar_conserva_tildes():
    texto = output.serializar({'nombre': 'diseño'})
    assert 'diseño' in texto


def test_emitir_json_escribe_en_stdout(capsys):
    output.emitir({'herramienta': 'prueba'}, formato='json')
    datos = json.loads(capsys.readouterr().out)
    assert datos['herramienta'] == 'prueba'


def test_emitir_rechaza_formato_desconocido():
    with pytest.raises(ErrorFormato):
        output.emitir({}, formato='xml')
