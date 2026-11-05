# Excepciones propias para que cada fallo tenga un mensaje claro y un codigo estable.
class ErrorBase(Exception):
    codigo = 2


class ErrorConfiguracion(ErrorBase):
    pass


class ErrorIntegridad(ErrorBase):
    pass


class ErrorFormato(ErrorBase):
    pass


class ErrorProceso(ErrorBase):
    pass


class ErrorRuta(ErrorBase):
    pass


class ErrorSoloLectura(ErrorBase):
    codigo = 4


class ErrorRespaldo(ErrorBase):
    pass


class ErrorClave(ErrorBase):
    pass


class ErrorLimpieza(ErrorBase):
    pass


class ErrorDuplicados(ErrorBase):
    pass


class ErrorOrganizar(ErrorBase):
    pass


class ErrorIdea(ErrorBase):
    pass


class ErrorIndex(ErrorBase):
    pass


class ErrorOCR(ErrorBase):
    pass
