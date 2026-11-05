# Punto unico donde se comprueba si una accion puede escribir en disco.
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from devkit.errors import ErrorSoloLectura

VALORES_ACTIVOS = {'1', 'true', 'si', 'yes', 'on'}


def modo_solo_lectura() -> bool:
    # Lee la variable global que bloquea cualquier escritura del toolkit.
    valor = os.environ.get('DEVKIT_READONLY', '')
    return valor.strip().lower() in VALORES_ACTIVOS


def verificar_escritura(accion: str) -> None:
    # Toda herramienta que mueva o borre pasa por aqui antes de tocar el disco.
    if modo_solo_lectura():
        raise ErrorSoloLectura(f'el modo de solo lectura impide {accion}')


# --- Planes persistentes (Bloque D) ---


def firmar_plan(acciones: list[dict]) -> str:
    # Firma estable del plan a partir de origen y destino.
    texto = '\n'.join(f'{a.get("origen", "")} -> {a.get("destino", "")}' for a in acciones)
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
        'firma': firma,
        'total': len(acciones),
        'acciones': acciones,
    }
    ruta = base / f'{id_ejecucion}.json'
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    return ruta


def cargar_plan(ruta: Path) -> dict:
    # Carga un plan persistido y valida su firma antes de aplicarlo.
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    if firmar_plan(datos.get('acciones', [])) != datos.get('firma'):
        raise ErrorSoloLectura(f'el plan {ruta} fue modificado, firma no coincide')
    return datos


def _validar_arbol(plan: dict) -> list[dict]:
    # Comprueba que cada archivo/carpeta del plan sigue existiendo con mismo tamano.
    fallos = []
    for accion in plan.get('acciones', []):
        ruta = Path(accion.get('origen', ''))
        if not ruta.exists():
            fallos.append({'ruta': str(ruta), 'detalle': 'ya no existe'})
            continue
        size_plan = accion.get('tamano')
        if size_plan is not None and ruta.is_file() and ruta.stat().st_size != size_plan:
            fallos.append({'ruta': str(ruta), 'detalle': 'cambio entre plan y aplicar'})
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
                destino.parent.mkdir(parents=True, exist_ok=True)
                Path(accion.origen).replace(destino)
            elif accion.tipo == 'crear_carpeta':
                from pathlib import Path

                Path(accion.origen).mkdir(parents=True, exist_ok=True)
            movidos.append(accion)
        except Exception as fallo:  # noqa: BLE001
            fallos.append({'origen': accion.origen, 'detalle': str(fallo)})
    return {'movidos': movidos, 'fallos': fallos, 'total': len(movidos)}


def aplicar_plan_persistente(ruta_plan: Path) -> dict:
    # Valida el manifiesto y luego ejecuta cada accion sin reescanear.
    plan = cargar_plan(ruta_plan)
    verificar_escritura('aplicar plan persistente')
    fallos = _validar_arbol(plan)
    if fallos:
        ident = plan.get('id_ejecucion')
        return {'movidos': [], 'fallos': fallos, 'total': 0, 'id_ejecucion': ident}
    envoltorio = Plan()
    for accion in plan.get('acciones', []):
        # El manifiesto guardaba el tipo como 'papelera' o 'mover'.
        tipo = accion.get('tipo', 'papelera')
        origen = accion.get('origen', '')
        destino = accion.get('destino')
        envoltorio.agregar(Accion(tipo=tipo, origen=origen, destino=destino))
    resultado = ejecutar_plan(envoltorio)
    resultado['id_ejecucion'] = plan.get('id_ejecucion')
    return resultado


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
