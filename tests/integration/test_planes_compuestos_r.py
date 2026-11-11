# Pruebas de regresion del bloque R: planes compuestos, manifiesto v2 y migracion.
import json
import shutil
from pathlib import Path

import pytest

from devkit.core import capabilities, politica, runlog, safety, workspace
from devkit.errors import ErrorIntegridad

POLITICA_ORGANIZE = politica.derivar('organize', 'aplicar', confirmada=True)


def _accion_mover(
    base: Path,
    nombre: str,
    identificador: str | None = None,
    depende_de: list[str] | None = None,
) -> tuple[dict, Path, Path]:
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
    if identificador is not None:
        accion['id'] = identificador
    if depende_de is not None:
        accion['depende_de'] = depende_de
    return accion, origen, destino


def _manifiesto(
    base: Path,
    acciones: list[dict],
    herramienta: str = 'organize',
    identificador: str = 'plan-r',
) -> Path:
    # Guarda un manifiesto v2 firmado y ligado al workspace de la raiz.
    return safety.guardar_plan(
        identificador,
        herramienta,
        acciones,
        destino_dir=base / 'planes',
        workspace_id=workspace.workspace_id(base),
        workspace_root=str(base),
    )


def _manifiesto_v1(
    base: Path,
    acciones: list[dict],
    herramienta: str = 'organize',
    identificador: str = 'plan-r-v1',
) -> Path:
    # Guarda un manifiesto de la version anterior con una firma que sigue siendo valida.
    destino = base / 'planes'
    destino.mkdir(parents=True, exist_ok=True)
    ident = workspace.workspace_id(base)
    firma = safety.firmar_plan(
        acciones,
        schema_version=1,
        plan_id=identificador,
        workspace_id=ident,
        workspace_root=str(base),
        herramienta=herramienta,
    )
    datos = {
        'schema_version': 1,
        'plan_id': identificador,
        'id_ejecucion': identificador,
        'workspace_id': ident,
        'workspace_root': str(base),
        'herramienta': herramienta,
        'estado': 'pendiente',
        'firma': firma,
        'total': len(acciones),
        'acciones': acciones,
    }
    ruta = destino / f'{identificador}.json'
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    return ruta


def _hitos(ruta_plan: Path) -> list[dict]:
    return runlog.hitos_del_plan(ruta_plan.stem)


def test_ciclo_de_dependencias_se_rechaza_antes_de_escribir(tmp_path):
    # Un ciclo no puede producir un manifiesto ni crear la carpeta de planes.
    primera, _, _ = _accion_mover(
        tmp_path, 'uno.txt', identificador='a001', depende_de=['a002']
    )
    segunda, _, _ = _accion_mover(
        tmp_path, 'dos.txt', identificador='a002', depende_de=['a001']
    )
    with pytest.raises(ErrorIntegridad, match='CICLO_DE_DEPENDENCIAS'):
        _manifiesto(tmp_path, [primera, segunda])
    assert not (tmp_path / 'planes').exists()


def test_dependencia_desconocida_se_rechaza(tmp_path):
    # Una dependencia que no apunta a ninguna accion se detecta antes de escribir.
    accion, _, _ = _accion_mover(
        tmp_path, 'uno.txt', identificador='a001', depende_de=['a999']
    )
    with pytest.raises(ErrorIntegridad, match='DEPENDENCIA_DESCONOCIDA'):
        _manifiesto(tmp_path, [accion])


def test_id_duplicado_se_rechaza(tmp_path):
    # Los identificadores son la identidad de la accion dentro del plan.
    primera, _, _ = _accion_mover(tmp_path, 'uno.txt', identificador='a001')
    segunda, _, _ = _accion_mover(tmp_path, 'dos.txt', identificador='a001')
    with pytest.raises(ErrorIntegridad, match='ACCION_DUPLICADA'):
        _manifiesto(tmp_path, [primera, segunda])


