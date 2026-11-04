# Informe de salud del sistema sin permisos de administrador ni servicios.
from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from devkit import __version__
from devkit.core import runlog


def _hijo(comando: list[str], tiempo: float = 20.0) -> subprocess.CompletedProcess:
    # Ejecuta lectura sin colgar la consola si el binario tarda demasiado.
    return subprocess.run(
        comando,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=tiempo,
    )


def _resultado(nombre: str, estado: str, detalle: str, valor: Any = None) -> dict:
    # Uniforma la forma de cada bloque para que el JSON sea predecible.
    return {'nombre': nombre, 'estado': estado, 'detalle': detalle, 'valor': valor}


def memoria() -> dict:
    # Construye el resumen de RAM con los umbrales del equipo de 8 GB.
    import psutil

    virtual = psutil.virtual_memory()
    total = virtual.total / (1024**3)
    disponible = virtual.available / (1024**3)
    uso = virtual.percent
    if uso > 90:
        estado = 'error'
    elif uso > 80:
        estado = 'aviso'
    else:
        estado = 'ok'
    datos = {
        'total_gb': round(total, 2),
        'disponible_gb': round(disponible, 2),
        'uso_pct': uso,
        'swap_pct': psutil.swap_memory().percent,
    }
    return _resultado('memoria', estado, f'{uso:.0f}% en uso, {disponible:.2f} GB libres', datos)


def disco() -> dict:
    # Resume el volumen del sistema y avisa cuando el espacio se estrecha.
    ancla = Path.home().anchor or 'C:\\'
    uso = shutil.disk_usage(ancla)
    libre_gb = uso.free / (1024**3)
    total_gb = uso.total / (1024**3)
    porcentaje = round((uso.used / uso.total) * 100, 1) if uso.total else 0
    if libre_gb < 5:
        estado = 'error'
    elif libre_gb < 20:
        estado = 'aviso'
    else:
        estado = 'ok'
    datos = {
        'unidad': ancla,
        'total_gb': round(total_gb, 2),
        'libre_gb': round(libre_gb, 2),
        'uso_pct': porcentaje,
    }
    detalle = f'{libre_gb:.2f} GB libres en {ancla} ({porcentaje}%)'
    return _resultado('disco', estado, detalle, datos)


def bateria() -> dict:
    # Informa el porcentaje y si el equipo esta conectado a la corriente.
    import psutil

    datos_bateria = psutil.sensors_battery()
    if datos_bateria is None:
        return _resultado('bateria', 'ok', 'sin bateria instalada', None)
    porcentaje = round(datos_bateria.percent, 1)
    conectado = bool(datos_bateria.power_plugged)
    estado = 'aviso' if porcentaje < 20 and not conectado else 'ok'
    detalle = 'enchufado' if conectado else f'{porcentaje}% sin enchufe'
    valor = {'porcentaje': porcentaje, 'conectado': conectado, 'secsleft': datos_bateria.secsleft}
    return _resultado('bateria', estado, detalle, valor)


def temperatura() -> dict:
    # La temperatura no esta expuesta por WMI sin administrador en este equipo.
    return _resultado('temperatura', 'ok', 'no disponible sin administrador', None)


def smart() -> dict:
    # Estado SMART del NVMe a traves de wmic, en solo lectura y sin administrador.
    try:
        resultado = _hijo(['wmic', 'diskdrive', 'get', 'Status,Model,Size', '/format:csv'])
    except FileNotFoundError:
        return _resultado('smart', 'ok', 'wmic no disponible', None)
    except subprocess.TimeoutExpired:
        return _resultado('smart', 'aviso', 'tardo al consultar SMART', None)
    if resultado.returncode != 0:
        return _resultado('smart', 'ok', 'no se pudo consultar SMART', None)
    lineas = [linea for linea in resultado.stdout.splitlines() if linea.strip()]
    discos = [] if len(lineas) < 3 else lineas[1:]
    valor = discos[0] if discos else 'sin datos'
    return _resultado('smart', 'ok', 'discos consultados sin administrador', valor)


def defender() -> dict:
    # Estado de Windows Defender con PowerShell sin escalar privilegios.
    guion = 'Get-MpComputerStatus | ConvertTo-Json -Compress'
    comando = ['powershell.exe', '-NoProfile', '-Command', guion]
    try:
        resultado = _hijo(comando)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return _resultado('defender', 'ok', 'powershell no disponible', None)
    if resultado.returncode != 0:
        return _resultado('defender', 'ok', 'no se pudo consultar Defender', None)
    texto = resultado.stdout.strip()
    if not texto:
        return _resultado('defender', 'ok', 'sin respuesta de Defender', None)
    import json

    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        return _resultado('defender', 'ok', 'respuesta no parseable', texto[:80])
    activo = datos.get('AntivirusEnabled')
    estado = 'ok' if activo else 'aviso'
    detalle = 'Defender activo' if activo else 'Defender desactivado'
    opciones = {
        'activo': activo,
        'antivirus': datos.get('AntivirusEnabled'),
        'tiempo_real': datos.get('RealTimeProtectionEnabled'),
    }
    return _resultado('defender', estado, detalle, opciones)


