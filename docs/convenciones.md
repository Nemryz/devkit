# Convenciones

Los identificadores se escriben en español y en minusculas con guion bajo, salvo las clases que usan mayuscula inicial. Ningun identificador coincide con una palabra reservada del lenguaje y se evitan tambien los nombres de funciones integradas.

Las funciones hacen una sola cosa y no superan las cuarenta lineas. No se usan clases abstractas, patrones de repositorio, inyeccion de dependencias ni sistemas de plugins.

Los comentarios se escriben en español, en una linea y explican el motivo de una decision. No repiten lo que el codigo ya dice ni traducen instrucciones evidentes.

Los mensajes al usuario estan en español. Los nombres de los comandos estan en ingles porque son la interfaz publica. La salida por defecto es JSON y los datos van a la salida estandar mientras el progreso va a la salida de error.

Las pruebas usan el sistema de archivos real sobre carpetas temporales. Los mocks se reservan para funciones puras.
