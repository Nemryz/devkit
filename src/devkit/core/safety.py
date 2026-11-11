# Punto unico donde se comprueba si una accion puede escribir en disco.
from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from devkit.core import capabilities, runlog
from devkit.core import politica as modulo_politica
from devkit.core import workspace as modulo_workspace
from devkit.errors import ErrorIntegridad, ErrorPolitica, ErrorSoloLectura

VALORES_ACTIVOS = {'1', 'true', 'si', 'yes', 'on'}


def modo_solo_lectura() -> bool:
    # Lee la variable global que bloquea cualquier escritura del toolkit.
    valor = os.environ.get('DEVKIT_READONLY', '')
    return valor.strip().lower() in VALORES_ACTIVOS


def verificar_escritura(accion: str) -> None:
    # Toda herramienta que mueva o borre pasa por aqui antes de tocar el disco.
    if modo_solo_lectura():
        raise ErrorSoloLectura(f'el modo de solo lectura impide {accion}')


# Planes persistentes con firma, validacion del arbol y estados del manifiesto.


CODIGO_MANIFEST_SCHEMA_VERSION_MISSING = 'MANIFEST_SCHEMA_VERSION_MISSING'
CODIGO_MANIFEST_SCHEMA_VERSION_NO_SOPORTADA = 'MANIFEST_SCHEMA_VERSION_NO_SOPORTADA'
CODIGO_CONTRATO_VERSION_NO_SOPORTADA = 'CONTRATO_VERSION_NO_SOPORTADA'
CODIGO_POLITICA_REQUERIDA_DESACTUALIZADA = 'POLITICA_REQUERIDA_DESACTUALIZADA'
CODIGO_ACCION_DUPLICADA = 'ACCION_DUPLICADA'
CODIGO_ACCION_SIN_ID = 'ACCION_SIN_ID'
CODIGO_DEPENDENCIA_DESCONOCIDA = 'DEPENDENCIA_DESCONOCIDA'
CODIGO_DEPENDENCIA_INVALIDA = 'DEPENDENCIA_INVALIDA'
CODIGO_CICLO_DE_DEPENDENCIAS = 'CICLO_DE_DEPENDENCIAS'
CODIGO_DEPENDENCIA_FALLIDA = 'DEPENDENCIA_FALLIDA'
CODIGO_DEPENDENCIA_OMITIDA = 'DEPENDENCIA_OMITIDA'
SCHEMA_VERSION_ACTUAL = 2
SCHEMAS_SOPORTADOS = (1, 2)
CONTRATOS_SOPORTADOS = (capabilities.VERSION_CONTRATO,)


def firmar_plan(
    acciones: list[dict],
    schema_version: int = SCHEMA_VERSION_ACTUAL,
    plan_id: str = '',
    workspace_id: str = '',
    workspace_root: str = '',
    herramienta: str = '',
    contrato_version: int | None = None,
    requisitos: dict | None = None,
) -> str:
    # Firma de integridad accidental, no de autenticidad, sobre todo el contenido del manifiesto.
    payload = {
        'schema_version': schema_version,
        'plan_id': plan_id,
        'workspace_id': workspace_id,
        'workspace_root': workspace_root,
        'herramienta': herramienta,
        'acciones': acciones,
    }
    # La version 1 conserva el payload antiguo para seguir verificando manifiestos existentes.
    if schema_version >= 2:
        payload['contrato_version'] = contrato_version
        payload['politica'] = requisitos
    texto = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def _id_accion(indice: int) -> str:
    # Genera identificadores estables y legibles para acciones sin id explicito.
    return f'a{indice + 1:03d}'


def _normalizar_acciones(acciones: list[dict], exigir_id: bool = False) -> list[dict]:
    # Copia las acciones y completa id y dependencias sin inventar las que ya existen.
    normalizadas = []
    vistos = set()
    for indice, accion in enumerate(acciones):
        if not isinstance(accion, dict):
            raise ErrorIntegridad(
                f'{CODIGO_ACCION_SIN_ID}: la accion {indice} no es un objeto'
            )
        copia = dict(accion)
        identificador = str(copia.get('id', '')).strip()
        if not identificador:
            if exigir_id:
                raise ErrorIntegridad(
                    f'{CODIGO_ACCION_SIN_ID}: la accion {indice} no declara id'
                )
            identificador = _id_accion(indice)
        if identificador in vistos:
            raise ErrorIntegridad(
                f'{CODIGO_ACCION_DUPLICADA}: el id {identificador} aparece mas de una vez'
            )
        vistos.add(identificador)
        dependencias = copia.get('depende_de', [])
        if dependencias is None:
            dependencias = []
        if not isinstance(dependencias, (list, tuple)):
            raise ErrorIntegridad(
                f'{CODIGO_DEPENDENCIA_INVALIDA}: {identificador} no declara '
                f'una lista de dependencias'
            )
        copia['id'] = identificador
        copia['depende_de'] = [str(dependencia) for dependencia in dependencias]
        normalizadas.append(copia)
    return normalizadas


def _indices_por_id(acciones: list[dict]) -> dict[str, int]:
    # Relaciona cada id con su posicion para validar el grafo sin recorrerlo de nuevo.
    indices: dict[str, int] = {}
    for indice, accion in enumerate(acciones):
        identificador = str(accion.get('id', ''))
        if identificador in indices:
            raise ErrorIntegridad(
                f'{CODIGO_ACCION_DUPLICADA}: el id {identificador} aparece mas de una vez'
            )
        indices[identificador] = indice
    return indices


def orden_topologico(acciones: list[dict]) -> list[dict]:
    # Ordena las acciones respetando dependencias y conservando el orden original entre iguales.
    indices = _indices_por_id(acciones)
    dependencias: dict[str, list[str]] = {}
    for accion in acciones:
        identificador = str(accion.get('id', ''))
        lista = [str(d) for d in accion.get('depende_de', [])]
        for dependencia in lista:
            if dependencia not in indices:
                raise ErrorIntegridad(
                    f'{CODIGO_DEPENDENCIA_DESCONOCIDA}: {identificador} depende de '
                    f'{dependencia}, que no existe'
                )
        dependencias[identificador] = lista
    # Kahn con una cola ordenada por posicion para que el resultado sea reproducible.
    pendientes = {
        identificador: set(lista) for identificador, lista in dependencias.items()
    }
    ordenados: list[str] = []
    while pendientes:
        disponibles = sorted(
            (identificador for identificador, faltan in pendientes.items() if not faltan),
            key=lambda identificador: indices[identificador],
        )
        if not disponibles:
            raise ErrorIntegridad(
                f'{CODIGO_CICLO_DE_DEPENDENCIAS}: el plan contiene un ciclo entre '
                + ', '.join(sorted(pendientes))
            )
        for identificador in disponibles:
            ordenados.append(identificador)
            del pendientes[identificador]
        for faltan in pendientes.values():
            faltan.difference_update(disponibles)
    return [acciones[indices[identificador]] for identificador in ordenados]


