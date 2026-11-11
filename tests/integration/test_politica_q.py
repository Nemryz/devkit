# Pruebas de regresion del bloque Q: politica inmutable y compuertas del ejecutor.
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devkit.cli import app
from devkit.core import capabilities, politica, runlog, safety, workspace
from devkit.errors import ErrorPolitica

EJECUTOR = CliRunner()
POLITICA_TRIM = politica.derivar('trim', 'aplicar', forzada=True)
POLITICA_DEDUPE = politica.derivar('dedupe', 'aplicar', forzada=True)
POLITICA_ORGANIZE = politica.derivar('organize', 'aplicar', confirmada=True)


def _entorno(tmp_path: Path) -> dict:
    return {'DEVKIT_ESTADO': str(tmp_path / 'estado')}


def _manifiesto(
    base: Path,
    acciones: list[dict],
    herramienta: str = 'organize',
    identificador: str = 'plan-q',
) -> Path:
    # Guarda un manifiesto firmado y ligado al workspace de la raiz.
    ident = workspace.workspace_id(base)
    return safety.guardar_plan(
        identificador,
        herramienta,
        acciones,
        destino_dir=base / 'planes',
        workspace_id=ident,
        workspace_root=str(base),
    )


def _accion_mover(base: Path, nombre: str = 'archivo.txt') -> tuple[dict, Path, Path]:
    # Construye una accion de movimiento con tamano y hash coherentes.
    origen = base / nombre
    destino = base / 'destino' / nombre
    origen.write_text('contenido', encoding='utf-8')
    accion = {
        'tipo': 'mover',
        'origen': str(origen),
        'destino': str(destino),
        'tamano': origen.stat().st_size,
        'hash': safety.hash_contenido(origen),
    }
    return accion, origen, destino


def _accion_papelera(base: Path, nombre: str = 'basura.txt') -> tuple[dict, Path]:
    # Construye una accion de papelera sobre un archivo real.
    origen = base / nombre
    origen.write_text('contenido', encoding='utf-8')
    return {'tipo': 'papelera', 'origen': str(origen)}, origen


def _hitos(ruta_plan: Path) -> list[dict]:
    return runlog.hitos_del_plan(ruta_plan.stem)


def test_politica_es_inmutable():
    # Una politica no puede mutarse despues de derivarla.
    with pytest.raises(FrozenInstanceError):
        POLITICA_TRIM.forzada = False


def test_huella_estable_y_sensible_a_las_compuertas():
    # La misma decision produce la misma huella y un cambio de compuerta la altera.
    otra = politica.derivar('trim', 'aplicar', forzada=True)
    assert POLITICA_TRIM.huella() == otra.huella()
    con_flags = politica.derivar(
        'trim', 'aplicar', forzada=True, flags=('plan', 'reanudar')
    )
    mismas_flags = politica.derivar(
        'trim', 'aplicar', forzada=True, flags=('reanudar', 'plan')
    )
    assert con_flags.huella() == mismas_flags.huella()
    assert con_flags.huella() != politica.derivar(
        'trim', 'aplicar', forzada=True, flags=('reanudar',)
    ).huella()
    assert POLITICA_TRIM.huella() != POLITICA_ORGANIZE.huella()


def test_derivar_exige_la_compuerta_de_anulacion():
    # trim no se puede aplicar sin --forzar aunque el manifiesto sea valido.
    with pytest.raises(ErrorPolitica, match='ANULACION_REQUERIDA'):
        politica.derivar('trim', 'aplicar')


def test_derivar_exige_la_compuerta_de_confirmacion():
    # organize no se puede aplicar sin --si aunque se pase --todos.
    with pytest.raises(ErrorPolitica, match='CONFIRMACION_REQUERIDA'):
        politica.derivar('organize', 'aplicar')


def test_compuertas_no_son_intercambiables():
    # Confirmar no anula una restriccion de seguridad y viceversa.
    with pytest.raises(ErrorPolitica, match='ANULACION_REQUERIDA'):
        politica.derivar('trim', 'aplicar', confirmada=True)
    with pytest.raises(ErrorPolitica, match='CONFIRMACION_REQUERIDA'):
        politica.derivar('organize', 'aplicar', forzada=True)


def test_capacidad_o_accion_no_declarada_se_rechaza():
    # Fuera del catalogo no hay politica que derivar.
    with pytest.raises(ErrorPolitica, match='POLITICA_NO_DECLARADA'):
        politica.derivar('inexistente', 'aplicar')
    with pytest.raises(ErrorPolitica, match='POLITICA_NO_DECLARADA'):
        politica.derivar('trim', 'inexistente')


