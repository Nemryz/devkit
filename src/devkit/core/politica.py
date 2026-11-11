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


@dataclass(frozen=True)
class Requerimientos:
    # Declara que autorizacion exige un plan, antes de que exista una decision.
    capacidad: str
    accion: str
    compuertas: tuple[str, ...]
    tipos: tuple[str, ...]
    permisos: tuple[str, ...]

    def como_dict(self) -> dict:
        # Devuelve la forma canonica que se guarda y se firma en el manifiesto.
        return {
            'capacidad': self.capacidad,
            'accion': self.accion,
            'compuertas': list(self.compuertas),
            'tipos': list(self.tipos),
            'permisos': list(self.permisos),
        }

    @classmethod
    def desde_dict(cls, datos: dict) -> Requerimientos:
        # Reconstruye los requerimientos firmados para compararlos con el catalogo.
        capacidad = datos.get('capacidad')
        accion = datos.get('accion')
        if not isinstance(capacidad, str) or not isinstance(accion, str):
            raise ValueError('los requerimientos no declaran capacidad y accion')
        return cls(
            capacidad=capacidad,
            accion=accion,
            compuertas=tuple(str(x) for x in datos.get('compuertas', [])),
            tipos=tuple(str(x) for x in datos.get('tipos', [])),
            permisos=tuple(str(x) for x in datos.get('permisos', [])),
        )

    def satisfechos_por(self, decision: Politica) -> bool:
        # Una decision satisface el plan si cubre permisos, tipos y compuertas.
        if decision.capacidad != self.capacidad or decision.accion != self.accion:
            return False
        if not set(self.permisos).issubset(set(decision.permisos)):
            return False
        if not set(self.tipos).issubset(set(decision.tipos)):
            return False
        if 'confirmacion' in self.compuertas and not decision.confirmada:
            return False
        return not ('anulacion' in self.compuertas and not decision.forzada)


def requerimientos(capacidad: str, accion: str) -> Requerimientos:
    # Lee del catalogo la autorizacion que exige una accion del ejecutor.
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
    exigidas = tuple(
        nombre for nombre in ('confirmacion', 'anulacion') if compuertas.get(nombre)
    )
    return Requerimientos(
        capacidad=capacidad,
        accion=accion,
        compuertas=exigidas,
        tipos=tuple(definicion.get('tipos') or ()),
        permisos=tuple(registro.get('write_permissions') or ()),
    )


def derivar(
    capacidad: str,
    accion: str,
    confirmada: bool = False,
    forzada: bool = False,
    flags: tuple[str, ...] = (),
) -> Politica:
    # Construye la politica de una accion y falla si falta una compuerta exigida.
    exigencia = requerimientos(capacidad, accion)
    if 'confirmacion' in exigencia.compuertas and not confirmada:
        raise ErrorPolitica(
            f'CONFIRMACION_REQUERIDA: {capacidad} {accion} exige --si'
        )
    if 'anulacion' in exigencia.compuertas and not forzada:
        raise ErrorPolitica(
            f'ANULACION_REQUERIDA: {capacidad} {accion} exige --forzar'
        )
    nombres = set(flags)
    if confirmada:
        nombres.add('si')
    if forzada:
        nombres.add('forzar')
    return Politica(
        capacidad=capacidad,
        accion=accion,
        confirmada=confirmada,
        forzada=forzada,
        flags=tuple(sorted(nombres)),
        permisos=exigencia.permisos,
        tipos=exigencia.tipos,
        compuertas=exigencia.compuertas,
    )
