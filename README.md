# devkit

Herramientas internas de mantenimiento para Windows, escritas en Python y pensadas para ejecutarse bajo demanda, sin servicios residentes. El objetivo es tener un pequeño entorno de mantenimiento local con capacidades especializadas que comparten un núcleo común de seguridad, registro y salida.

## Instalación global

El comando `dev` se instala una sola vez y queda disponible desde cualquier carpeta de PowerShell o CMD. No depende de estar dentro del repositorio.

### PowerShell

```powershell
uv tool install --editable .
dev --version
```

### CMD

```cmd
uv tool install --editable .
dev --version
```

### Verificar que funciona desde cualquier carpeta

```powershell
cd C:\
dev --version
dev doctor
```

Si `dev` no responde, el directorio de ejecutables no está en el PATH. Agregarlo manualmente:

```powershell
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";$env:USERPROFILE\.local\bin", "User")
```

Después de agregar el PATH, reiniciar la consola. Para automatizar la instalación completa, usar el script incluido:

```powershell
.\install.ps1
```

El script sincroniza dependencias, instala el paquete, descubre el directorio de ejecutables de uv dinámicamente y configura el PATH del usuario.

### Instalación empaquetada (producción)

Por defecto, `install.ps1` instala el paquete empaquetado (no editable). El repositorio fuente puede moverse o eliminarse sin romper la instalación:

```powershell
.\install.ps1
```

Para desarrollo (editable):

```powershell
.\install.ps1 --editable
```

### Reinstalar o actualizar

```powershell
cd <ruta-del-repositorio>
uv tool install --editable . --force
```

## Comandos

Todos los comandos devuelven JSON por defecto. Con `--formato tabla` se obtiene salida legible por personas. Los códigos de salida son 0 (correcto), 1 (aviso), 2 (error) y 4 (solo lectura).

### doctor

Comprueba el entorno antes de ejecutar cualquier otra herramienta.

```powershell
dev doctor
dev doctor --formato tabla
```

Revisa versión de Python, dependencias del núcleo, memoria disponible, espacio libre, carpeta de estado, journal, OneDrive, rutas largas y elevación.

### health

Genera un informe de salud del equipo sin permisos de administrador ni servicios.

```powershell
dev health
dev health --formato tabla
```

Bloques: memoria, disco, batería, temperatura, SMART, Defender, actualizaciones, inicio y eventos. Distingue cuatro estados: ok, aviso, error y unknown. Cuando no hay datos (wmic no disponible, sin acceso al registro), el estado es unknown y no se interpreta como sano.

### backup

Respaldos cifrados con manifiesto de hashes y verificación obligatoria.

```powershell
dev backup crear --origen C:\Notas --destino D:\Respaldos --clave clave.txt --etiqueta notas
dev backup verificar D:\Respaldos\20260101-notas --clave clave.txt
dev backup restaurar D:\Respaldos\20260101-notas --destino C:\Restaurado --clave clave.txt
dev backup listar
dev backup listar --destino D:\Respaldos
```

Crea un archivo 7z con cifrado AES-256 y cabecera cifrada. Escribe un manifiesto con SHA-256 por archivo. Verifica extrayendo en una carpeta temporal y comparando hashes. La restauración comprueba integridad al terminar.

### trim

Limpieza de caches y artefactos con plan previo, papelera de Windows y journal transaccional.

```powershell
dev trim escanear C:\Proyectos
dev trim escanear C:\Proyectos --incluir-venv
dev trim aplicar C:\Proyectos --forzar
dev trim aplicar C:\Proyectos --forzar --edad-dias 14
```

Detecta carpetas de cache (__pycache__, .pytest_cache, .ruff_cache, .mypy_cache, build, dist, htmlcov, node_modules) y archivos temporales (.log, .pyc, .pyo, .tmp). Excluye .git, src y tests. Respeta DEVKIT_READONLY. El plan incluye manifiesto firmado para aplicar sin reescanear el árbol.

### dedupe

Detección de duplicados exactos con BLAKE3, plan previo y papelera de Windows.

```powershell
dev dedupe escanear C:\Proyectos
dev dedupe escanear C:\Proyectos --edad-dias 60
dev dedupe aplicar C:\Proyectos --forzar
```

