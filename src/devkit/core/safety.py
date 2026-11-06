# Punto unico donde se comprueba si una accion puede escribir en disco.
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from devkit.core import runlog
from devkit.core import workspace as modulo_workspace
from devkit.errors import ErrorIntegridad, ErrorSoloLectura

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
SCHEMA_VERSION_ACTUAL = 1


def firmar_plan(
    acciones: list[dict],
    schema_version: int = SCHEMA_VERSION_ACTUAL,
    plan_id: str = '',
    workspace_id: str = '',
    workspace_root: str = '',
    herramienta: str = '',
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
    texto = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def guardar_plan(
    id_ejecucion: str,
    herramienta: str,
    acciones: list[dict],
    destino_dir: Path | None = None,
    workspace_id: str = '',
    workspace_root: str = '',
) -> Path:
    # Guarda el manifiesto del plan para aplicar despues sin reescanear.
    from devkit.core import paths

    base = destino_dir or (paths.directorio_planes())
    base.mkdir(parents=True, exist_ok=True)
    firma = firmar_plan(
        acciones,
        schema_version=SCHEMA_VERSION_ACTUAL,
        plan_id=id_ejecucion,
        workspace_id=workspace_id,
        workspace_root=workspace_root,
        herramienta=herramienta,
    )
    datos = {
        'schema_version': SCHEMA_VERSION_ACTUAL,
        'plan_id': id_ejecucion,
        'id_ejecucion': id_ejecucion,
        'workspace_id': workspace_id,
        'workspace_root': workspace_root,
        'herramienta': herramienta,
        'fecha': datetime.now(UTC).isoformat(),
        'estado': 'pendiente',
        'firma': firma,
        'total': len(acciones),
        'acciones': acciones,
    }
    ruta = base / f'{id_ejecucion}.json'
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    return ruta


def cargar_plan(ruta: Path) -> dict:
    # Carga un plan persistido y valida su firma antes de aplicarlo.
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
    if schema_version != SCHEMA_VERSION_ACTUAL:
        raise ErrorIntegridad(
            f'el manifiesto declara schema_version {schema_version}, no soportada. '
            f'No se ejecuto ninguna accion.'
        )
    acciones = datos.get('acciones', [])
    firma_esperada = firmar_plan(
        acciones,
        schema_version=schema_version,
        plan_id=str(datos.get('plan_id') or datos.get('id_ejecucion') or ruta.stem),
        workspace_id=str(datos.get('workspace_id', '')),
        workspace_root=str(datos.get('workspace_root', '')),
        herramienta=str(datos.get('herramienta', '')),
    )
    if firma_esperada != datos.get('firma'):
        raise ErrorIntegridad(f'el plan {ruta} fue modificado, firma no coincide')
    return datos


def actualizar_estado_plan(ruta_plan: Path, estado: str) -> None:
    # Marca el manifiesto sin tocar la firma, que cubre solo las acciones.
    datos = json.loads(ruta_plan.read_text(encoding='utf-8'))
    datos['estado'] = estado
    ruta_plan.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')


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
    # Mantiene compatibilidad con el nombre antiguo del guardian.
    import send2trash

    try:
        send2trash.send2trash(str(ruta))
    except OSError as fallo:
        raise ErrorSoloLectura(f'no se pudo mover a papelera {ruta} porque {fallo}') from fallo


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


def aplicar_manifiesto(ruta_plan, herramienta, espacio_trabajo='', autorizar=None):
    verificar_escritura('aplicar ' + herramienta)
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
    id_plan = ruta_plan.stem
    id_ejec = runlog.iniciar_ejecucion(
        herramienta, 'aplicar', espacio_trabajo=espacio_trabajo, id_plan=id_plan
    )
    movidos = []
    fallidos = []
    omitidos = []
    for accion in acciones:
        origen = str(accion.get('origen', ''))
        destino = str(accion.get('destino', ''))
        if autorizar is not None and not autorizar(accion):
            omitidos.append(accion)
            runlog.registrar_hito(
                id_ejec, herramienta, 'accion', 'OMITIDO', 'sin autorizar',
                origen=origen, destino=destino,
                espacio_trabajo=espacio_trabajo, id_plan=id_plan, nivel='accion',
            )
            continue
        detalle = _validar_accion(accion)
        runlog.registrar_hito(
            id_ejec, herramienta, 'accion', 'PENDING', detalle or 'en curso',
            origen=origen, destino=destino,
            espacio_trabajo=espacio_trabajo, id_plan=id_plan, nivel='accion',
        )
        if detalle:
            fallidos.append({'origen': origen, 'detalle': detalle})
            runlog.registrar_hito(
                id_ejec, herramienta, 'accion', 'FAILED', detalle,
                origen=origen, destino=destino, codigo=2,
                espacio_trabajo=espacio_trabajo, id_plan=id_plan, nivel='accion',
            )
            continue
        try:
            _ejecutar_accion(accion)
            movidos.append(accion)
            runlog.registrar_hito(
                id_ejec, herramienta, 'accion', 'COMPLETED', 'aplicada',
                origen=origen, destino=destino, codigo=0,
                espacio_trabajo=espacio_trabajo, id_plan=id_plan, nivel='accion',
            )
        except Exception as fallo:  # noqa: BLE001
            texto = str(fallo)
            fallidos.append({'origen': origen, 'detalle': texto})
            runlog.registrar_hito(
                id_ejec, herramienta, 'accion', 'FAILED', texto,
                origen=origen, destino=destino, codigo=2,
                espacio_trabajo=espacio_trabajo, id_plan=id_plan, nivel='accion',
            )
    if not fallidos and not omitidos and len(movidos) == len(acciones):
        estado_plan = 'aplicado'
    elif movidos:
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
    }