def test_manifiesto_v2_ordena_por_dependencias_y_declara_politica(tmp_path):
    # El manifiesto se escribe en orden topologico y declara la autorizacion vigente.
    primera, _, _ = _accion_mover(tmp_path, 'uno.txt', identificador='a001')
    segunda, _, _ = _accion_mover(
        tmp_path, 'dos.txt', identificador='a002', depende_de=['a001']
    )
    ruta_plan = _manifiesto(tmp_path, [segunda, primera])
    datos = safety.cargar_plan(ruta_plan)
    assert datos['schema_version'] == 2
    assert datos['contrato_version'] == capabilities.VERSION_CONTRATO
    assert [a['id'] for a in datos['acciones']] == ['a001', 'a002']
    assert datos['politica'] == politica.requerimientos('organize', 'aplicar').como_dict()


def test_ids_se_asignan_en_orden_declarado_si_faltan(tmp_path):
    # Un plan nuevo sin ids recibe identificadores estables a001, a002.
    primera, _, _ = _accion_mover(tmp_path, 'uno.txt')
    segunda, _, _ = _accion_mover(tmp_path, 'dos.txt')
    ruta_plan = _manifiesto(tmp_path, [primera, segunda])
    datos = safety.cargar_plan(ruta_plan)
    assert [a['id'] for a in datos['acciones']] == ['a001', 'a002']
    assert all(a['depende_de'] == [] for a in datos['acciones'])


def test_fallo_de_predecesora_omite_dependiente_y_deja_parcial(tmp_path, monkeypatch):
    # La accion dependiente no se intenta y el plan queda parcial con su motivo en el journal.
    primera, origen_uno, destino_uno = _accion_mover(
        tmp_path, 'uno.txt', identificador='a001'
    )
    segunda, origen_dos, destino_dos = _accion_mover(
        tmp_path, 'dos.txt', identificador='a002', depende_de=['a001']
    )
    ruta_plan = _manifiesto(tmp_path, [primera, segunda])

    def falla_la_primera(accion):
        if accion.get('id') == 'a001':
            raise OSError('fallo simulado')
        raise AssertionError('la dependiente no debia ejecutarse')

    monkeypatch.setattr(safety, '_ejecutar_accion', falla_la_primera)
    resultado = safety.aplicar_manifiesto(
        ruta_plan, 'organize', espacio_trabajo=str(tmp_path),
        politica=POLITICA_ORGANIZE,
    )
    assert resultado['codigo'] == 2
    assert resultado['estado_plan'] == 'parcial'
    assert [f['origen'] for f in resultado['fallidos']] == [str(origen_uno)]
    assert [str(a['origen']) for a in resultado['omitidos']] == [str(origen_dos)]
    omitidos = [h for h in _hitos(ruta_plan) if h['estado'] == 'OMITIDO']
    assert omitidos
    assert omitidos[0]['codigo_error'] == 'DEPENDENCIA_FALLIDA'
    assert origen_uno.exists() and not destino_uno.exists()
    assert origen_dos.exists() and not destino_dos.exists()


def test_predecesora_omitida_omite_dependiente(tmp_path):
    # Omitir la primera accion arrastra a la segunda aunque su origen siga intacto.
    primera, _, _ = _accion_mover(tmp_path, 'uno.txt', identificador='a001')
    segunda, _, _ = _accion_mover(
        tmp_path, 'dos.txt', identificador='a002', depende_de=['a001']
    )
    ruta_plan = _manifiesto(tmp_path, [primera, segunda])
    resultado = safety.aplicar_manifiesto(
        ruta_plan, 'organize', espacio_trabajo=str(tmp_path),
        autorizar=lambda accion: False, politica=POLITICA_ORGANIZE,
    )
    assert resultado['estado_plan'] == 'parcial'
    assert len(resultado['omitidos']) == 2
    codigos = {
        h['codigo_error'] for h in _hitos(ruta_plan) if h['estado'] == 'OMITIDO'
    }
    assert 'DEPENDENCIA_OMITIDA' in codigos


