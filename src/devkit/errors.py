# Excepciones propias para que cada fallo tenga un mensaje claro y un codigo estable.
class ErrorBase(Exception):  # noqa: N818
    codigo = 2


class ErrorConfiguracion(ErrorBase):
    pass


class ErrorFormato(ErrorBase):
    pass


class ErrorProceso(ErrorBase):
    pass


class ErrorRuta(ErrorBase):
    pass


class ErrorSoloLectura(ErrorBase):
    codigo = 4