def _orden_de_ejecucion(acciones: list[dict]) -> list[int]:
    # Traduce el orden topologico a posiciones del manifiesto para conservar sus indices.
    indices = _indices_por_id(acciones)
    ordenadas = orden_topologico(acciones)
    return [indices[str(accion.get('id', ''))] for accion in ordenadas]


def _requerimientos_del_catalogo(herramienta: str) -> modulo_politica.Requerimientos:
    # Deriva del catalogo lo que un plan de aplicar necesita antes de existir la decision.
    return modulo_politica.requerimientos(herramienta, 'aplicar')


def _validar_tipos_declarados(
    requisitos: modulo_politica.Requerimientos, acciones: list[dict]
) -> None:
    # Un manifiesto no puede declarar una politica que no cubra sus propios tipos de accion.
    for accion in acciones:
        tipo = str(accion.get('tipo', 'papelera'))
        if tipo not in requisitos.tipos:
            raise ErrorPolitica(
                'ACCION_FUERA_DE_POLITICA: '
                + tipo
                + ' no esta declarada para '
                + requisitos.capacidad
            )


def _escribir_manifiesto(ruta: Path, datos: dict) -> None:
    # Reescribe el manifiesto mediante un temporal para no dejarlo a medias si el proceso muere.
    temporal = ruta.with_name(ruta.name + '.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporal, ruta)


def _verificar_firma(datos: dict, ruta: Path, schema_version: int) -> None:
    # Verifica la firma del payload exacto que declara la version del manifiesto.
    firma_esperada = firmar_plan(
        datos.get('acciones', []),
        schema_version=schema_version,
        plan_id=str(datos.get('plan_id') or datos.get('id_ejecucion') or ruta.stem),
        workspace_id=str(datos.get('workspace_id', '')),
        workspace_root=str(datos.get('workspace_root', '')),
        herramienta=str(datos.get('herramienta', '')),
        contrato_version=datos.get('contrato_version'),
        requisitos=datos.get('politica'),
    )
    if firma_esperada != datos.get('firma'):
        raise ErrorIntegridad(f'el plan {ruta} fue modificado, firma no coincide')


def _requisitos_del_manifiesto(
    datos: dict, ruta: Path
) -> modulo_politica.Requerimientos:
    # Comprueba que el manifiesto v2 declara la autorizacion vigente del catalogo.
    bruto = datos.get('politica')
    if not isinstance(bruto, dict):
        raise ErrorIntegridad(
            f'{CODIGO_POLITICA_REQUERIDA_DESACTUALIZADA}: el plan {ruta} no declara politica'
        )
    try:
        declarados = modulo_politica.Requerimientos.desde_dict(bruto)
    except ValueError as fallo:
        raise ErrorIntegridad(
            f'{CODIGO_POLITICA_REQUERIDA_DESACTUALIZADA}: {fallo}'
        ) from fallo
    herramienta = str(datos.get('herramienta', ''))
    try:
        actuales = _requerimientos_del_catalogo(herramienta)
    except ErrorPolitica as fallo:
        raise ErrorIntegridad(
            f'{CODIGO_POLITICA_REQUERIDA_DESACTUALIZADA}: {fallo}'
        ) from fallo
    if declarados != actuales:
        raise ErrorIntegridad(
            f'{CODIGO_POLITICA_REQUERIDA_DESACTUALIZADA}: el plan {ruta} declara '
            f'requerimientos de {declarados.capacidad} {declarados.accion} que ya no '
            f'coinciden con el catalogo'
        )
    return declarados


def guardar_plan(
    id_ejecucion: str,
    herramienta: str,
    acciones: list[dict],
    destino_dir: Path | None = None,
    workspace_id: str = '',
    workspace_root: str = '',
) -> Path:
    # Guarda el manifiesto v2 del plan para aplicar despues sin reescanear.
    from devkit.core import paths

    requisitos = _requerimientos_del_catalogo(herramienta)
    normalizadas = _normalizar_acciones(acciones)
    _validar_tipos_declarados(requisitos, normalizadas)
    ordenadas = orden_topologico(normalizadas)
    base = destino_dir or (paths.directorio_planes())
    base.mkdir(parents=True, exist_ok=True)
    firma = firmar_plan(
        ordenadas,
        schema_version=SCHEMA_VERSION_ACTUAL,
        plan_id=id_ejecucion,
        workspace_id=workspace_id,
        workspace_root=workspace_root,
        herramienta=herramienta,
        contrato_version=capabilities.VERSION_CONTRATO,
        requisitos=requisitos.como_dict(),
    )
    datos = {
        'schema_version': SCHEMA_VERSION_ACTUAL,
        'contrato_version': capabilities.VERSION_CONTRATO,
        'plan_id': id_ejecucion,
        'id_ejecucion': id_ejecucion,
        'workspace_id': workspace_id,
        'workspace_root': workspace_root,
        'herramienta': herramienta,
        'fecha': datetime.now(UTC).isoformat(),
        'estado': 'pendiente',
        'politica': requisitos.como_dict(),
        'firma': firma,
        'total': len(ordenadas),
        'acciones': ordenadas,
    }
    ruta = base / f'{id_ejecucion}.json'
    _escribir_manifiesto(ruta, datos)
    return ruta


def cargar_plan(ruta: Path) -> dict:
    # Carga un plan persistido, valida su firma y normaliza la version 1 en memoria.
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except OSError as fallo:
        raise ErrorIntegridad(f'no se pudo leer el plan {ruta} porque {fallo}') from fallo
    except json.JSONDecodeError as fallo:
        raise ErrorIntegridad(f'el plan {ruta} no es JSON valido porque {fallo}') from fallo
    schema_version = datos.get('schema_version')
    if schema_version is None:
        raise ErrorIntegridad(
            f'{CODIGO_MANIFEST_SCHEMA_VERSION_MISSING}: el manifiesto no declara schema_version. '
            f'No se ejecuto ninguna accion. Utiliza un manifiesto compatible o genera uno nuevo.'
        )
    if schema_version not in SCHEMAS_SOPORTADOS:
        raise ErrorIntegridad(
            f'{CODIGO_MANIFEST_SCHEMA_VERSION_NO_SOPORTADA}: el manifiesto declara '
            f'schema_version {schema_version}, no soportada. No se ejecuto ninguna accion.'
        )
    if schema_version >= 2:
        contrato = datos.get('contrato_version')
        if contrato not in CONTRATOS_SOPORTADOS:
            raise ErrorIntegridad(
                f'{CODIGO_CONTRATO_VERSION_NO_SOPORTADA}: el manifiesto declara '
                f'contrato_version {contrato}, no soportada. No se ejecuto ninguna accion.'
            )
        _requisitos_del_manifiesto(datos, ruta)
    _verificar_firma(datos, ruta, schema_version)
    acciones = _normalizar_acciones(
        list(datos.get('acciones', [])), exigir_id=schema_version >= 2
    )
    herramienta = str(datos.get('herramienta', ''))
    try:
        requisitos = _requerimientos_del_catalogo(herramienta)
    except ErrorPolitica as fallo:
        raise ErrorIntegridad(
            f'{CODIGO_POLITICA_REQUERIDA_DESACTUALIZADA}: {fallo}'
        ) from fallo
    _validar_tipos_declarados(requisitos, acciones)
    _indices_por_id(acciones)
    orden_topologico(acciones)
    datos['acciones'] = acciones
    datos['total'] = len(acciones)
    return datos


def migrar_plan(ruta_plan: Path) -> Path:
    # Reescribe un manifiesto v1 como v2 conservando acciones, estado y metadatos.
    try:
        datos = json.loads(ruta_plan.read_text(encoding='utf-8'))
    except OSError as fallo:
        raise ErrorIntegridad(
            f'no se pudo leer el plan {ruta_plan} porque {fallo}'
        ) from fallo
    except json.JSONDecodeError as fallo:
        raise ErrorIntegridad(
            f'el plan {ruta_plan} no es JSON valido porque {fallo}'
        ) from fallo
    version = datos.get('schema_version')
    if version is None:
        raise ErrorIntegridad(
            f'{CODIGO_MANIFEST_SCHEMA_VERSION_MISSING}: el manifiesto no declara schema_version'
        )
    if version == SCHEMA_VERSION_ACTUAL:
        # Migrar dos veces no cambia el archivo ni vuelve a firmarlo.
        cargar_plan(ruta_plan)
        return ruta_plan
    if version != 1:
        raise ErrorIntegridad(
            f'{CODIGO_MANIFEST_SCHEMA_VERSION_NO_SOPORTADA}: el manifiesto declara '
            f'schema_version {version}, no soportada'
        )
    _verificar_firma(datos, ruta_plan, 1)
    herramienta = str(datos.get('herramienta', ''))
    requisitos = _requerimientos_del_catalogo(herramienta)
    acciones = _normalizar_acciones(list(datos.get('acciones', [])))
    _validar_tipos_declarados(requisitos, acciones)
    acciones = orden_topologico(acciones)
    firma = firmar_plan(
        acciones,
        schema_version=SCHEMA_VERSION_ACTUAL,
        plan_id=str(datos.get('plan_id') or datos.get('id_ejecucion') or ruta_plan.stem),
        workspace_id=str(datos.get('workspace_id', '')),
        workspace_root=str(datos.get('workspace_root', '')),
        herramienta=herramienta,
        contrato_version=capabilities.VERSION_CONTRATO,
        requisitos=requisitos.como_dict(),
    )
    datos['schema_version'] = SCHEMA_VERSION_ACTUAL
    datos['contrato_version'] = capabilities.VERSION_CONTRATO
    datos['politica'] = requisitos.como_dict()
    datos['migrado_desde'] = 1
    datos['acciones'] = acciones
    datos['total'] = len(acciones)
    datos['firma'] = firma
    _escribir_manifiesto(ruta_plan, datos)
    return ruta_plan


def actualizar_estado_plan(ruta_plan: Path, estado: str) -> None:
    # Marca el manifiesto sin tocar la firma, que cubre solo las acciones y su contrato.
    datos = json.loads(ruta_plan.read_text(encoding='utf-8'))
    datos['estado'] = estado
    _escribir_manifiesto(ruta_plan, datos)


def hash_contenido(ruta: Path) -> str:
    # Calcula el SHA-256 del archivo por bloques para no cargarlo completo.
    resumen = hashlib.sha256()
    with ruta.open('rb') as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b''):
            resumen.update(bloque)
    return resumen.hexdigest()