def test_manifiesto_v1_se_migra_conservando_acciones_y_firma(tmp_path):
    # La migracion reescribe, vuelve a firmar y conserva origen y destino.
    accion, origen, destino = _accion_mover(tmp_path, 'uno.txt')
    ruta_plan = _manifiesto_v1(tmp_path, [accion])
    cargado = safety.cargar_plan(ruta_plan)
    assert cargado['schema_version'] == 1
    assert cargado['acciones'][0]['id'] == 'a001'
    assert cargado['acciones'][0]['depende_de'] == []

    safety.migrar_plan(ruta_plan)
    datos = json.loads(ruta_plan.read_text(encoding='utf-8'))
    assert datos['schema_version'] == 2
    assert datos['contrato_version'] == capabilities.VERSION_CONTRATO
    assert datos['migrado_desde'] == 1
    assert datos['acciones'][0]['origen'] == str(origen)
    assert datos['acciones'][0]['destino'] == str(destino)
    assert safety.cargar_plan(ruta_plan)['schema_version'] == 2

    antes = ruta_plan.read_text(encoding='utf-8')
    safety.migrar_plan(ruta_plan)
    assert ruta_plan.read_text(encoding='utf-8') == antes


def test_manifiesto_v2_en_otro_workspace_falla_por_identidad(tmp_path):
    # Copiar el manifiesto a otro workspace no se confunde con una version distinta.
    raiz_a = tmp_path / 'a'
    raiz_b = tmp_path / 'b'
    raiz_a.mkdir()
    raiz_b.mkdir()
    workspace.workspace_id(raiz_b)
    ruta_plan = _manifiesto(raiz_a, [], identificador='plan-vacio')
    copia = raiz_b / 'planes' / ruta_plan.name
    copia.parent.mkdir()
    shutil.copyfile(ruta_plan, copia)
    with pytest.raises(ErrorIntegridad) as contexto:
        safety.aplicar_manifiesto(
            copia, 'organize', espacio_trabajo=str(raiz_b),
            politica=POLITICA_ORGANIZE,
        )
    mensaje = str(contexto.value)
    assert 'workspace' in mensaje
    assert 'schema_version' not in mensaje


def test_schema_version_desconocida_se_rechaza_con_codigo_estable(tmp_path):
    # Una version de manifiesto que el ejecutor no entiende no se intenta interpretar.
    ruta = tmp_path / 'plan.json'
    ruta.write_text(
        json.dumps(
            {'schema_version': 99, 'herramienta': 'organize', 'acciones': [], 'firma': 'x'}
        ),
        encoding='utf-8',
    )
    with pytest.raises(ErrorIntegridad, match='MANIFEST_SCHEMA_VERSION_NO_SOPORTADA'):
        safety.cargar_plan(ruta)


def test_contrato_version_desconocida_se_rechaza(tmp_path):
    # La version de contrato se valida aparte de la version del manifiesto.
    accion, _, _ = _accion_mover(tmp_path, 'uno.txt')
    ruta_plan = _manifiesto(tmp_path, [accion])
    datos = json.loads(ruta_plan.read_text(encoding='utf-8'))
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
    ruta_plan.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(ErrorIntegridad, match='CONTRATO_VERSION_NO_SOPORTADA'):
        safety.cargar_plan(ruta_plan)


def test_politica_requerida_desactualizada_se_rechaza(tmp_path):
    # Un manifiesto que declara compuertas distintas a las del catalogo no se aplica.
    accion, _, _ = _accion_mover(tmp_path, 'uno.txt')
    ruta_plan = _manifiesto(tmp_path, [accion])
    datos = json.loads(ruta_plan.read_text(encoding='utf-8'))
    datos['politica']['compuertas'] = []
    datos['firma'] = safety.firmar_plan(
        datos['acciones'],
        schema_version=2,
        plan_id=datos['plan_id'],
        workspace_id=datos['workspace_id'],
        workspace_root=datos['workspace_root'],
        herramienta=datos['herramienta'],
        contrato_version=datos['contrato_version'],
        requisitos=datos['politica'],
    )
    ruta_plan.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(ErrorIntegridad, match='POLITICA_REQUERIDA_DESACTUALIZADA'):
        safety.cargar_plan(ruta_plan)


