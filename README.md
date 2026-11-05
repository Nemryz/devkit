# devkit

Herramientas internas de mantenimiento para Windows, escritas en Python y pensadas para ejecutarse bajo demanda, sin servicios residentes.

## Estado actual

La fase cero entrega el esqueleto del paquete, el registro de ejecuciones, el modo de solo lectura y el comando doctor. Las herramientas de backup, limpieza, deduplicacion, salud, organizacion, ideas e indice estan implementadas. OCR llega en la fase seis.

## Instalacion

```powershell
uv sync
uv run dev --help
uv tool install --editable .
```

## Comandos

```powershell
dev doctor
dev doctor --formato tabla
dev health
dev backup crear --origen C:\Notas --destino C:\Respaldos --clave clave.txt --etiqueta notas
dev backup verificar C:\Respaldos\20260101-notas --clave clave.txt
dev backup restaurar C:\Respaldos\20260101-notas --destino C:\Restaurado --clave clave.txt
dev backup listar
dev trim escanear C:\Proyectos
dev trim aplicar C:\Proyectos --forzar
dev dedupe escanear C:\Proyectos
dev dedupe aplicar C:\Proyectos --forzar
dev organize plan C:\Descargas
dev organize aplicar --todos C:\Descargas
dev idea crear C:\FutureProjects\notas --titulo "Mi idea" --cuerpo "Contenido"
dev index construir C:\FutureProjects\notas
dev index buscar python
dev nice ejecutar -- python -c "print(1)"
dev --version
```

Doctor comprueba version de Python, dependencias, memoria disponible, espacio libre, carpeta de estado, journal, OneDrive, rutas largas y elevacion. Devuelve JSON por defecto y codigo de salida cero cuando todo esta correcto, uno cuando hay avisos y dos cuando hay errores.

Health informa memoria, disco, bateria, SMART, Defender, actualizaciones, inicio y eventos. Backup crea un archivo cifrado con manifiesto y verificacion. Trim y dedupe limpian caches y duplicados a la papelera de Windows con plan previo. Organize clasifica por extension, firma y año. Idea crea notas Markdown validadas e index las busca con FTS5. Nice ejecuta con prioridad baja y tiempo maximo.

## Reglas del proyecto

El codigo, los comentarios y los mensajes visibles estan en español. Los identificadores no usan palabras reservadas del lenguaje. La salida por defecto es JSON. Toda escritura pasa por el modulo de seguridad y respeta la variable DEVKIT_READONLY. El estado vive en la carpeta local del usuario y nunca dentro del repositorio.

El journal es transaccional (PENDING, RUNNING, COMPLETED, FAILED, INTERRUPTED) y los planes tienen manifiesto firmado para aplicar sin reescanear. Las comprobaciones de salud usan ok, aviso, error y unknown para no fingir salud cuando no hay datos.

## Pruebas

```powershell
uv run pytest
uv run ruff check .
```

## Documentacion

La documentacion de producto vive en la carpeta FutureProjects. Este repositorio guarda el codigo y las decisiones tecnicas.