Agrupa por tamaño, calcula prehash parcial (primeros 8 KB) y hash completo con BLAKE3. Conserva la ruta más corta y, a igualdad, el archivo más antiguo. Incluye resumen por extensión y filtro de OneDrive. El plan incluye manifiesto firmado para aplicar sin reescanear.

### organize

Clasificación por extensión, firma binaria y año, con confirmación archivo por archivo.

```powershell
dev organize plan C:\Descargas
dev organize aplicar --todos C:\Descargas
dev organize aplicar --por-archivo C:\Descargas
```

Detecta el tipo real por magic number (JPEG, PNG, PDF, ZIP, MP3, MP4, etc.) y cae a la extensión si no hay firma. Organiza en `Organizados/<año>/<tipo>/<nombre>`. Resuelve colisiones con `_2`, `_3`. El plan incluye manifiesto firmado con origen, destino, tamaño y mtime.

Para aplicar un manifiesto ya guardado sin reescanear el árbol:

```powershell
dev organize plan C:\Descargas
dev organize aplicar --todos C:\Descargas --plan <ruta-del-manifiesto>.json
```

### idea

Notas Markdown con frontmatter validado y revisión de enlaces.

```powershell
mkdir C:\Notas
dev idea crear C:\Notas --titulo "Mi idea" --cuerpo "Contenido" --etiqueta devkit --estado activo
dev idea revisar C:\Notas
dev idea listar C:\Notas
dev idea listar C:\Notas --estado activo
```

Crea archivos con frontmatter (titulo, creado, etiquetas, estado, origen). Valida campos obligatorios y formato de fecha. Revisa enlaces rotos `[texto](ruta.md)`. Avisa si el título ya existe. El campo origen admite manual, ocr, scrape e importado. La carpeta de notas debe existir antes de usar idea, porque ninguna acción la crea por ti y el error por carpeta ausente es explícito.

### index

Índice SQLite con FTS5 sobre las notas Markdown. Cada espacio de trabajo tiene su propio índice aislado.

```powershell
dev index construir C:\Notas
dev index buscar python
dev index buscar python --raiz C:\Notas --limite 5
dev index actualizar C:\Notas
dev index exportar C:\Notas\export.json --raiz C:\Notas
```

Construye un índice FTS5 (tokenize unicode61) sobre título y cuerpo en `<raiz>/.devkit/index.sqlite`. Permite buscar con fragmentos resaltados. Actualiza de forma incremental por mtime. Exporta a JSON. La raíz del índice se resuelve por precedencia: `--raiz` explícito > variable `DEVKIT_WORKSPACE` > directorio actual. Si no existe el índice en esa raíz, avisa con `ejecuta index construir` y no consulta ningún índice global de forma silenciosa. Cada raíz edita y actualiza su propio `.devkit`; si la raíz no permite crear esa carpeta, falla con error explícito en lugar de guardar el índice en otro sitio.

### nice

Ejecuta hijos con prioridad baja y registro de memoria.

```powershell
dev nice ejecutar -- python -c "print(1)"
dev nice ejecutar --prioridad idle --tiempo 300 -- python script.py
dev nice ejecutar --memoria-mb 512 -- python pesado.py
```

Aplica BELOW_NORMAL_PRIORITY_CLASS al proceso hijo. Tiempo máximo configurable. Mide memoria pico con un hilo mientras corre. Si SetInformationJobObject devuelve 24, cierra el Job y sigue sin límite antes que romper. Registra pico en el journal.

### ocr

OCR en solo lectura con Tesseract y PyMuPDF.

```powershell
dev ocr escanear C:\Documentos
dev ocr escanear C:\Documentos --idioma spa
dev ocr exportar C:\Documentos --destino C:\OCR
```

Extrae texto de imágenes y PDFs con Tesseract 5.5.3. Renderiza PDFs a 150 dpi con PyMuPDF. Calcula confianza media, mínima y conteo de palabras por página. Exporta notas con origen ocr listas para idea e index. No mueve, borra ni clasifica archivos. Respeta DEVKIT_READONLY.

## Perfiles de almacenamiento

DevKit resuelve sus ubicaciones de estado según un perfil activo. La precedencia es: variables de entorno > config.toml > perfil activo > platformdirs.

### Perfiles disponibles

