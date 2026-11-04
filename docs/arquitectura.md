# Arquitectura

El paquete se divide en un nucleo compartido y una carpeta de herramientas. El nucleo no contiene logica de negocio y no importa ninguna herramienta.

## Nucleo

El modulo paths resuelve las raices del sistema, la deteccion de OneDrive y las rutas extendidas. El modulo safety concentra el modo de solo lectura, el objeto de plan y la verificacion previa a cualquier escritura. El modulo runlog escribe una linea JSON por ejecucion en el journal local. El modulo output decide entre JSON y tabla. El modulo proceso lanza hijos con prioridad reducida. El modulo sistema encapsula las lecturas del sistema operativo.

## Herramientas

Cada herramienta vive en un archivo propio, recibe sus dependencias por parametro y devuelve estructuras simples. La interfaz de linea de comandos solo traduce argumentos y codigos de salida, de modo que las pruebas puedan llamar a la logica sin levantar el proceso completo.

## Estado

El estado vive en la carpeta local del perfil del usuario. El journal es la fuente de verdad y se escribe antes de cada accion destructiva. Las bases SQLite son caches reconstruibles y nunca sustituyen al journal.

## Flujo de una operacion destructiva

La herramienta construye un plan con las acciones previstas. Si el modo de solo lectura esta activo, la operacion se rechaza con codigo cuatro. Si el plan se aprueba, cada accion se registra en el journal antes de ejecutarse. Un fallo a mitad deja el estado marcado como inconsistente y permite revertir lo aplicado.