def test_accion_sin_compuertas_declaradas_no_finge_politica():
    # Backup declara permisos pero no compuertas, asi que no promete lo que no aplica.
    with pytest.raises(ErrorPolitica, match='POLITICA_NO_DECLARADA'):
        politica.derivar('backup', 'ejecutar')


def test_catalogo_declara_compuertas_y_tipos_en_el_ejecutor():
    # Las acciones de escritura declaran su compuerta y su tipo de accion.
    esperadas = {
        ('trim', 'aplicar'): ['papelera'],
        ('dedupe', 'aplicar'): ['papelera'],
        ('organize', 'aplicar'): ['mover'],
    }
    for (capacidad, accion), tipos in esperadas.items():
        definicion = capabilities.obtener_capacidad(capacidad)['actions'][accion]
        assert 'compuertas' in definicion
        assert definicion['tipos'] == tipos
        assert definicion['compuertas']
    for capacidad, accion in (
        ('trim', 'escanear'),
        ('dedupe', 'escanear'),
        ('organize', 'plan'),
    ):
        definicion = capabilities.obtener_capacidad(capacidad)['actions'][accion]
        assert definicion['compuertas'] == {}
        assert definicion['tipos'] == []


@pytest.mark.parametrize(
    ('permiso', 'tipo'),
    [
        (POLITICA_TRIM, 'papelera'),
        (POLITICA_DEDUPE, 'papelera'),
        (POLITICA_ORGANIZE, 'mover'),
    ],
)
def test_cada_accion_declarada_permite_su_tipo(permiso, tipo):
    # La politica acepta el tipo que declara el catalogo y rechaza los demas.
    assert permiso.permite(tipo)
    assert not permiso.permite('crear_carpeta')
    assert not permiso.permite('tipo-inexistente')


def test_sin_politica_el_ejecutor_deniega(tmp_path):
    # Default deny: sin politica explicita no se toca el disco.
    accion, origen, _ = _accion_mover(tmp_path)
    ruta_plan = _manifiesto(tmp_path, [accion])
    with pytest.raises(ErrorPolitica, match='POLITICA_AUSENTE'):
        safety.aplicar_manifiesto(
            ruta_plan, 'organize', espacio_trabajo=str(tmp_path)
        )
    assert origen.exists()


def test_politica_de_otra_capacidad_se_rechaza(tmp_path):
    # Una politica de trim no autoriza un plan de organize.
    accion, origen, _ = _accion_mover(tmp_path)
    ruta_plan = _manifiesto(tmp_path, [accion])
    with pytest.raises(ErrorPolitica, match='POLITICA_INCOHERENTE'):
        safety.aplicar_manifiesto(
            ruta_plan, 'organize', espacio_trabajo=str(tmp_path),
            politica=POLITICA_TRIM,
        )
    assert origen.exists()


def test_tipo_de_accion_fuera_de_politica(tmp_path):
    # La politica de trim solo cubre papelera, no movimientos.
    accion, origen, destino = _accion_mover(tmp_path)
    ruta_plan = _manifiesto(tmp_path, [accion], herramienta='trim')
    with pytest.raises(ErrorPolitica, match='ACCION_FUERA_DE_POLITICA'):
        safety.aplicar_manifiesto(
            ruta_plan, 'trim', espacio_trabajo=str(tmp_path),
            politica=POLITICA_TRIM,
        )
    assert origen.exists()
    assert not destino.exists()


def test_journal_anota_la_politica_en_cada_hito(tmp_path):
    # Cada hito de la accion lleva la huella y los flags que autorizaron el cambio.
    accion, _, destino = _accion_mover(tmp_path)
    ruta_plan = _manifiesto(tmp_path, [accion])
    resultado = safety.aplicar_manifiesto(
        ruta_plan, 'organize', espacio_trabajo=str(tmp_path),
        politica=POLITICA_ORGANIZE,
    )
    assert resultado['politica_huella'] == POLITICA_ORGANIZE.huella()
    assert destino.exists()
    hitos = [h for h in _hitos(ruta_plan) if h.get('politica')]
    assert hitos
    for hito in hitos:
        anotacion = hito['politica']
        assert anotacion['huella'] == POLITICA_ORGANIZE.huella()
        assert anotacion['decision'] == 'PERMITIDA'
        assert anotacion['confirmada'] is True
        assert anotacion['forzada'] is False
        assert 'si' in anotacion['flags']