| Perfil | Descripción |
|--------|-------------|
| global | Estado en `%LOCALAPPDATA%\devkit`, configuración en `%APPDATA%\devkit`, cache en platformdirs (predeterminado) |
| portable | Estado y configuración junto al paquete instalado, incluida la cache y los planes |
| custom | Rutas de `[storage]` en config.toml; exige `state` y coloca cache, planes y journal dentro de esa ruta |
| temporary | Todo el estado y la cache en la carpeta temporal del sistema, sin persistencia entre sesiones |

Resolve con fail loud: si el perfil es custom y falta `state` en config.toml, o si el archivo de configuración existe pero está dañado o con tipos inválidos, el error es explícito (`ErrorConfiguracion`) y no hay fallback silencioso al perfil global. La carpeta de configuración se fija con `DEVKIT_CONFIG` o con `DEVKIT_PERFIL=portable`/`temporary` y nunca a través del propio config.toml, porque el archivo no puede resolver el directorio donde vive él mismo. El campo `storage.config` de configuraciones antiguas se ignora sin romper la migración.

### Variables de entorno

| Variable | Efecto |
|----------|--------|
| DEVKIT_ESTADO | Redirige la carpeta de estado |
| DEVKIT_CONFIG | Redirige la carpeta de configuración |
| DEVKIT_CACHE | Redirige la carpeta de cache |
| DEVKIT_PLANES | Redirige la carpeta de planes |
| DEVKIT_TEMP | Redirige la carpeta temporal |
| DEVKIT_PROYECTOS | Redirige la carpeta de proyectos |
| DEVKIT_WORKSPACE | Define el espacio de trabajo activo |
| DEVKIT_PERFIL | Fuerza un perfil (global, portable, custom, temporary) |
| DEVKIT_READONLY | Activa modo de solo lectura (1, true, si, yes, on) |
| DEVKIT_CLAVE | Clave para respaldos cifrados |

### Ejemplo de config.toml

```toml
raices = []
retencion_dias = 180
idioma = "es"
perfil = "global"

[storage]
state = "D:/DevKit/state"
cache = "D:/DevKit/cache"
plans = "D:/DevKit/plans"
journal = "D:/DevKit/journal"
```

Cada campo de `[storage]` es opcional y respeta la misma precedencia: la variable de entorno correspondiente gana, luego config.toml, luego el perfil activo. El campo `perfil` dentro de `[storage]` tiene prioridad sobre el `perfil` de nivel superior cuando ambos existen.

## Espacios de trabajo

Cada espacio de trabajo tiene su propio índice SQLite en `<raiz>/.devkit/index.sqlite`. Dos espacios de trabajo no contaminan sus índices. Mover la carpeta mueve el índice con ella, porque vive dentro de la raíz y no en un estado global.

```powershell
dev index construir C:\Proyectos\A
dev index construir C:\Proyectos\B
dev index buscar python --raiz C:\Proyectos\A
```

Con `DEVKIT_WORKSPACE` activo, los comandos de index resuelven esa raíz cuando no se pasa `--raiz`. La búsqueda en un espacio no devuelve resultados de otro. El índice es rebuildable y no sincroniza con OneDrive. Si la raíz de notas es de solo lectura y no permite crear `.devkit`, el comando falla con error explícito y no guarda el índice en otra ubicación sin avisar.

## Escenarios de uso

### Escenario 1: equipo lento con poca RAM

El equipo tiene 8 GB en single channel y menos de 1,5 GB libres. El objetivo es recuperar rendimiento sin reinstalar.

```powershell
dev doctor
dev health --formato tabla
dev trim escanear C:\Proyectos
dev trim aplicar C:\Proyectos --forzar
dev dedupe escanear C:\Proyectos
dev dedupe aplicar C:\Proyectos --forzar
```

Doctor diagnostica el entorno. Health informa memoria, disco y eventos. Trim libera caches. Dedupe elimina duplicados. El journal registra cada acción para poder revertir.

### Escenario 2: carpeta de descargas desordenada

La carpeta de descargas tiene archivos de varios tipos y años mezclados.

```powershell
dev organize plan C:\Descargas
dev organize plan C:\Descargas --formato tabla
dev organize aplicar --todos C:\Descargas
```

Organize detecta el tipo real por magic number (no solo extensión), propone `Organizados/<año>/<tipo>/<nombre>` y resuelve colisiones. El plan se muestra antes de mover. Sin `--todos` ni `--por-archivo` no se aplica nada.

### Escenario 3: respaldo antes de reinstalar

