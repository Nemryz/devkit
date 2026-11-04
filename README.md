# devkit

Herramientas internas de mantenimiento para Windows, escritas en Python y pensadas para ejecutarse bajo demanda, sin servicios residentes.

## Estado actual

La fase cero entrega el esqueleto del paquete, el registro de ejecuciones, el modo de solo lectura y el comando doctor. Las herramientas de backup, limpieza, deduplicacion, salud, organizacion, ideas y OCR llegan en fases posteriores.

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
dev --version
```

Doctor comprueba version de Python, dependencias, memoria disponible, espacio libre, carpeta de estado, journal, OneDrive, rutas largas y elevacion. Devuelve JSON por defecto y codigo de salida cero cuando todo esta correcto, uno cuando hay avisos y dos cuando hay errores.

## Reglas del proyecto

El codigo, los comentarios y los mensajes visibles estan en español. Los identificadores no usan palabras reservadas del lenguaje. La salida por defecto es JSON. Toda escritura pasa por el modulo de seguridad y respeta la variable DEVKIT_READONLY. El estado vive en la carpeta local del usuario y nunca dentro del repositorio.

## Pruebas

```powershell
uv run pytest
uv run ruff check .
```

## Documentacion

La documentacion de producto vive en la carpeta FutureProjects. Este repositorio guarda el codigo y las decisiones tecnicas.