def hash_arbol(raiz: Path) -> str:
    # Calcula un hash del arbol de una carpeta sin seguir enlaces ni junctions.
    resumen = hashlib.sha256()
    base = Path(raiz).expanduser().resolve()
    inventario: list[tuple[str, str, str]] = []
    for carpeta, subcarpetas, archivos in os.walk(base, followlinks=False):
        ruta_carpeta = Path(carpeta)
        # Los enlaces y junctions se registran pero no se recorren.
        for nombre in list(subcarpetas):
            candidato = ruta_carpeta / nombre
            if candidato.is_symlink() or candidato.is_junction():
                inventario.append(('link', str(candidato.relative_to(base)), ''))
                subcarpetas.remove(nombre)
        for nombre in archivos:
            candidato = ruta_carpeta / nombre
            if candidato.is_symlink() or candidato.is_junction():
                inventario.append(('link', str(candidato.relative_to(base)), ''))
                continue
            try:
                huella = hash_contenido(candidato)
                inventario.append(('file', str(candidato.relative_to(base)), huella))
            except OSError:
                inventario.append(('file', str(candidato.relative_to(base)), 'ERROR'))
    inventario.sort()
    for tipo, relativo, huella in inventario:
        resumen.update(f'{tipo}:{relativo}:{huella}\n'.encode())
    return resumen.hexdigest()


