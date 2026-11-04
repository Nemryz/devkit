# Pruebas de las comprobaciones individuales del doctor.
from devkit.tools import doctor


def test_calcular_estado_correcto():
    assert doctor.calcular_estado([{'estado': 'ok'}]) == ('correcto', 0)


def test_calcular_estado_aviso():
    assert doctor.calcular_estado([{'estado': 'ok'}, {'estado': 'aviso'}]) == ('aviso', 1)


def test_calcular_estado_error():
    assert doctor.calcular_estado([{'estado': 'aviso'}, {'estado': 'error'}]) == ('error', 2)


def test_comprobar_python_es_ok_en_esta_maquina():
    assert doctor.comprobar_python()['estado'] == 'ok'


def test_comprobar_dependencias_es_ok_en_esta_maquina():
    assert doctor.comprobar_dependencias()['estado'] == 'ok'


def test_comprobar_memoria_devuelve_un_numero():
    valor = doctor.comprobar_memoria()['valor']
    assert isinstance(valor, (int, float))
    assert valor > 0


def test_comprobar_disco_devuelve_un_numero():
    valor = doctor.comprobar_disco()['valor']
    assert isinstance(valor, (int, float))
    assert valor > 0


def test_comprobar_estado_crea_la_carpeta(estado_temporal):
    resultado = doctor.comprobar_estado()
    assert resultado['estado'] == 'ok'
    assert estado_temporal.is_dir()


def test_comprobar_journal_cuenta_cero_al_inicio(estado_temporal):
    resultado = doctor.comprobar_journal()
    assert resultado['estado'] == 'ok'
    assert resultado['valor'] == 0


def test_ejecutar_doctor_escribe_journal(estado_temporal):
    resultado = doctor.ejecutar_doctor()
    assert resultado['herramienta'] == 'doctor'
    assert resultado['codigo'] in (0, 1, 2)
    assert len(resultado['comprobaciones']) == 9
    assert (estado_temporal / 'journal' / 'ejecuciones.jsonl').exists()
