# Politica de permisos inmutable derivada del catalogo y de las compuertas del CLI.
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from devkit.core import capabilities
from devkit.errors import ErrorPolitica

# Permiso que exige cada tipo de accion del ejecutor unico.
PERMISOS_POR_TIPO = {
    'papelera': 'trash:move',
    'mover': 'filesystem:write',
    'crear_carpeta': 'filesystem:write',
}


@dataclass(frozen=True)
class Politica:
    # Describe que puede hacer una capacidad concreta y con que compuertas.
    capacidad: str
    accion: str
    confirmada: bool
    forzada: bool
    flags: tuple[str, ...]
    permisos: tuple[str, ...]
    tipos: tuple[str, ...]
    compuertas: tuple[str, ...]

    def permite(self, tipo: str) -> bool:
        # Una accion solo pasa si su tipo esta declarado y el permiso esta presente.
        if tipo not in self.tipos:
            return False
        permiso = PERMISOS_POR_TIPO.get(tipo)
        return permiso is None or permiso in self.permisos

    def huella(self) -> str:
        # Resume la decision en una huella estable para el journal.
        datos = {
            'capacidad': self.capacidad,
            'accion': self.accion,
            'confirmada': self.confirmada,
            'forzada': self.forzada,
            'flags': list(self.flags),
            'permisos': list(self.permisos),
            'tipos': list(self.tipos),
            'compuertas': list(self.compuertas),
        }
        texto = json.dumps(
            datos, sort_keys=True, separators=(',', ':'), ensure_ascii=False
        )
        return hashlib.sha256(texto.encode('utf-8')).hexdigest()

    def como_dict(self) -> dict:
        # Devuelve la anotacion que acompana a cada hito del journal.
        return {
            'huella': self.huella(),
            'capacidad': self.capacidad,
            'accion': self.accion,
            'confirmada': self.confirmada,
            'forzada': self.forzada,
            'flags': list(self.flags),
            'permisos': list(self.permisos),
            'tipos': list(self.tipos),
            'compuertas': list(self.compuertas),
            'decision': 'PERMITIDA',
        }


def derivar(
    capacidad: str,
    accion: str,
    confirmada: bool = False,
    forzada: bool = False,
    flags: tuple[str, ...] = (),
) -> Politica:
    # Construye la politica de una accion y falla si falta una compuerta exigida.
    registro = capabilities.obtener_capacidad(capacidad)
    if registro is None:
        raise ErrorPolitica(
            f'POLITICA_NO_DECLARADA: no existe la capacidad {capacidad}'
        )
    acciones = dict(registro.get('actions') or {})
    if accion not in acciones:
        raise ErrorPolitica(
            f'POLITICA_NO_DECLARADA: {capacidad} no declara la accion {accion}'
        )
    definicion = dict(acciones[accion])
    if 'compuertas' not in definicion or 'tipos' not in definicion:
        raise ErrorPolitica(
            f'POLITICA_NO_DECLARADA: {capacidad} {accion} no declara compuertas ni tipos'
        )
    compuertas = dict(definicion.get('compuertas') or {})
    if compuertas.get('confirmacion') and not confirmada:
        raise ErrorPolitica(
            f'CONFIRMACION_REQUERIDA: {capacidad} {accion} exige --si'
        )
    if compuertas.get('anulacion') and not forzada:
        raise ErrorPolitica(
            f'ANULACION_REQUERIDA: {capacidad} {accion} exige --forzar'
        )
    nombres = set(flags)
    if confirmada:
        nombres.add('si')
    if forzada:
        nombres.add('forzar')
    permisos = tuple(registro.get('write_permissions') or ())
    tipos = tuple(definicion.get('tipos') or ())
    exigidas = tuple(
        nombre for nombre in ('confirmacion', 'anulacion') if compuertas.get(nombre)
    )
    return Politica(
        capacidad=capacidad,
        accion=accion,
        confirmada=confirmada,
        forzada=forzada,
        flags=tuple(sorted(nombres)),
        permisos=permisos,
        tipos=tipos,
        compuertas=exigidas,
    )