def _validar_accion(accion: dict) -> str | None:
    # Comprueba que una accion sigue siendo correcta justo antes de ejecutarla.
    origen = Path(str(accion.get('origen', '')))
    tipo = str(accion.get('tipo', 'papelera'))
    if tipo not in TIPOS_PERMITIDOS:
        return f'tipo no permitido {tipo}'
    if origen.is_symlink() or origen.is_junction():
        return 'el origen es un enlace, no se procesa'
    if tipo == 'crear_carpeta':
        return None if not origen.exists() or origen.is_dir() else 'el origen es un archivo'
    if not origen.exists():
        return 'ya no existe'
    if origen.is_file():
        tamano_plan = accion.get('tamano')
        if tamano_plan is not None and origen.stat().st_size != tamano_plan:
            return 'cambio de tamano entre plan y aplicar'
        mtime_plan = accion.get('mtime')
        if mtime_plan is not None and origen.stat().st_mtime != mtime_plan:
            return 'cambio de contenido entre plan y aplicar'
        firma = accion.get('hash')
        if firma and hash_contenido(origen) != firma:
            return 'cambio de contenido entre plan y aplicar'
    elif origen.is_dir():
        firma = accion.get('hash')
        if firma:
            try:
                if hash_arbol(origen) != firma:
                    return 'cambio de contenido entre plan y aplicar'
            except OSError:
                return 'no se pudo validar el contenido de la carpeta'
    destino = str(accion.get('destino', ''))
    if tipo == 'mover':
        if not destino:
            return 'mover sin destino'
        if Path(destino).exists():
            return f'el destino ya existe, no se sobrescribe {destino}'
    return None


def _validar_arbol(plan: dict) -> list[dict]:
    # Recorre cada accion del plan y acumula las que ya no se pueden ejecutar.
    fallos = []
    for accion in plan.get('acciones', []):
        detalle = _validar_accion(accion)
        if detalle:
            fallos.append({'ruta': str(accion.get('origen', '')), 'detalle': detalle})
    return fallos


# Tipos de accion que puede ejecutar el guardian.
TIPOS_PERMITIDOS = {'papelera', 'mover', 'crear_carpeta'}


def mover_a_papelera_from_safety(ruta) -> None:
    # Mantiene el nombre antiguo y deja propagar el OSError con su winerror intacto.
    import send2trash

    send2trash.send2trash(str(ruta))


def ejecutar_plan(plan, accion_desc: str = 'ejecutar plan') -> dict:
    # Guardian centralizado reutilizando el validador y el ejecutor unicos.
    verificar_escritura(accion_desc)
    movidos = []
    fallos = []
    for accion_obj in plan.acciones:
        accion = {
            'tipo': accion_obj.tipo,
            'origen': accion_obj.origen,
            'destino': accion_obj.destino,
        }
        detalle = _validar_accion(accion)
        if detalle:
            fallos.append({'origen': accion_obj.origen, 'detalle': detalle})
            continue
        try:
            _ejecutar_accion(accion)
            movidos.append(accion_obj)
        except Exception as fallo:  # noqa: BLE001
            fallos.append({'origen': accion_obj.origen, 'detalle': str(fallo)})
    return {'movidos': movidos, 'fallos': fallos, 'total': len(movidos)}


def _ejecutar_accion(accion: dict) -> None:
    # Ejecuta una accion ya validada, unico camino de escritura del toolkit.
    tipo = str(accion.get('tipo', 'papelera'))
    origen = Path(str(accion.get('origen', '')))
    if tipo == 'papelera':
        mover_a_papelera_from_safety(origen)
        return
    destino = str(accion.get('destino', ''))
    if tipo == 'mover':
        destino_ruta = Path(destino)
        destino_ruta.parent.mkdir(parents=True, exist_ok=True)
        origen.replace(destino_ruta)
        return
    if tipo == 'crear_carpeta':
        origen.mkdir(parents=True, exist_ok=True)
        return
    raise ErrorIntegridad(f'tipo no permitido {tipo}')




def _validar_identidad(base, plan, dry_run):
    workspace_manifesto = str(plan.get('workspace_id', ''))
    workspace_activo = modulo_workspace.leer_id(base)
    if workspace_activo is None:
        estado_identidad = 'sin_identidad'
    elif not workspace_manifesto:
        estado_identidad = 'manifiesto_sin_identidad'
    elif workspace_manifesto == workspace_activo:
        estado_identidad = 'coincide'
    else:
        estado_identidad = 'distinta'
    es_compartido = (
        estado_identidad in ('coincide', 'sin_identidad')
        and workspace_activo is not None
        and modulo_workspace.es_compartido(base)
    )
    if es_compartido:
        estado_identidad = 'compartido'
    if not dry_run:
        if estado_identidad == 'distinta':
            raise ErrorIntegridad(
                'el manifiesto pertenece al workspace '
                + workspace_manifesto
                + ', no a '
                + str(workspace_activo)
            )
        if estado_identidad == 'manifiesto_sin_identidad':
            raise ErrorIntegridad(
                'el manifiesto no declara workspace_id; no se puede verificar su origen'
            )
        if estado_identidad == 'compartido':
            raise ErrorIntegridad(
                'el workspace '
                + str(workspace_activo)
                + ' se ha visto bajo otra raiz; usa --permitir-compartido para continuar'
            )
    return estado_identidad


def _validar_acciones_comunes(acciones, base):
    for accion in acciones:
        for clave in ('origen', 'destino'):
            valor = accion.get(clave)
            if valor and not modulo_workspace.esta_contenida(base, Path(str(valor))):
                raise ErrorIntegridad(
                    'la accion contiene una ruta fuera del workspace: ' + str(valor)
                )
    destinos = set()
    for accion in acciones:
        destino = str(accion.get('destino', ''))
        if destino:
            if destino in destinos:
                raise ErrorIntegridad(
                    'dos acciones comparten el mismo destino: ' + destino
                )
            destinos.add(destino)


def _validar_politica(politica, herramienta, acciones, requisitos=None):
    # Comprueba que la politica cubre la capacidad y cada tipo de accion del plan.
    if politica is None:
        raise ErrorPolitica(
            'POLITICA_AUSENTE: aplicar ' + herramienta + ' exige una politica explicita'
        )
    if politica.capacidad != herramienta:
        raise ErrorPolitica(
            'POLITICA_INCOHERENTE: la politica es de '
            + politica.capacidad
            + ', no de '
            + herramienta
        )
    if politica.accion != 'aplicar':
        raise ErrorPolitica(
            'POLITICA_INCOHERENTE: la politica cubre '
            + politica.accion
            + ', no la accion aplicar'
        )
    if requisitos is not None and not requisitos.satisfechos_por(politica):
        raise ErrorPolitica(
            'POLITICA_INCOHERENTE: la politica no satisface los requerimientos del manifiesto'
        )
    for accion in acciones:
        tipo = str(accion.get('tipo', 'papelera'))
        if not politica.permite(tipo):
            raise ErrorPolitica(
                'ACCION_FUERA_DE_POLITICA: '
                + tipo
                + ' no esta permitida por la politica de '
                + herramienta
            )