def test_simulacion_exige_la_misma_politica(tmp_path):
    # Simular sin politica falla y con politica devuelve la misma huella.
    accion, _, _ = _accion_mover(tmp_path)
    ruta_plan = _manifiesto(tmp_path, [accion])
    with pytest.raises(ErrorPolitica, match='POLITICA_AUSENTE'):
        safety.simular_manifiesto(
            ruta_plan, 'organize', espacio_trabajo=str(tmp_path)
        )
    simulado = safety.simular_manifiesto(
        ruta_plan, 'organize', espacio_trabajo=str(tmp_path),
        politica=POLITICA_ORGANIZE,
    )
    assert simulado['codigo'] == 0
    assert simulado['politica_huella'] == POLITICA_ORGANIZE.huella()


def test_aplicar_plan_persistente_usa_la_herramienta_del_manifiesto(tmp_path):
    # La forma antigua de la API tambien exige politica y respeta la herramienta.
    accion, _, destino = _accion_mover(tmp_path)
    ruta_plan = _manifiesto(tmp_path, [accion])
    with pytest.raises(ErrorPolitica, match='POLITICA_AUSENTE'):
        safety.aplicar_plan_persistente(
            ruta_plan, espacio_trabajo=str(tmp_path)
        )
    resultado = safety.aplicar_plan_persistente(
        ruta_plan, espacio_trabajo=str(tmp_path), politica=POLITICA_ORGANIZE
    )
    assert resultado['total'] == 1
    assert resultado['fallos'] == []
    assert destino.exists()


def test_organize_si_no_equivale_a_todos(tmp_path):
    # --si confirma pero no selecciona archivos; sin --todos no hay plan que aplicar.
    origen = tmp_path / 'descargas'
    origen.mkdir()
    archivo = origen / 'foto.jpg'
    archivo.write_bytes(b'\xff\xd8\xff\x00' + b'x' * 40)
    salida = EJECUTOR.invoke(
        app, ['organize', 'aplicar', str(origen), '--si'], env=_entorno(tmp_path)
    )
    assert salida.exit_code == 2
    assert 'sin --todos ni --por-archivo' in salida.output + salida.stderr
    assert archivo.exists()


def test_organize_todos_sin_si_no_aplica(tmp_path):
    # La seleccion no sustituye a la compuerta de confirmacion.
    origen = tmp_path / 'descargas'
    origen.mkdir()
    archivo = origen / 'foto.jpg'
    archivo.write_bytes(b'\xff\xd8\xff\x00' + b'x' * 40)
    salida = EJECUTOR.invoke(
        app, ['organize', 'aplicar', str(origen), '--todos'], env=_entorno(tmp_path)
    )
    assert salida.exit_code == 2
    datos = json.loads(salida.stdout)
    assert 'CONFIRMACION_REQUERIDA' in datos['detalle']
    assert archivo.exists()


def test_trim_sin_forzar_no_aplica_y_lo_dice(tmp_path):
    # La compuerta de anulacion tambien falla antes de escanear.
    origen = tmp_path / 'proyecto'
    origen.mkdir()
    cache = origen / '__pycache__'
    cache.mkdir()
    (cache / 'dato.pyc').write_bytes(b'x' * 20)
    salida = EJECUTOR.invoke(
        app, ['trim', 'aplicar', str(origen)], env=_entorno(tmp_path)
    )
    assert salida.exit_code == 2
    datos = json.loads(salida.stdout)
    assert 'ANULACION_REQUERIDA' in datos['detalle']
    assert cache.exists()


def test_cli_trim_forzar_deja_la_politica_en_el_journal(tmp_path, monkeypatch):
    # El camino humano y el de agentes comparten la misma politica anotada.
    monkeypatch.setenv('DEVKIT_ESTADO', str(tmp_path / 'estado'))
    origen = tmp_path / 'proyecto'
    origen.mkdir()
    cache = origen / '__pycache__'
    cache.mkdir()
    (cache / 'dato.pyc').write_bytes(b'x' * 20)
    monkeypatch.setattr(
        safety, 'mover_a_papelera_from_safety', lambda ruta: None
    )
    salida = EJECUTOR.invoke(
        app, ['trim', 'aplicar', str(origen), '--forzar']
    )
    assert salida.exit_code == 0
    referencia = politica.derivar('trim', 'aplicar', forzada=True)
    lineas = [
        json.loads(linea)
        for linea in runlog.ruta_journal().read_text(encoding='utf-8').splitlines()
        if linea.strip()
    ]
    hitos = [h for h in lineas if h.get('politica', {}).get('huella')]
    assert hitos
    assert hitos[-1]['politica']['huella'] == referencia.huella()
    assert 'forzar' in hitos[-1]['politica']['flags']