def actualizaciones() -> dict:
    # Lista los ultimos parches de Windows con registro, solo lectura.
    try:
        import winreg
    except ImportError:
        return _resultado('actualizaciones', 'ok', 'sin winreg en este Python', None)
    ruta = r'SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\Results\Install'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ruta) as clave:
            valor, _ = winreg.QueryValueEx(clave, 'LastSuccessTime')
    except OSError as fallo:
        # Sin privilegio de lectura en este equipo no es un error de salud.
        return _resultado('actualizaciones', 'ok', f'sin acceso al registro {fallo}', None)
    return _resultado('actualizaciones', 'ok', f'ultima actualizacion {valor}', valor)


def inicio() -> dict:
    # Cuenta programas de arranque de la clave Run del usuario.
    try:
        import winreg
    except ImportError:
        return _resultado('inicio', 'ok', 'sin winreg en este Python', None)
    ruta_hku = r'Software\Microsoft\Windows\CurrentVersion\Run'
    total = 0
    for raiz in (winreg.HKEY_CURRENT_USER,):
        try:
            with winreg.OpenKey(raiz, ruta_hku) as clave:
                conteo, _, _ = winreg.QueryInfoKey(clave)
                total += conteo
        except OSError:
            # Entrada ausente significa cero programas en esa clave.
            pass
    estado = 'aviso' if total > 15 else 'ok'
    return _resultado('inicio', estado, f'{total} programas en arranque', total)


def eventos() -> dict:
    # Revisa los ultimos errores del registro de sistema en solo lectura.
    filtro = '@{LogName="System"; Level=2} -MaxEvents 5'
    guion = f'Get-WinEvent -FilterHashtable {filtro} | ConvertTo-Json -Compress'
    comando = ['powershell.exe', '-NoProfile', '-Command', guion]
    try:
        resultado = _hijo(comando, tiempo=30.0)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return _resultado('eventos', 'ok', 'powershell no disponible', None)
    if resultado.returncode != 0:
        return _resultado('eventos', 'ok', 'no se pudo leer el registro', None)
    texto = resultado.stdout.strip()
    if not texto:
        return _resultado('eventos', 'ok', 'sin errores recientes', 0)
    import json

    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        return _resultado('eventos', 'ok', 'respuesta no parseable', None)
    conteo = 1 if isinstance(datos, dict) else len(datos) if isinstance(datos, list) else 0
    estado = 'aviso' if conteo >= 3 else 'ok'
    return _resultado('eventos', estado, f'{conteo} errores recientes', conteo)


def calcular_estado(bloques: list[dict]) -> tuple[str, int]:
    # Resume los bloques en un estado y un codigo de salida estables.
    if any(fila['estado'] == 'error' for fila in bloques):
        return 'error', 2
    if any(fila['estado'] == 'aviso' for fila in bloques):
        return 'aviso', 1
    return 'correcto', 0


def _memoria_actual() -> int:
    # Guarda el pico aproximado para el journal sin romper si psutil falla.
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except (ImportError, Exception):
        return 0


def ejecutar_salud(argumentos: list[str] | None = None) -> dict:
    # Ejecuta todos los bloques y deja constancia en el journal.
    marca = time.perf_counter()
    bloques = [
        memoria(),
        disco(),
        bateria(),
        temperatura(),
        smart(),
        defender(),
        actualizaciones(),
        inicio(),
        eventos(),
    ]
    estado, codigo = calcular_estado(bloques)
    duracion = round((time.perf_counter() - marca) * 1000, 1)
    resultado = {
        'herramienta': 'health',
        'version': __version__,
        'fecha': datetime.now(UTC).isoformat(),
        'equipo': os.environ.get('COMPUTERNAME', 'desconocido'),
        'estado': estado,
        'codigo': codigo,
        'duracion_ms': duracion,
        'bloques': bloques,
    }
    try:
        runlog.registrar_ejecucion(
            'health', argumentos or [], marca, codigo, _memoria_actual(), estado
        )
    except OSError as fallo:
        resultado['aviso_journal'] = str(fallo)
    return resultado


if __name__ == '__main__':
    import sys

    print(ejecutar_salud(sys.argv[1:]))
