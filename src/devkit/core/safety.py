# Punto unico donde se comprueba si una accion puede escribir en disco.
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from devkit.core import runlog
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


def firmar_plan(acciones: list[dict]) -> str:
    # Firma de integridad accidental, no de autenticidad, sobre todo el contenido de las acciones.
    texto = json.dumps(acciones, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def guardar_plan(
    id_ejecucion: str,
    herramienta: str,
    acciones: list[dict],
    destino_dir: Path | None = None,
) -> Path:
    # Guarda el manifiesto del plan para aplicar despues sin reescanear.
    from devkit.core import paths

    base = destino_dir or (paths.directorio_planes())
    base.mkdir(parents=True, exist_ok=True)
    firma = firmar_plan(acciones)
    datos = {
        'id_ejecucion': id_ejecucion,
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
    if firmar_plan(datos.get('acciones', [])) != datos.get('firma'):
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


def _validar_accion(accion: dict) -> str | None:
    # Comprueba que una accion sigue siendo correcta justo antes de ejecutarla.
    origen = Path(str(accion.get('origen', '')))
    tipo = str(accion.get('tipo', 'papelera'))
    if tipo not in TIPOS_PERMITIDOS:
        return f'tipo no permitido {tipo}'
    if tipo == 'crear_carpeta':
        return None if not origen.is_file() else 'el origen es un archivo'
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
    # Guardian centralizado — unico sitio que toca el disco en escrituras.
    verificar_escritura(accion_desc)
    movidos = []
    fallos = []
    for accion in plan.acciones:
        if accion.tipo not in TIPOS_PERMITIDOS:
            fallos.append({'origen': accion.origen, 'detalle': f'tipo no permitido {accion.tipo}'})
            continue
        try:
            if accion.tipo == 'papelera':
                mover_a_papelera_from_safety(accion.origen)
            elif accion.tipo == 'mover':
                from pathlib import Path

                destino = Path(accion.destino) if accion.destino else None
                if destino is None:
                    fallos.append({'origen': accion.origen, 'detalle': 'mover sin destino'})
                    continue
                # Se mira el destino justo antes de mover para no pisar nada creado mientras tanto.
                if destino.exists():
                    detalle = f'el destino ya existe, no se sobrescribe {destino}'
                    fallos.append({'origen': accion.origen, 'detalle': detalle})
                    continue
                destino.parent.mkdir(parents=True, exist_ok=True)
                Path(accion.origen).replace(destino)
            elif accion.tipo == 'crear_carpeta':
                from pathlib import Path

                Path(accion.origen).mkdir(parents=True, exist_ok=True)
            movidos.append(accion)
        except Exception as fallo:  # noqa: BLE001
            fallos.append({'origen': accion.origen, 'detalle': str(fallo)})
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


def aplicar_manifiesto(
    ruta_plan: Path,
    herramienta: str,
    espacio_trabajo: str = '',
    autorizar=None,
) -> dict:
    # Ejecutor unico de manifiestos persistentes de toda la suite de herramientas.
    plan = cargar_plan(ruta_plan)
    verificar_escritura(f'aplicar {herramienta}')
    acciones = [dict(accion) for accion in plan.get('acciones', [])]
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
                id_ejec,
                herramienta,
                'accion',
                'OMITIDO',
                'sin autorizar',
                origen=origen,
                destino=destino,
                espacio_trabajo=espacio_trabajo,
                id_plan=id_plan,
                nivel='accion',
            )
            continue
        detalle = _validar_accion(accion)
        runlog.registrar_hito(
            id_ejec,
            herramienta,
            'accion',
            'PENDING',
            detalle or 'en curso',
            origen=origen,
            destino=destino,
            espacio_trabajo=espacio_trabajo,
            id_plan=id_plan,
            nivel='accion',
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
        # Las acciones omitidas a proposito dejan el manifiesto en parcial.
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


def aplicar_plan_persistente(ruta_plan: Path) -> dict:
    # Compatibilidad con la forma antigua del resultado del ejecutor.
    resultado = aplicar_manifiesto(ruta_plan, 'plan')
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
