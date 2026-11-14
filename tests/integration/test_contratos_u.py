# Pruebas de regresion del bloque U: contratos versionados y migracion explicita.
import json
import tomllib
from importlib.metadata import version as version_paquete
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devkit import config as modulo_config
from devkit.cli import app
from devkit.core import capabilities, paths, safety, workspace
from devkit.errors import ErrorConfiguracion

EJECUTOR = CliRunner()


def _entorno(tmp_path: Path) -> dict:
    return {
        'DEVKIT_ESTADO': str(tmp_path / 'estado'),
        'DEVKIT_CONFIG': str(tmp_path / 'configuracion'),
    }


def _journal_lineas() -> list[str]:
    ruta = paths.ruta_journal()
    if not ruta.exists():
        return []
    return ruta.read_text(encoding='utf-8').splitlines()


def _accion_mover(base: Path, nombre: str = 'archivo.txt') -> tuple[dict, Path, Path]:
    # Construye una accion de movimiento con tamano, fecha y hash coherentes.
    origen = base / nombre
    destino = base / 'destino' / nombre
    origen.write_text('contenido', encoding='utf-8')
    accion = {
        'tipo': 'mover',
        'origen': str(origen),
        'destino': str(destino),
        'tamano': origen.stat().st_size,
        'mtime': origen.stat().st_mtime,
        'hash': safety.hash_contenido(origen),
    }
    return accion, origen, destino


def _manifiesto_v2(
    base: Path,
    acciones: list[dict],
    identificador: str = 'plan-u',
) -> Path:
    # Guarda un manifiesto v2 firmado y ligado al workspace de la raiz.
    return safety.guardar_plan(
        identificador,
        'organize',
        acciones,
        destino_dir=base / 'planes',
        workspace_id=workspace.workspace_id(base),
        workspace_root=str(base),
    )


def _manifiesto_v1(
    base: Path,
    acciones: list[dict],
    identificador: str = 'plan-u-v1',
) -> Path:
    # Guarda un manifiesto v1 con una firma valida para probar la migracion.
    destino = base / 'planes'
    destino.mkdir(parents=True, exist_ok=True)
    ident = workspace.workspace_id(base)
    firma = safety.firmar_plan(
        acciones,
        schema_version=1,
        plan_id=identificador,
        workspace_id=ident,
        workspace_root=str(base),
        herramienta='organize',
    )
    datos = {
        'schema_version': 1,
        'plan_id': identificador,
        'id_ejecucion': identificador,
        'workspace_id': ident,
        'workspace_root': str(base),
        'herramienta': 'organize',
        'estado': 'pendiente',
        'firma': firma,
        'total': len(acciones),
        'acciones': acciones,
    }
    ruta = destino / f'{identificador}.json'
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    return ruta


def _invocar(args: list[str], tmp_path: Path) -> object:
    return EJECUTOR.invoke(app, args, env=_entorno(tmp_path))


def test_catalogo_declara_version_por_accion():
    # Toda accion del catalogo declara una version que el ejecutor acepta.
    for capacidad in capabilities.listar_capacidades():
        assert isinstance(capacidad['contrato_version'], int)
        for nombre, definicion in capacidad['actions'].items():
            assert isinstance(definicion.get('contrato_version'), int), (
                f'{capacidad["name"]} {nombre} sin contrato_version'
            )
            assert definicion['contrato_version'] in capabilities.CONTRATOS_SOPORTADOS
            assert (
                capabilities.version_contrato_de(capacidad['name'], nombre)
                == definicion['contrato_version']
            )


def test_schema_publica_la_version_de_cada_accion():
    # Cada combinacion declarada responde con la version de su accion, no la global.
    for capacidad in capabilities.listar_capacidades():
        for nombre, definicion in capacidad['actions'].items():
            resultado = EJECUTOR.invoke(app, ['schema', capacidad['name'], nombre])
            assert resultado.exit_code == 0, resultado.stdout
            datos = json.loads(resultado.stdout)
            assert datos['version_contrato'] == definicion['contrato_version']


def test_schema_rechaza_accion_con_contrato_desconocido(monkeypatch):
    # Una accion que declara una version no soportada se rechaza con codigo estable.
    definicion = capabilities.obtener_capacidad('trim')['actions']['escanear']
    monkeypatch.setitem(definicion, 'contrato_version', 99)
    resultado = EJECUTOR.invoke(app, ['schema', 'trim', 'escanear'])
    assert resultado.exit_code == 2
    assert 'CONTRATO_VERSION_NO_SOPORTADA' in resultado.stdout


