# Arquitectura

El paquete se divide en un nucleo compartido y una carpeta de herramientas. El nucleo no contiene logica de negocio y no importa ninguna herramienta.

## Nucleo

El modulo paths resuelve las raices del sistema, la deteccion de OneDrive y las rutas extendidas. El modulo safety concentra el modo de solo lectura, el objeto de plan y la verificacion previa a cualquier escritura. El modulo safety es ademas el guardian centralizado: ejecutar_plan es el unico sitio autorizado para mover a papelera o renombrar. El modulo runlog escribe hitos transaccionales PENDING, RUNNING, COMPLETED, FAILED e INTERRUPTED con id de ejecucion, origen, destino y codigo. El modulo output decide entre JSON y tabla. El modulo proceso lanza hijos con prioridad reducida y Job Object. El modulo sistema encapsula las lecturas del sistema operativo. El modulo markdown parsea frontmatter y revisa enlaces para idea e index.

## Herramientas

Cada herramienta vive en un archivo propio, recibe sus dependencias por parametro y devuelve estructuras simples. La interfaz de linea de comandos solo traduce argumentos y codigos de salida, de modo que las pruebas puedan llamar a la logica sin levantar el proceso completo.

## Estado

El estado vive en la carpeta local del perfil del usuario. El journal es la fuente de verdad y se escribe antes de cada accion destructiva. Las bases SQLite son caches reconstruibles y nunca sustituyen al journal. Los planes persistentes viven en planes con firma SHA-256 del manifiesto para aplicar sin reescanear el arbol, con estado pendiente, aplicado o fallido.

## Flujo de una operacion destructiva

La herramienta construye un plan con las acciones previstas. Si el modo de solo lectura esta activo, la operacion se rechaza con codigo cuatro. Si el plan se aprueba, se firma con SHA-256, se guarda el manifiesto y cada accion se registra en el journal antes de ejecutarse. Un fallo a mitad deja el estado marcado como inconsistente y permite revertir lo aplicado. La validacion del arbol comprueba que cada archivo sigue existiendo con mismo tamano, mtime y contenido antes de moverlo.

## Salud sin falsos ok

Health distingue ok, aviso, error y unknown. Cuando no hay datos (wmic no disponible, sin acceso al registro), el estado es unknown y no se interpreta como sano. El codigo de salida 1 significa aviso, 2 error y 0 solo cuando todo es ok o unknown sin aviso.