def _estados_iniciales(acciones: list[dict], reconciliacion: dict | None) -> dict[str, str]:
    # Parten del estado reconciliado para que las dependencias historicas sigan contando.
    estados = {str(accion.get('id', '')): 'PENDIENTE' for accion in acciones}
    if reconciliacion:
        for fila in reconciliacion.get('resultados', []):
            indice = int(fila.get('indice', -1))
            if 0 <= indice < len(acciones):
                estados[str(acciones[indice].get('id', ''))] = str(fila.get('estado', 'PENDIENTE'))
    return estados


def _motivo_dependencia(accion: dict, estados: dict[str, str]) -> tuple[str, str] | None:
    # Una accion solo corre si todas sus dependencias ya se completaron en este plan.
    for dependencia in accion.get('depende_de', []):
        identificador = str(dependencia)
        estado = estados.get(identificador, 'DESCONOCIDA')
        if estado == 'COMPLETADA':
            continue
        if estado == 'OMITIDA':
            return CODIGO_DEPENDENCIA_OMITIDA, 'dependencia omitida: ' + identificador
        if estado in ('FALLIDA', 'FAILED', 'AMBIGUA', 'INCONSISTENTE', 'DESCONOCIDA'):
            return CODIGO_DEPENDENCIA_FALLIDA, 'dependencia fallida: ' + identificador
        return CODIGO_DEPENDENCIA_FALLIDA, 'dependencia pendiente: ' + identificador
    return None


def _codigo_de_detalle(detalle: str) -> str:
    # Traduce el mensaje de validacion a un codigo estable para el journal.
    texto = detalle.lower()
    if 'ya no existe' in texto:
        return 'ORIGEN_DESAPARECIDO'
    if 'cambio' in texto or 'modificado' in texto:
        return 'CAMBIO_DURANTE_EJECUCION'
    if 'destino ya existe' in texto:
        return 'DESTINO_OCUPADO'
    if 'fuera del workspace' in texto:
        return 'RUTA_FUERA_DEL_WORKSPACE'
    if 'enlace' in texto or 'junction' in texto:
        return 'ORIGEN_ES_ENLACE'
    if 'sin destino' in texto:
        return 'DESTINO_FALTANTE'
    return 'VALIDACION_FALLIDA'


def _espera_reintento(intento: int) -> float:
    # Espera 100, 300 o 900 ms con una variacion del 20 por ciento.
    base = [0.1, 0.3, 0.9][min(intento, 2)]
    return base * (1 + random.uniform(-0.2, 0.2))


def _ejecutar_accion_con_reintento(accion: dict, al_reintentar=None, max_intentos: int = 3) -> int:
    # Ejecuta una accion y reintenta solo los bloqueos transitorios de Windows.
    intento = 1
    while True:
        try:
            _ejecutar_accion(accion)
            return intento
        except OSError as fallo:
            codigo = clasificar_error_windows(fallo)
            if codigo == 'ARCHIVO_BLOQUEADO' and intento < max_intentos:
                if al_reintentar is not None:
                    al_reintentar(codigo, intento, fallo)
                time.sleep(_espera_reintento(intento - 1))
                intento += 1
                continue
            raise