def test_version_del_paquete_no_es_la_version_del_contrato():
    # La version instalada y la del contrato se publican por caminos distintos.
    paquete = version_paquete('devkit')
    assert paquete != str(capabilities.VERSION_CONTRATO)
    version = EJECUTOR.invoke(app, ['--version'])
    assert version.exit_code == 0
    assert version.stdout.strip() == f'devkit {paquete}'
    resultado = EJECUTOR.invoke(app, ['capabilities'])
    assert resultado.exit_code == 0
    datos = json.loads(resultado.stdout)
    assert datos['version_contrato'] == capabilities.VERSION_CONTRATO
    assert isinstance(datos['version_contrato'], int)
    assert datos['contratos_soportados'] == list(capabilities.CONTRATOS_SOPORTADOS)


def test_migrate_plan_v1_a_v2_es_idempotente(tmp_path):
    # La primera migracion reescribe y la segunda no toca ni el archivo ni el journal.
    accion, _, _ = _accion_mover(tmp_path)
    ruta = _manifiesto_v1(tmp_path, [accion])
    resultado = _invocar(['migrate', str(ruta), '--tipo', 'plan'], tmp_path)
    assert resultado.exit_code == 0, resultado.stdout
    datos = json.loads(resultado.stdout)
    assert datos['version_origen'] == 1
    assert datos['version_destino'] == 2
    assert datos['migrado'] is True
    assert 'migrado_desde' in ruta.read_text(encoding='utf-8')
    lineas_primera = _journal_lineas()
    contenido = ruta.read_bytes()

    segundo = _invocar(['migrate', str(ruta), '--tipo', 'plan'], tmp_path)
    assert segundo.exit_code == 0, segundo.stdout
    repetido = json.loads(segundo.stdout)
    assert repetido['version_origen'] == 2
    assert repetido['version_destino'] == 2
    assert repetido['migrado'] is False
    assert ruta.read_bytes() == contenido
    assert _journal_lineas() == lineas_primera


def test_migrate_plan_migrado_equivale_a_uno_nuevo(tmp_path):
    # El plan migrado declara la misma politica, ids y dependencias que uno recien guardado.
    accion, _, _ = _accion_mover(tmp_path)
    ruta_v1 = _manifiesto_v1(tmp_path, [accion])
    resultado = _invocar(['migrate', str(ruta_v1), '--tipo', 'plan'], tmp_path)
    assert resultado.exit_code == 0, resultado.stdout
    migrado = safety.cargar_plan(ruta_v1)
    ruta_nueva = _manifiesto_v2(tmp_path, [dict(accion)], identificador='plan-nuevo')
    nuevo = safety.cargar_plan(ruta_nueva)
    for clave in ('schema_version', 'contrato_version', 'politica', 'total'):
        assert migrado[clave] == nuevo[clave]
    for vieja, reciente in zip(migrado['acciones'], nuevo['acciones'], strict=True):
        assert vieja['id'] == reciente['id']
        assert vieja['depende_de'] == reciente['depende_de']
        assert vieja['origen'] == reciente['origen']
        assert vieja['destino'] == reciente['destino']


def test_migrate_plan_con_contrato_desconocido_no_escribe(tmp_path):
    # Un manifiesto v2 con un contrato que el codigo no entiende no se toca.
    accion, _, _ = _accion_mover(tmp_path)
    ruta = _manifiesto_v2(tmp_path, [accion])
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    datos['contrato_version'] = 99
    datos['firma'] = safety.firmar_plan(
        datos['acciones'],
        schema_version=2,
        plan_id=datos['plan_id'],
        workspace_id=datos['workspace_id'],
        workspace_root=datos['workspace_root'],
        herramienta=datos['herramienta'],
        contrato_version=99,
        requisitos=datos['politica'],
    )
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    antes = ruta.read_bytes()
    resultado = _invocar(['migrate', str(ruta), '--tipo', 'plan'], tmp_path)
    assert resultado.exit_code == 2
    assert 'CONTRATO_VERSION_NO_SOPORTADA' in resultado.stdout
    assert ruta.read_bytes() == antes


def test_migrate_plan_rechaza_desde_inesperado(tmp_path):
    # La version de origen pedida se compara antes de escribir.
    accion, _, _ = _accion_mover(tmp_path)
    ruta = _manifiesto_v1(tmp_path, [accion])
    antes = ruta.read_bytes()
    resultado = _invocar(
        ['migrate', str(ruta), '--tipo', 'plan', '--desde', '2'], tmp_path
    )
    assert resultado.exit_code == 2
    assert 'VERSION_ORIGEN_INESPERADA' in resultado.stdout
    assert ruta.read_bytes() == antes


