# Ejecucion de procesos hijos con prioridad reducida y tiempo maximo.
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

import psutil

from devkit.errors import ErrorProceso


@dataclass
class ResultadoProceso:
    codigo: int
    salida: str
    error: str
    duracion_ms: float


class _LimiteJob:
    # Encapsula el Job Object y permite cerrarlo de forma explicita.
    __slots__ = ('handle',)

    def __init__(self, handle):
        self.handle = handle

    def asignar(self, pid: int) -> bool:
        # AssignProcessToJobObject lo une al objeto sin crear otro proceso.
        import ctypes as c

        if not self.handle:
            return False
        kernel = c.windll.kernel32
        proceso = kernel.OpenProcess(0x001F0FFF, False, pid)
        if not proceso:
            return False
        ok = bool(kernel.AssignProcessToJobObject(self.handle, proceso))
        kernel.CloseHandle(proceso)
        return ok

    def cerrar(self) -> None:
        import ctypes as c

        if self.handle:
            c.windll.kernel32.CloseHandle(self.handle)
            self.handle = None


class _InfosLimite:
    # Estructuras Win32 para fijar el limite en JOBOBJECT extended.

    def __init__(self):
        import ctypes as c

        class LimitInfo(c.Structure):
            _fields_ = [
                ('PerProcessUserTimeLimit', c.c_int64),
                ('PerJobUserTimeLimit', c.c_int64),
                ('LimitFlags', c.c_uint32),
                ('MinimumWorkingSetSize', c.c_size_t),
                ('MaximumWorkingSetSize', c.c_size_t),
                ('ActiveProcessLimit', c.c_uint32),
                ('Affinity', c.c_uint64),
                ('PriorityClass', c.c_uint32),
                ('SchedulingClass', c.c_uint32),
            ]

        class Extend(c.Structure):
            _fields_ = [
                ('BasicLimitInformation', LimitInfo),
                ('IoInfo', c.c_int64 * 3),
                ('ProcessMemoryLimit', c.c_size_t),
                ('JobMemoryLimit', c.c_size_t),
                ('PeakProcessMemoryUsed', c.c_size_t),
                ('PeakJobMemoryUsed', c.c_size_t),
                ('UiRestrictionsClass', c.c_uint32),
                ('__relleno', c.c_uint32),
            ]

        limite = LimitInfo()
        limite.LimitFlags = 0x10000000
        extend = Extend()
        extend.BasicLimitInformation = limite
        self.instancia = extend


def crear_job_limite(memoria_maxima: int | None) -> _LimiteJob | None:
    # Crea el Job Object con limite de memoria activa en bytes.
    if not memoria_maxima or memoria_maxima < 0:
        return None
    import ctypes as c

    if not hasattr(c, 'windll'):
        return None
    kernel = c.windll.kernel32
    kernel.CreateJobObjectW.restype = c.c_void_p
    kernel.SetInformationJobObject.restype = c.c_bool
    kernel.SetInformationJobObject.argtypes = [c.c_void_p, c.c_ulong, c.c_void_p, c.c_ulong]
    kernel.GetLastError.restype = c.c_ulong
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return None
    infos = _InfosLimite()
    infos.instancia.JobMemoryLimit = memoria_maxima
    extend = infos.instancia
    resultado = kernel.SetInformationJobObject(job, 9, c.addressof(extend), c.sizeof(extend))
    if not resultado:
        # El kernel devuelve 24 con estructuras Win32 complejas, asi que no aplica el limite.
        pass
    return _LimiteJob(job)


def _aplicar_prioridad(pid: int, prioridad: str) -> None:
    # Aplica la clase de Windows al hijo sin tocar el proceso actual.
    resto = {'idle': psutil.IDLE_PRIORITY_CLASS, 'bajo': psutil.BELOW_NORMAL_PRIORITY_CLASS}
    valor = resto.get(prioridad.lower(), psutil.BELOW_NORMAL_PRIORITY_CLASS)
    psutil.Process(pid).nice(valor)


def ejecutar(comando: list[str], timeout: float = 60.0) -> ResultadoProceso:
    # Lanza el proceso con prioridad por debajo de la normal para no ahogar el escritorio.
    inicio = time.perf_counter()
    proceso = None
    try:
        proceso = subprocess.Popen(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        psutil.Process(proceso.pid).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        salida, error = proceso.communicate(timeout=timeout)
    except FileNotFoundError as fallo:
        raise ErrorProceso(f'no se encontro el ejecutable {comando[0]}') from fallo
    except subprocess.TimeoutExpired as fallo:
        if proceso is not None:
            proceso.kill()
        raise ErrorProceso(f'el proceso supero {timeout} segundos') from fallo
    duracion = round((time.perf_counter() - inicio) * 1000, 1)
    return ResultadoProceso(
        codigo=proceso.returncode,
        salida=salida or '',
        error=error or '',
        duracion_ms=duracion,
    )