def aplicar_manifiesto(
    ruta_plan,
    herramienta,
    espacio_trabajo='',
    autorizar=None,
    reanudar: bool = False,
    politica=None,
):
    # Ejecutor unico de manifiestos persistentes de toda la suite de herramientas.
    verificar_escritura('aplicar ' + herramienta)
    _validar_politica(politica, herramienta, [])
    preflight_plan(ruta_plan, espacio_trabajo)
    plan = cargar_plan(ruta_plan)
    acciones = [dict(accion) for accion in plan.get('acciones', [])]
    plan_herramienta = str(plan.get('herramienta', ''))
    if plan_herramienta and plan_herramienta != herramienta:
        raise ErrorIntegridad(
            'el manifiesto pertenece a ' + plan_herramienta + ', no a ' + herramienta
        )
    base = Path(espacio_trabajo).expanduser().resolve() if espacio_trabajo else Path.cwd().resolve()
    if not base.is_dir():
        raise ErrorIntegridad('la raiz de trabajo no existe ' + str(base))
    _validar_identidad(base, plan, dry_run=False)
    _validar_acciones_comunes(acciones, base)
    requisitos = _requerimientos_del_catalogo(herramienta)
    if int(plan.get('schema_version', 0)) >= 2:
        requisitos = _requisitos_del_manifiesto(plan, ruta_plan)
    _validar_politica(politica, herramienta, acciones, requisitos=requisitos)
    anotacion = politica.como_dict()
    id_plan = ruta_plan.stem
    reconciliacion = None
    pendientes = None
    if reanudar:
        reconciliacion = reconciliar_plan(ruta_plan, espacio_trabajo)
        if reconciliacion['ambiguas'] or reconciliacion['inconsistentes']:
            raise ErrorIntegridad(
                'RECONCILIACION_REQUIERE_INTERVENCION: '
                + str(len(reconciliacion['ambiguas']))
                + ' ambiguas y '
                + str(len(reconciliacion['inconsistentes']))
                + ' inconsistentes en '
                + id_plan
            )
        pendientes = {
            fila['indice']
            for fila in reconciliacion['resultados']
            if fila['estado'] == 'PENDIENTE'
        }
        if not pendientes:
            return {
                'id_ejecucion': '',
                'id_plan': id_plan,
                'estado_plan': 'reconciliado',
                'movidos': [],
                'fallidos': [],
                'omitidos': [],
                'total': len(acciones),
                'codigo': 0,
                'ya_resueltas': len(acciones),
                'reconciliacion': reconciliacion,
            }
    orden = _orden_de_ejecucion(acciones)
    indices = [i for i in orden if pendientes is None or i in pendientes]
    ya_resueltas = len(acciones) - len(indices)
    estados = _estados_iniciales(acciones, reconciliacion)
    id_ejec = runlog.iniciar_ejecucion(
        herramienta, 'aplicar', espacio_trabajo=espacio_trabajo, id_plan=id_plan,
        politica=anotacion,
    )
    movidos = []
    fallidos = []
    omitidos = []

    def anotar_reintento(codigo_error: str, intento: int, fallo: Exception) -> None:
        # Deja constancia de cada reintento para que la ventana de bloqueo sea auditable.
        runlog.registrar_hito(
            id_ejec,
            herramienta,
            'accion',
            'REINTENTO',
            codigo_error + ': intento ' + str(intento) + ' ' + str(fallo),
            origen=str(accion_actual.get('origen', '')),
            destino=str(accion_actual.get('destino', '')),
            codigo_error=codigo_error,
            espacio_trabajo=espacio_trabajo,
            id_plan=id_plan,
            nivel='accion',
            politica=anotacion,
        )

    for posicion, indice in enumerate(indices):
        accion_actual = acciones[indice]
        origen = str(accion_actual.get('origen', ''))
        destino = str(accion_actual.get('destino', ''))
        id_accion = str(accion_actual.get('id', ''))
        motivo_dependencia = _motivo_dependencia(accion_actual, estados)
        if motivo_dependencia is not None:
            codigo_error, detalle = motivo_dependencia
            estados[id_accion] = 'OMITIDA'
            omitidos.append(accion_actual)
            runlog.registrar_hito(
                id_ejec, herramienta, 'accion', 'OMITIDO', detalle,
                origen=origen, destino=destino, codigo_error=codigo_error,
                espacio_trabajo=espacio_trabajo, id_plan=id_plan, nivel='accion',
                politica=anotacion,
            )
            continue
        if autorizar is not None and not autorizar(accion_actual):
            estados[id_accion] = 'OMITIDA'
            omitidos.append(accion_actual)
            runlog.registrar_hito(
                id_ejec, herramienta, 'accion', 'OMITIDO', 'sin autorizar',
                origen=origen, destino=destino,
                espacio_trabajo=espacio_trabajo, id_plan=id_plan, nivel='accion',
                politica=anotacion,
            )
            continue
        detalle = _validar_accion(accion_actual)
        runlog.registrar_hito(
            id_ejec, herramienta, 'accion', 'PENDING', detalle or 'en curso',
            origen=origen, destino=destino,
            codigo_error=_codigo_de_detalle(detalle) if detalle else '',
            espacio_trabajo=espacio_trabajo, id_plan=id_plan, nivel='accion',
            politica=anotacion,
        )
        if detalle:
            codigo_error = _codigo_de_detalle(detalle)
            estados[id_accion] = 'FALLIDA'
            fallidos.append(
                {'origen': origen, 'detalle': detalle, 'codigo_error': codigo_error}
            )
            runlog.registrar_hito(
                id_ejec, herramienta, 'accion', 'FAILED', detalle,
                origen=origen, destino=destino, codigo=2, codigo_error=codigo_error,
                espacio_trabajo=espacio_trabajo, id_plan=id_plan, nivel='accion',
                politica=anotacion,
            )
            continue
        try:
            _ejecutar_accion_con_reintento(accion_actual, al_reintentar=anotar_reintento)
            estados[id_accion] = 'COMPLETADA'
            movidos.append(accion_actual)
            runlog.registrar_hito(
                id_ejec, herramienta, 'accion', 'COMPLETED', 'aplicada',
                origen=origen, destino=destino, codigo=0,
                espacio_trabajo=espacio_trabajo, id_plan=id_plan, nivel='accion',
                politica=anotacion,
            )
        except Exception as fallo:  # noqa: BLE001
            codigo_error = clasificar_error_windows(fallo)
            texto = str(fallo)
            if codigo_error == 'ERROR_DESCONOCIDO':
                detalle_final = texto
            else:
                detalle_final = codigo_error + ': ' + texto
            estados[id_accion] = 'FALLIDA'
            fallidos.append(
                {'origen': origen, 'detalle': detalle_final, 'codigo_error': codigo_error}
            )
            runlog.registrar_hito(
                id_ejec, herramienta, 'accion', 'FAILED', detalle_final,
                origen=origen, destino=destino, codigo=2, codigo_error=codigo_error,
                espacio_trabajo=espacio_trabajo, id_plan=id_plan, nivel='accion',
                politica=anotacion,
            )
            if codigo_error == 'DISCO_LLENO':
                # Un disco lleno invalida el resto del lote; no se acumulan fallos identicos.
                for restante in indices[posicion + 1:]:
                    accion_restante = acciones[restante]
                    estados[str(accion_restante.get('id', ''))] = 'OMITIDA'
                    omitidos.append(accion_restante)
                    runlog.registrar_hito(
                        id_ejec, herramienta, 'accion', 'OMITIDO',
                        'lote abortado por DISCO_LLENO',
                        origen=str(accion_restante.get('origen', '')),
                        destino=str(accion_restante.get('destino', '')),
                        codigo_error='DISCO_LLENO',
                        espacio_trabajo=espacio_trabajo, id_plan=id_plan, nivel='accion',
                        politica=anotacion,
                    )
                break
    omitidas_historicas = len(reconciliacion['omitidas']) if reconciliacion else 0
    if (
        not fallidos
        and not omitidos
        and omitidas_historicas == 0
        and len(movidos) + ya_resueltas == len(acciones)
    ):
        estado_plan = 'aplicado'
    elif movidos or ya_resueltas or omitidos:
        estado_plan = 'parcial'
    elif fallidos:
        estado_plan = 'fallido'
    else:
        estado_plan = 'parcial'
    actualizar_estado_plan(ruta_plan, estado_plan)
    estado = 'COMPLETED' if not fallidos else 'FAILED'
    runlog.cerrar_ejecucion(
        id_ejec, herramienta, 'aplicar', estado, 0 if not fallidos else 2,
        detalle=estado_plan, espacio_trabajo=espacio_trabajo, id_plan=id_plan,
        politica=anotacion,
    )
    return {
        'id_ejecucion': id_ejec,
        'id_plan': id_plan,
        'estado_plan': estado_plan,
        'movidos': movidos,
        'fallidos': fallidos,
        'omitidos': omitidos,
        'total': len(acciones),
        'codigo': 0 if not fallidos else 2,
        'ya_resueltas': ya_resueltas,
        'reconciliacion': reconciliacion,
        'politica_huella': politica.huella(),
    }