Antes de reinstalar Windows, respaldar documentos importantes.

```powershell
dev backup crear --origen C:\Notas --destino D:\Respaldos --clave clave.txt --etiqueta notas
dev backup verificar D:\Respaldos\20260101-notas --clave clave.txt
dev backup listar --destino D:\Respaldos
```

El respaldo es un archivo 7z con AES-256 y cabecera cifrada. El manifiesto contiene SHA-256 por archivo. La verificación extrae en temporal y compara. Para restaurar:

```powershell
dev backup restaurar D:\Respaldos\20260101-notas --destino C:\Restaurado --clave clave.txt
```

### Escenario 4: notas y búsqueda

Crear, validar e indexar notas Markdown para buscarlas después.

```powershell
mkdir C:\Notas
dev idea crear C:\Notas --titulo "Proyecto devkit" --cuerpo "Herramientas de mantenimiento" --etiqueta devkit --estado activo
dev idea revisar C:\Notas
dev idea listar C:\Notas --estado activo
dev index construir C:\Notas
dev index buscar mantenimiento --raiz C:\Notas
dev index buscar devkit --raiz C:\Notas --limite 5
```

Idea valida frontmatter y revisa enlaces. Index construye FTS5 y devuelve fragmentos resaltados. Con la carpeta de notas como directorio de trabajo o con `DEVKIT_WORKSPACE=C:\Notas`, buscar sin `--raiz` resuelve esa raíz por precedencia. Para actualizar después de añadir notas:

```powershell
dev index actualizar C:\Notas
```

### Escenario 5: procesar archivos pesados sin bloquear el escritorio

Ejecutar un script largo sin ahogar el equipo.

```powershell
dev nice ejecutar -- python script_largo.py --tiempo 300
dev nice ejecutar --prioridad idle -- python indexar.py
```

El hijo corre con BELOW_NORMAL_PRIORITY_CLASS. El tiempo máximo evita procesos colgados. La memoria pico se registra en el journal.

### Escenario 6: digitalizar documentos escaneados

Extraer texto de PDFs e imágenes escaneadas.

```powershell
dev ocr escanear C:\Documentos
dev ocr exportar C:\Documentos --destino C:\OCR
dev index construir C:\OCR
dev index buscar contrato
```

OCR es solo lectura: no mueve, borra ni clasifica. Genera notas con origen ocr listas para indexar.

### Escenario 7: ejecutar desde cualquier carpeta

DevKit no depende de dónde reside. Funciona desde cualquier directorio.

```powershell
cd C:\
dev --version
dev doctor
dev health
```

### Escenario 8: dos espacios de trabajo sin contaminación

Dos proyectos con el mismo nombre en diferentes unidades no mezclan sus índices.

```powershell
dev index construir D:\Proyectos\A\notas
dev index construir E:\Proyectos\A\notas
dev index buscar python --raiz D:\Proyectos\A\notas
```

### Escenario 9: reinstalar sin perder datos

La instalación empaquetada permite mover o eliminar el repositorio fuente sin perder configuración ni estado.

```powershell
.\install.ps1
# Mover el repositorio a otra carpeta
# dev sigue funcionando
dev --version
```

## Análisis técnico por herramienta

### backup

Flujo interno: valida orígenes y destino, recorre sin seguir enlaces, calcula SHA-256 por archivo, empaqueta en tar, comprime con 7z (AES-256, cabecera cifrada), escribe manifiesto JSON, limpia el tar temporal.

Seguridad: la contraseña se pasa por entrada estándar, nunca por línea de comandos. Verificación extrae en carpeta temporal y compara hashes. Restauración comprueba integridad al terminar. El plan se firma con SHA-256.

Casos de uso: respaldo antes de reinstalar, copia a USB, migración entre equipos.

### trim

Flujo interno: recorre sin seguir enlaces, detecta carpetas y archivos por nombre y sufijo, filtra por antigüedad, aplica tope de bytes por pasada, construye plan, ejecuta moviendo a papelera.

Seguridad: excluye .git, src, tests. No sigue enlaces simbólicos. Respeta DEVKIT_READONLY. El plan se firma con SHA-256 cubriendo origen, tamaño, mtime y contenido (hash por archivo) de cada fila, y se guarda en planes con estado pendiente, aplicado o fallido. Antes de tocar nada valida que cada elemento sigue existiendo con el mismo tamaño, mtime y contenido, con destino solo para movimientos. Si el árbol cambia entre plan y aplicación, se aborta con aviso.

