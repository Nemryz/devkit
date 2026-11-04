# Pruebas del modo de solo lectura y del objeto de plan.
import pytest

from devkit.core import safety
from devkit.errors import ErrorSoloLectura


def test_modo_solo_lectura_apagado_por_defecto(monkeypatch):
    monkeypatch.delenv('DEVKIT_READONLY', raising=False)
    assert safety.modo_solo_lectura() is False


def test_modo_solo_lectura_acepta_valores_conocidos(monkeypatch):
    monkeypatch.setenv('DEVKIT_READONLY', '1')
    assert safety.modo_solo_lectura() is True


def test_modo_solo_lectura_ignora_valores_vacios(monkeypatch):
    monkeypatch.setenv('DEVKIT_READONLY', '   ')
    assert safety.modo_solo_lectura() is False


def test_verificar_escritura_bloquea_en_solo_lectura(monkeypatch):
    monkeypatch.setenv('DEVKIT_READONLY', 'true')
    with pytest.raises(ErrorSoloLectura):
        safety.verificar_escritura('mover archivos')


def test_verificar_escritura_permite_sin_solo_lectura(monkeypatch):
    monkeypatch.delenv('DEVKIT_READONLY', raising=False)
    safety.verificar_escritura('mover archivos')


def test_plan_acumula_acciones():
    plan = safety.Plan()
    plan.agregar(safety.Accion(tipo='mover', origen='a', destino='b'))
    plan.agregar(safety.Accion(tipo='borrar', origen='c'))
    assert plan.total() == 2
