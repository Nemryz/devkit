# Utilidades compartidas por las pruebas del toolkit.
import pytest


@pytest.fixture
def estado_temporal(tmp_path, monkeypatch):
    # Aisla el estado del toolkit para que las pruebas no escriban en el perfil real.
    destino = tmp_path / 'estado'
    monkeypatch.setenv('DEVKIT_ESTADO', str(destino))
    return destino