Casos de uso: limpiar caches después de desarrollo, liberar espacio antes de backup, mantenimiento periódico.

### dedupe

Flujo interno: agrupa por tamaño (descarta únicos), prehash parcial (8 KB), hash completo con BLAKE3, selecciona conservar por ruta más corta y fecha más antigua, construye plan con tope, ejecuta moviendo a papelera.

Seguridad: excluye .git, src, tests. No sigue enlaces. Filtra OneDrive por defecto. El plan se firma con SHA-256 cubriendo origen, tamaño, mtime y contenido, y se guarda con su estado. Antes de aplicar valida que no haya cambio de origen, tamaño, mtime ni contenido, y aborta con aviso si el árbol cambió.

Casos de uso: liberar espacio en discos llenos, limpiar carpetas de fotos duplicadas, mantenimiento de archivos de trabajo.

### organize

Flujo interno: recorre sin seguir enlaces, detecta tipo por magic number y extensión, calcula año por mtime, propone ruta Organizados/<año>/<tipo>/<nombre>, resuelve colisiones, construye plan, ejecuta moviendo.

Seguridad: excluye .git, src, tests. No sigue enlaces. Respeta DEVKIT_READONLY. El plan se firma con SHA-256 sobre origen, destino, tamaño, mtime y contenido. `plan` guarda el manifiesto persistente y `aplicar --plan` lo consume sin reescanear; sin plan previo, generar, guardar, validar y aplicar es un solo flujo. Valida cada movimiento contra destino ocupado y no sobrescribe nada. Sin --todos ni --por-archivo no se aplica nada. Sin tty, --por-archivo aborta. Pasa por el guardián centralizado.

Casos de uso: organizar descargas, clasificar por año y tipo, preparar archivos para archivo.

### health

Flujo interno: ejecuta 9 bloques (memoria, disco, batería, temperatura, SMART, Defender, actualizaciones, inicio, eventos). Cada bloque devuelve estado ok, aviso, error o unknown. Resume en estado general y código de salida.

Seguridad: solo lectura, sin administrador, sin servicios. No modifica nada. Unknown cuando no hay datos para no fingir salud.

Casos de uso: diagnóstico rápido, verificar estado antes de operaciones pesadas, monitorización manual.

### idea

Flujo interno: crea notas con frontmatter validado, revisa enlaces rotos, lista por estado. Genera nombre con slug y fecha. Avisa duplicados. El campo origen admite manual, ocr, scrape e importado.

Seguridad: respeta DEVKIT_READONLY. Solo escribe en la raíz indicada. Valida campos obligatorios.

Casos de uso: capturar ideas, documentar proyectos, mantener notas organizadas.

### index

Flujo interno: construye SQLite con FTS5 (unicode61) sobre título y cuerpo en `<raiz>/.devkit/index.sqlite`. Busca con snippet. Actualiza por mtime. Exporta a JSON. La raíz se resuelve por precedencia: `--raiz` > `DEVKIT_WORKSPACE` > directorio actual, sin consulta a ningún índice global si esa raíz no tiene índice.

Seguridad: el índice vive en el espacio de trabajo, no en el perfil global, y la carpeta mueve el índice con ella. Es rebuildable. La base abre en WAL y las escrituras incrementales van en una transacción inmediata (`BEGIN IMMEDIATE`), de modo que dos procesos que actualizan a la vez se serializan y no chocan contra el UNIQUE de rutas. Respeta DEVKIT_READONLY.

Casos de uso: buscar en notas, encontrar referencias, exportar para revisión.

### nice

Flujo interno: lanza proceso con subprocess, aplica prioridad, mide memoria pico con hilo mientras corre, captura stdout/stderr, mata si timeout, cierra Job.

Seguridad: mata al hijo si falla la prioridad. Tiempo máximo obligatorio. Job Object para límite de memoria: si el kernel rechaza fijar el límite, el Job se cierra y el proceso sigue solo con prioridad baja y tiempo máximo, y el pico de memoria queda registrado en el journal como observación, no como impostación. Registra pico en el journal.

Casos de uso: ejecutar scripts largos sin bloquear, procesar archivos pesados, tareas de OCR.

### ocr

