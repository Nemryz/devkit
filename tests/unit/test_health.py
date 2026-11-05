# Pruebas de los bloques del informe de salud.
from devkit.tools import health


def test_calcular_estado_correcto():
    assert health.calcular_estado([{'estado': 'ok'}]) == ('correcto', 0)


def test_calcular_estado_aviso():
    assert health.calcular_estado([{'estado': 'ok'}, {'estado': 'aviso'}]) == ('aviso', 1)


def test_calcular_estado_error():
    assert health.calcular_estado([{'estado': 'ok'}, {'estado': 'error'}]) == ('error', 2)


def test_memoria_devuelve_numeros_reales():
    resultado = health.memoria()
    datos = resultado['valor']
    assert datos['total_gb'] > 0
    assert 0 <= datos['uso_pct'] <= 100
    assert resultado['estado'] in ('ok', 'aviso', 'error')


def test_disco_devuelve_numeros_reales():
    resultado = health.disco()
    datos = resultado['valor']
    assert datos['total_gb'] > 0
    assert datos['libre_gb'] > 0
    assert resultado['estado'] in ('ok', 'aviso', 'error')


def test_bateria_responde_sin_error():
    resultado = health.bateria()
    assert resultado['nombre'] == 'bateria'
    assert resultado['estado'] in ('ok', 'aviso', 'error', 'unknown')


def test_temperatura_sin_administrador_es_unknown():
    assert health.temperatura()['estado'] == 'unknown'


def test_smart_responde_sin_administrador():
    resultado = health.smart()
    assert resultado['nombre'] == 'smart'
    assert resultado['estado'] in ('ok', 'aviso', 'unknown')


def test_defender_responde_sin_administrador():
    resultado = health.defender()
    assert resultado['nombre'] == 'defender'
    assert resultado['estado'] in ('ok', 'aviso', 'unknown')


def test_actualizaciones_responde():
    resultado = health.actualizaciones()
    assert resultado['nombre'] == 'actualizaciones'
    assert resultado['estado'] in ('ok', 'aviso', 'error', 'unknown')


def test_inicio_responde():
    resultado = health.inicio()
    assert resultado['nombre'] == 'inicio'
    assert resultado['estado'] in ('ok', 'aviso', 'unknown')


def test_eventos_responde():
    resultado = health.eventos()
    assert resultado['nombre'] == 'eventos'
    assert resultado['estado'] in ('ok', 'aviso', 'unknown')


def test_ejecutar_salud_tiene_nueve_bloques(estado_temporal):
    resultado = health.ejecutar_salud(['health'])
    assert resultado['herramienta'] == 'health'
    assert resultado['codigo'] in (0, 1, 2)
    assert len(resultado['bloques']) == 9
    nombres = [fila['nombre'] for fila in resultado['bloques']]
    assert nombres == [
        'memoria',
        'disco',
        'bateria',
        'temperatura',
        'smart',
        'defender',
        'actualizaciones',
        'inicio',
        'eventos',
    ]
    assert (estado_temporal / 'journal' / 'ejecuciones.jsonl').exists()
