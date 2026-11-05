# Utilidades compartidas por las pruebas del toolkit.
import pytest


@pytest.fixture(autouse=True)
def estado_aislado(tmp_path, monkeypatch):
    # Aisla el estado por defecto en cada prueba para que el nucleo nunca escriba
    # en el perfil real del usuario, aunque la prueba no pida el fixture explicito.
    monkeypatch.setenv('DEVKIT_ESTADO', str(tmp_path / 'estado'))
    monkeypatch.setenv('DEVKIT_CONFIG', str(tmp_path / 'estado' / 'config'))


@pytest.fixture
def estado_temporal(tmp_path, monkeypatch):
    # Aisla el estado del toolkit para que las pruebas no escriban en el perfil real.
    destino = tmp_path / 'estado'
    monkeypatch.setenv('DEVKIT_ESTADO', str(destino))
    return destino