def simular_manifiesto(ruta_plan, herramienta, espacio_trabajo='', autorizar=None):
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
    estado_identidad = _validar_identidad(base, plan, dry_run=True)
    _validar_acciones_comunes(acciones, base)
    movidos = []
    fallidos = []
    omitidos = []
    for accion in acciones:
        origen = str(accion.get('origen', ''))
        if autorizar is not None and not autorizar(accion):
            omitidos.append(accion)
            continue
        detalle = _validar_accion(accion)
        if detalle:
            fallidos.append({'origen': origen, 'detalle': detalle})
        else:
            movidos.append(accion)
    return {
        'id_ejecucion': '',
        'id_plan': ruta_plan.stem,
        'estado_plan': 'simulado',
        'movidos': movidos,
        'fallidos': fallidos,
        'omitidos': omitidos,
        'total': len(acciones),
        'codigo': 0 if not fallidos else 2,
        'dry_run': True,
        'estado_identidad': estado_identidad,
    }


def _simular_acciones(acciones, herramienta, base, autorizar=None):
    movidos = []
    fallidos = []
    omitidos = []
    destinos = set()
    for accion in acciones:
        origen = str(accion.get('origen', ''))
        destino = str(accion.get('destino', ''))
        if destino and destino in destinos:
            fallidos.append({'origen': origen, 'detalle': 'destino duplicado: ' + destino})
            continue
        if destino:
            destinos.add(destino)
        fuera = False
        for clave in ('origen', 'destino'):
            valor = accion.get(clave)
            if valor and not modulo_workspace.esta_contenida(base, Path(str(valor))):
                fallidos.append(
                    {'origen': origen, 'detalle': 'ruta fuera del workspace: ' + str(valor)}
                )
                fuera = True
                break
        if fuera:
            continue
        if autorizar is not None and not autorizar(accion):
            omitidos.append(accion)
            continue
        detalle = _validar_accion(accion)
        if detalle:
            fallidos.append({'origen': origen, 'detalle': detalle})
        else:
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
        'estado_identidad': 'sin_identidad',
    }


def aplicar_plan_persistente(ruta_plan: Path, espacio_trabajo: str = '') -> dict:
    # Compatibilidad con la forma antigua del resultado del ejecutor.
    plan = cargar_plan(ruta_plan)
    base = espacio_trabajo or str(plan.get('workspace_root') or '')
    resultado = aplicar_manifiesto(ruta_plan, 'plan', espacio_trabajo=base)
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