def _simular_acciones_ordenadas(
    acciones,
    herramienta,
    base,
    autorizar=None,
    politica=None,
    estado_identidad='sin_identidad',
):
    # Simula el plan completo en orden de dependencias y omite lo que nunca llegaria a correr.
    orden = _orden_de_ejecucion(acciones)
    estados = {str(accion.get('id', '')): 'PENDIENTE' for accion in acciones}
    movidos = []
    fallidos = []
    omitidos = []
    destinos = set()
    for indice in orden:
        accion = acciones[indice]
        identificador = str(accion.get('id', ''))
        origen = str(accion.get('origen', ''))
        destino = str(accion.get('destino', ''))
        motivo = _motivo_dependencia(accion, estados)
        if motivo is not None:
            estados[identificador] = 'OMITIDA'
            omitidos.append(accion)
            continue
        if destino and destino in destinos:
            estados[identificador] = 'FALLIDA'
            fallidos.append(
                {'origen': origen, 'detalle': 'destino duplicado: ' + destino}
            )
            continue
        if destino:
            destinos.add(destino)
        fuera = False
        for clave in ('origen', 'destino'):
            valor = accion.get(clave)
            if valor and not modulo_workspace.esta_contenida(base, Path(str(valor))):
                estados[identificador] = 'FALLIDA'
                fallidos.append(
                    {'origen': origen, 'detalle': 'ruta fuera del workspace: ' + str(valor)}
                )
                fuera = True
                break
        if fuera:
            continue
        if autorizar is not None and not autorizar(accion):
            estados[identificador] = 'OMITIDA'
            omitidos.append(accion)
            continue
        detalle = _validar_accion(accion)
        if detalle:
            estados[identificador] = 'FALLIDA'
            fallidos.append(
                {
                    'origen': origen,
                    'detalle': detalle,
                    'codigo_error': _codigo_de_detalle(detalle),
                }
            )
        else:
            estados[identificador] = 'COMPLETADA'
            movidos.append(accion)
    return {
        'id_ejecucion': '',
        'id_plan': 'simulado',
        'estado_plan': 'simulado',
        'movidos': movidos,
        'fallidos': fallidos,
        'omitidos': omitidos,
        'total': len(acciones),
        'codigo': 0 if not fallidos else 2,
        'dry_run': True,
        'estado_identidad': estado_identidad,
        'politica_huella': politica.huella() if politica is not None else '',
    }


def simular_manifiesto(
    ruta_plan, herramienta, espacio_trabajo='', autorizar=None, politica=None
):
    _validar_politica(politica, herramienta, [])
    plan = cargar_plan(ruta_plan)
    acciones = [dict(accion) for accion in plan.get('acciones', [])]
    requisitos = _requerimientos_del_catalogo(herramienta)
    if int(plan.get('schema_version', 0)) >= 2:
        requisitos = _requisitos_del_manifiesto(plan, ruta_plan)
    _validar_politica(politica, herramienta, acciones, requisitos=requisitos)
    plan_herramienta = str(plan.get('herramienta', ''))
    if plan_herramienta and plan_herramienta != herramienta:
        raise ErrorIntegridad(
            'el manifiesto pertenece a ' + plan_herramienta + ', no a ' + herramienta
        )
    base = Path(espacio_trabajo).expanduser().resolve() if espacio_trabajo else Path.cwd().resolve()
    if not base.is_dir():
        raise ErrorIntegridad('la raiz de trabajo no existe ' + str(base))
    estado_identidad = _validar_identidad(base, plan, dry_run=True)
    _validar_acciones_comunes(acciones, base)
    resultado = _simular_acciones_ordenadas(
        acciones, herramienta, base, autorizar, politica, estado_identidad
    )
    resultado['id_plan'] = ruta_plan.stem
    return resultado


def _simular_acciones(acciones, herramienta, base, autorizar=None, politica=None):
    _validar_politica(politica, herramienta, [])
    normalizadas = _normalizar_acciones(acciones)
    _validar_politica(politica, herramienta, normalizadas)
    ordenadas = orden_topologico(normalizadas)
    return _simular_acciones_ordenadas(
        ordenadas, herramienta, base, autorizar, politica, 'sin_identidad'
    )


def aplicar_plan_persistente(
    ruta_plan: Path, espacio_trabajo: str = '', politica=None
) -> dict:
    # Compatibilidad con la forma antigua del resultado del ejecutor.
    plan = cargar_plan(ruta_plan)
    base = espacio_trabajo or str(plan.get('workspace_root') or '')
    herramienta = str(plan.get('herramienta') or '')
    resultado = aplicar_manifiesto(
        ruta_plan, herramienta, espacio_trabajo=base, politica=politica
    )
    return {
        'movidos': resultado['movidos'],
        'fallos': resultado['fallidos'],
        'total': len(resultado['movidos']),
        'id_ejecucion': resultado['id_ejecucion'],
        'estado_plan': resultado['estado_plan'],
    }


@dataclass
class Accion:
    tipo: str
    origen: str
    destino: str | None = None


@dataclass
class Plan:
    acciones: list[Accion] = field(default_factory=list)

    def agregar(self, accion: Accion) -> None:
        self.acciones.append(accion)

    def total(self) -> int:
        return len(self.acciones)