def test_migrate_plan_rechaza_hasta_no_soportada(tmp_path):
    # Pedir una version de destino que no existe no produce cambios.
    accion, _, _ = _accion_mover(tmp_path)
    ruta = _manifiesto_v1(tmp_path, [accion])
    antes = ruta.read_bytes()
    resultado = _invocar(
        ['migrate', str(ruta), '--tipo', 'plan', '--hasta', '3'], tmp_path
    )
    assert resultado.exit_code == 2
    assert 'VERSION_DESTINO_NO_SOPORTADA' in resultado.stdout
    assert ruta.read_bytes() == antes


def test_migrate_config_sin_version_anade_la_actual(tmp_path):
    # Una configuracion anterior conserva sus valores y pasa a declarar su version.
    ruta = tmp_path / 'config.toml'
    ruta.write_text(
        'retencion_dias = 60\n'
        '[storage]\n'
        f'state = "{tmp_path.as_posix()}/datos"\n',
        encoding='utf-8',
    )
    resultado = _invocar(['migrate', str(ruta), '--tipo', 'config'], tmp_path)
    assert resultado.exit_code == 0, resultado.stdout
    datos = json.loads(resultado.stdout)
    assert datos['version_origen'] == 0
    assert datos['version_destino'] == 1
    assert datos['migrado'] is True
    texto = ruta.read_text(encoding='utf-8')
    assert texto.startswith('version = 1\n')
    assert tomllib.loads(texto)['retencion_dias'] == 60


def test_migrate_config_idempotente_no_toca_journal(tmp_path):
    # La segunda ejecucion no reescribe la configuracion ni agrega hitos.
    ruta = tmp_path / 'config.toml'
    ruta.write_text('retencion_dias = 60\n', encoding='utf-8')
    primera = _invocar(['migrate', str(ruta), '--tipo', 'config'], tmp_path)
    assert primera.exit_code == 0, primera.stdout
    linea_primera = _journal_lineas()
    contenido = ruta.read_bytes()

    segunda = _invocar(['migrate', str(ruta), '--tipo', 'config'], tmp_path)
    assert segunda.exit_code == 0, segunda.stdout
    repetido = json.loads(segunda.stdout)
    assert repetido['migrado'] is False
    assert ruta.read_bytes() == contenido
    assert _journal_lineas() == linea_primera


def test_migrate_config_con_version_desconocida_no_escribe(tmp_path):
    # Una configuracion de una version posterior no se degrada ni se toca.
    ruta = tmp_path / 'config.toml'
    ruta.write_text('version = 7\nretencion_dias = 60\n', encoding='utf-8')
    antes = ruta.read_bytes()
    resultado = _invocar(['migrate', str(ruta), '--tipo', 'config'], tmp_path)
    assert resultado.exit_code == 2
    assert 'CONFIG_VERSION_NO_SOPORTADA' in resultado.stdout
    assert ruta.read_bytes() == antes


def test_migrate_tipo_desconocido_no_toca_el_archivo(tmp_path):
    # El tipo se exige antes de leer o escribir el archivo.
    ruta = tmp_path / 'datos.txt'
    ruta.write_text('sin formato conocido\n', encoding='utf-8')
    antes = ruta.read_bytes()
    resultado = _invocar(['migrate', str(ruta), '--tipo', 'otro'], tmp_path)
    assert resultado.exit_code == 2
    assert 'TIPO_NO_SOPORTADO' in resultado.stdout
    assert ruta.read_bytes() == antes


def test_migrate_ruta_inexistente_falla_con_codigo_estable(tmp_path):
    # Una ruta que no existe se reporta sin abrir el journal.
    resultado = _invocar(
        ['migrate', str(tmp_path / 'no-existe.json'), '--tipo', 'plan'], tmp_path
    )
    assert resultado.exit_code == 2
    assert 'RUTA_NO_ENCONTRADA' in resultado.stdout
    assert _journal_lineas() == []


def test_config_con_version_desconocida_no_carga(tmp_path, monkeypatch):
    # El cargador rechaza una configuracion que declara una version no soportada.
    carpeta = tmp_path / 'config'
    carpeta.mkdir()
    monkeypatch.setenv('DEVKIT_CONFIG', str(carpeta))
    (carpeta / 'config.toml').write_text('version = 7\n', encoding='utf-8')
    with pytest.raises(ErrorConfiguracion, match='CONFIG_VERSION_NO_SOPORTADA'):
        modulo_config.cargar_configuracion()