Flujo interno: recorre sin seguir enlaces, detecta imágenes y PDFs, renderiza PDFs a 150 dpi con PyMuPDF, ejecuta Tesseract, calcula confianza por palabra y página, genera notas con origen ocr.

Seguridad: solo lectura, no mueve/borra/clasifica. Respeta DEVKIT_READONLY. Tiempo por documento vía nice. El binario de Tesseract se verifica antes de usarlo.

Casos de uso: digitalizar documentos escaneados, extraer texto de PDFs, preparar notas para indexar.

## Núcleo compartido

El núcleo concentra lo que comparten todas las herramientas y no contiene lógica de negocio.

| Módulo | Responsabilidad |
|--------|-----------------|
| paths.py | Rutas del sistema, detección de OneDrive, rutas extendidas, perfiles de almacenamiento, platformdirs |
| safety.py | Modo solo lectura, guardián centralizado, planes persistentes firmados con SHA-256 |
| runlog.py | Journal transaccional (PENDING, RUNNING, COMPLETED, FAILED, INTERRUPTED) con espacio de trabajo, id de plan y recuperación de ejecuciones interrumpidas |
| output.py | JSON y tabla legible |
| proceso.py | Procesos con prioridad baja y Job Object |
| sistema.py | Información del sistema operativo |
| config.py | Configuración persistente en TOML con sección storage y errores explícitos ante archivo dañado |
| errors.py | Excepciones con códigos de salida estables |
| markdown.py | Parser de frontmatter, slugify, enlaces rotos |

## Reglas del proyecto

El código, los comentarios y los mensajes visibles están en español. Los identificadores no usan palabras reservadas del lenguaje. La salida por defecto es JSON. Toda escritura pasa por el módulo de seguridad y respeta la variable DEVKIT_READONLY.

Las rutas del estado se resuelven por capas: variable de entorno, config.toml en su sección storage, perfil activo y raíces del sistema. El perfil custom exige `state` en config.toml y un config.toml dañado o con tipos inválidos falla con error explícito, nunca con un fallback silencioso al perfil global.

El journal es transaccional y los planes tienen manifiesto firmado para aplicar sin reescanear. La firma SHA-256 cubre tamaño, mtime y contenido de cada acción y se revalida justo antes de ejecutarla, por lo que un cambio de contenido que preserve tamaño y mtime se detecta. Esa firma es integridad accidental, no autenticación: detecta cambios involuntarios en el árbol, no manipulación maliciosa del plan, que podría recalcular el hash. Si la manipulación maliciosa entra en el modelo de amenazas, hará falta HMAC con clave secreta o un mecanismo equivalente. Queda una ventana residual de carrera entre la validación de un archivo y su movimiento (TOCTOU) que se reduce revalidando cada acción en el mismo instante en que se ejecuta. Las comprobaciones de salud usan ok, aviso, error y unknown para no fingir salud cuando no hay datos.

DevKit no depende de dónde reside, solo de los recursos que necesita para ejecutar sus operaciones. Las herramientas no presuponen que el directorio de trabajo es el directorio de instalación. Los datos de un espacio de trabajo no contaminan los de otro. Las operaciones destructivas respetan las políticas de seguridad. Las interrupciones no dejan estados ambiguos sin posibilidad de diagnóstico.

## Pruebas

```powershell
uv run pytest
uv run ruff check .
```

270 pruebas en verde, con 2 pruebas omitidas sin Tesseract instalado (3 en la integración continua sin el binario). Todas usan el sistema de archivos real sobre carpetas temporales, sin mocks del sistema de archivos. Integración continua en Windows con uv sync --locked, ruff y pytest.

Las pruebas de contrato cubren los escenarios que fijan el comportamiento prometido: precedencia de rutas por capas y perfiles de almacenamiento con fail loud, validación del manifiesto entre plan y aplicación con estados pendiente, aplicado y fallido, trazabilidad del journal con espacio de trabajo e id de plan y recuperación de ejecuciones interrumpidas, identidad de espacios de trabajo en el índice con resolución por raíz efectiva, concurrencia de escrituras en SQLite con WAL y transacciones inmediatas, y migración de configuraciones antiguas sin perder datos.

## Documentación

La documentación de producto no vive en este repositorio sino en un proyecto de documentación aparte. Este repositorio guarda el código y las decisiones técnicas.