def preflight_plan(ruta_plan, espacio_trabajo=''):
    plan = cargar_plan(ruta_plan)
    acciones = [dict(a) for a in plan.get('acciones', [])]
    base = Path(espacio_trabajo).expanduser().resolve() if espacio_trabajo else Path.cwd().resolve()
    if not base.is_dir():
        raise ErrorIntegridad('la raiz de trabajo no existe ' + str(base))
    # Comprobar espacio libre.
    total_bytes = sum(int(a.get('tamano', 0)) for a in acciones)
    try:
        libre = shutil.disk_usage(str(base)).free
    except OSError:
        libre = None
    if libre is not None and libre < total_bytes:
        raise ErrorIntegridad(
            'DISCO_LLENO: espacio libre insuficiente '
            + str(libre) + ' < ' + str(total_bytes)
        )
    # Comprobar longitud de ruta y existencia de origen.
    for accion in acciones:
        for clave in ('origen', 'destino'):
            valor = accion.get(clave)
            if valor:
                ruta = Path(str(valor))
                if len(str(ruta)) > 260:
                    raise ErrorIntegridad(
                        'RUTA_DEMASIADO_LARGA: ' + str(valor)
                    )
        origen = Path(str(accion.get('origen', '')))
        fuera = (
            accion.get('tipo') != 'crear_carpeta'
            and origen.exists()
            and not modulo_workspace.esta_contenida(base, origen)
        )
        if fuera:
            raise ErrorIntegridad(
                'la accion contiene una ruta fuera del workspace: ' + str(origen)
            )
    # Comprobar que el destino base es escribible.
    try:
        prueba = base / '.devkit' / '.preflight_test'
        prueba.parent.mkdir(parents=True, exist_ok=True)
        prueba.write_text('ok', encoding='utf-8')
        prueba.unlink()
    except OSError as fallo:
        raise ErrorIntegridad(
            'PERMISO_DENEGADO: no se puede escribir en ' + str(base) + ': ' + str(fallo)
        ) from fallo
    return True


# Clasificacion de errores de Windows.
def clasificar_error_windows(fallo: Exception) -> str:
    winerror = getattr(fallo, 'winerror', None)
    if winerror in (32, 33):
        return 'ARCHIVO_BLOQUEADO'
    if winerror in (5, 19):
        return 'PERMISO_DENEGADO'
    if winerror == 112:
        return 'DISCO_LLENO'
    if winerror == 206:
        return 'RUTA_DEMASIADO_LARGA'
    if winerror == 183:
        return 'DESTINO_OCUPADO'
    if winerror in (2, 3):
        return 'ORIGEN_DESAPARECIDO'
    return 'ERROR_DESCONOCIDO'


def _postcondicion(accion: dict) -> str:
    # Deduce el estado de una accion comparando el manifiesto con el sistema de archivos.
    origen = Path(str(accion.get('origen', '')))
    destino_texto = str(accion.get('destino', ''))
    destino = Path(destino_texto) if destino_texto else None
    tipo = str(accion.get('tipo', 'papelera'))
    if tipo == 'crear_carpeta':
        if origen.is_dir():
            return 'COMPLETADA'
        return 'INCONSISTENTE' if origen.exists() else 'PENDIENTE'
    if tipo == 'papelera':
        return 'COMPLETADA' if not origen.exists() else 'PENDIENTE'
    if destino is None:
        return 'PENDIENTE' if origen.exists() else 'INCONSISTENTE'
    existe_origen = origen.exists()
    existe_destino = destino.exists()
    if existe_origen and not existe_destino:
        return 'PENDIENTE'
    if existe_origen and existe_destino:
        return 'AMBIGUA'
    if not existe_origen and not existe_destino:
        return 'INCONSISTENTE'
    # Queda el caso de destino presente y origen ausente: hay que probar el contenido.
    esperado = accion.get('hash')
    if esperado:
        try:
            if not destino.is_file():
                return 'AMBIGUA'
            return 'COMPLETADA' if hash_contenido(destino) == str(esperado) else 'AMBIGUA'
        except OSError:
            return 'AMBIGUA'
    tamano = accion.get('tamano')
    if tamano is not None:
        try:
            if destino.is_file() and destino.stat().st_size == int(tamano):
                return 'COMPLETADA'
            return 'AMBIGUA'
        except OSError:
            return 'AMBIGUA'
    return 'COMPLETADA'


def reconciliar_plan(ruta_plan: Path, espacio_trabajo: str = '') -> dict:
    # Reconstruye el estado de cada accion desde sus postcondiciones y los hitos del journal.
    plan = cargar_plan(ruta_plan)
    acciones = [dict(a) for a in plan.get('acciones', [])]
    historial = runlog.hitos_del_plan(ruta_plan.stem)
    omitidas = {
        (str(h.get('origen', '')), str(h.get('destino', '')))
        for h in historial
        if h.get('estado') == 'OMITIDO'
    }
    completadas = {
        (str(h.get('origen', '')), str(h.get('destino', '')))
        for h in historial
        if h.get('estado') == 'COMPLETED'
    }
    resultados: dict[int, dict] = {}
    estado_por_id: dict[str, str] = {}
    for indice in _orden_de_ejecucion(acciones):
        accion = acciones[indice]
        clave = (str(accion.get('origen', '')), str(accion.get('destino', '')))
        if clave in omitidas:
            estado = 'OMITIDA'
            motivo = 'hito OMITIDO en el journal'
        else:
            estado = _postcondicion(accion)
            motivo = ''
            if estado != 'COMPLETADA' and clave in completadas:
                estado = 'INCONSISTENTE'
                motivo = 'el journal la marca COMPLETED pero la postcondicion no se cumple'
            elif estado == 'AMBIGUA':
                motivo = 'origen y destino presentes, o contenido distinto'
            elif estado == 'PENDIENTE':
                motivo = 'origen presente y destino ausente'
            elif estado == 'INCONSISTENTE':
                motivo = 'origen y destino ausentes'
        if estado == 'PENDIENTE':
            # Una dependencia omitida impide ejecutar la accion, aunque su origen siga presente.
            for dependencia in accion.get('depende_de', []):
                if estado_por_id.get(str(dependencia)) == 'OMITIDA':
                    estado = 'OMITIDA'
                    motivo = 'dependencia omitida: ' + str(dependencia)
                    break
        identificador = str(accion.get('id', ''))
        fila = {
            'indice': indice,
            'id': identificador,
            'tipo': str(accion.get('tipo', 'papelera')),
            'origen': clave[0],
            'destino': clave[1],
            'estado': estado,
            'motivo': motivo,
        }
        resultados[indice] = fila
        estado_por_id[identificador] = estado
    finales = [resultados[indice] for indice in range(len(acciones))]
    return {
        'id_plan': ruta_plan.stem,
        'total': len(acciones),
        'resultados': finales,
        'pendientes': [r for r in finales if r['estado'] == 'PENDIENTE'],
        'ambiguas': [r for r in finales if r['estado'] == 'AMBIGUA'],
        'inconsistentes': [r for r in finales if r['estado'] == 'INCONSISTENTE'],
        'completadas': [r for r in finales if r['estado'] == 'COMPLETADA'],
        'omitidas': [r for r in finales if r['estado'] == 'OMITIDA'],
    }