def test_manifiesto_v2_sin_politica_se_rechaza(tmp_path):
    # La politica requerida forma parte del contrato del manifiesto v2.
    accion, _, _ = _accion_mover(tmp_path, 'uno.txt')
    ruta_plan = _manifiesto(tmp_path, [accion])
    datos = json.loads(ruta_plan.read_text(encoding='utf-8'))
    del datos['politica']
    datos['firma'] = safety.firmar_plan(
        datos['acciones'],
        schema_version=2,
        plan_id=datos['plan_id'],
        workspace_id=datos['workspace_id'],
        workspace_root=datos['workspace_root'],
        herramienta=datos['herramienta'],
        contrato_version=datos['contrato_version'],
        requisitos=None,
    )
    ruta_plan.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(ErrorIntegridad, match='POLITICA_REQUERIDA_DESACTUALIZADA'):
        safety.cargar_plan(ruta_plan)


def test_accion_sin_id_en_manifiesto_v2_se_rechaza(tmp_path):
    # El ejecutor no inventa identidades para un manifiesto que se declara v2.
    accion, _, _ = _accion_mover(tmp_path, 'uno.txt', identificador='a001')
    ruta_plan = _manifiesto(tmp_path, [accion])
    datos = json.loads(ruta_plan.read_text(encoding='utf-8'))
    del datos['acciones'][0]['id']
    datos['firma'] = safety.firmar_plan(
        datos['acciones'],
        schema_version=2,
        plan_id=datos['plan_id'],
        workspace_id=datos['workspace_id'],
        workspace_root=datos['workspace_root'],
        herramienta=datos['herramienta'],
        contrato_version=datos['contrato_version'],
        requisitos=datos['politica'],
    )
    ruta_plan.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(ErrorIntegridad, match='ACCION_SIN_ID'):
        safety.cargar_plan(ruta_plan)


def test_simulacion_completa_omite_dependientes(tmp_path):
    # Simular recorre el grafo y distingue el fallo propio de la dependencia que no correra.
    fallida = {
        'tipo': 'mover',
        'id': 'a001',
        'origen': str(tmp_path / 'no-existe.txt'),
        'destino': str(tmp_path / 'destino' / 'no-existe.txt'),
        'tamano': 1,
    }
    dependiente, _, _ = _accion_mover(
        tmp_path, 'dos.txt', identificador='a002', depende_de=['a001']
    )
    independiente, _, _ = _accion_mover(tmp_path, 'tres.txt', identificador='a003')
    ruta_plan = _manifiesto(tmp_path, [fallida, dependiente, independiente])
    resultado = safety.simular_manifiesto(
        ruta_plan, 'organize', espacio_trabajo=str(tmp_path),
        politica=POLITICA_ORGANIZE,
    )
    assert [f['origen'] for f in resultado['fallidos']] == [str(tmp_path / 'no-existe.txt')]
    assert [a['id'] for a in resultado['omitidos']] == ['a002']
    assert [a['id'] for a in resultado['movidos']] == ['a003']


def test_reconciliacion_propaga_dependencia_omitida(tmp_path):
    # El estado reconciliado de una predecesora omitida se propaga a su dependiente.
    primera, origen_uno, destino_uno = _accion_mover(
        tmp_path, 'uno.txt', identificador='a001'
    )
    segunda, _, _ = _accion_mover(
        tmp_path, 'dos.txt', identificador='a002', depende_de=['a001']
    )
    ruta_plan = _manifiesto(tmp_path, [primera, segunda])
    runlog.registrar_hito(
        'r-reconciliacion', 'organize', 'accion', 'OMITIDO', 'sin autorizar',
        origen=str(origen_uno), destino=str(destino_uno),
        id_plan=ruta_plan.stem, nivel='accion',
    )
    reconciliacion = safety.reconciliar_plan(ruta_plan, str(tmp_path))
    por_id = {fila['id']: fila for fila in reconciliacion['resultados']}
    assert por_id['a001']['estado'] == 'OMITIDA'
    assert por_id['a002']['estado'] == 'OMITIDA'
    assert 'dependencia omitida: a001' in por_id['a002']['motivo']
