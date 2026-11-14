# Herramientas

Los planes que se aplican sin reescanear usan un manifiesto v2 firmado: las acciones llevan `id` y `depende_de`, el orden es topologico y la politica requerida se deriva del catalogo. Una dependiente de una accion fallida u omitida queda `OMITIDA` con su codigo, y el plan se marca `parcial`. Los manifiestos v1 se siguen leyendo y se migran de forma explicita.

## doctor

Comprueba el entorno antes de ejecutar cualquier otra herramienta. Revisa version de Python, dependencias del nucleo, memoria, disco, carpeta de estado, journal, OneDrive, rutas largas y elevacion. Devuelve JSON por defecto y acepta el formato tabla.

## backup

Genera un archivo cifrado con manifiesto SHA-256 y prueba de restauracion obligatoria. Crea el contenedor 7z con AES-256 y cabecera cifrada, escribe el manifiesto y verifica extrayendo en temporal.

## trim

Limpia caches y artefactos con plan previo, papelera de Windows y journal transaccional. Excluye .git, src y tests. Respeta DEVKIT_READONLY. El plan incluye manifiesto firmado para aplicar sin reescanear el arbol y valida tamano, fecha y destino antes de mover. Aplicar exige `--forzar` como anulacion de seguridad y la politica derivada solo permite acciones de papelera.

## dedupe

Agrupa por tamaño, confirma con BLAKE3 (prehash parcial y completo) y mueve los duplicados a la papelera. Conserva la ruta mas corta y el mas antiguo. Incluye resumen por extension y filtro de OneDrive. Aplicar exige `--forzar` y la politica derivada solo permite acciones de papelera.

## health

Genera un informe de memoria, disco, SMART, bateria, Defender, actualizaciones, inicio y eventos. Distingue ok, aviso, error y unknown para no fingir salud cuando no hay datos.

## nice

Envuelve un proceso hijo con prioridad en bajo (BELOW_NORMAL_PRIORITY_CLASS) y tiempo maximo. Mide memoria pico mientras corre con un hilo. Si SetInformationJobObject devuelve 24, cierra el Job y sigue sin limite antes que romper. Registra pico en el journal.

## organize

Clasifica por extension, firma binaria y año, con confirmacion archivo por archivo o --todos. `--todos` elige y `--si` confirma la aplicacion; ninguna sustituye a la otra. Resuelve colisiones con _2, _3. El manifiesto firmado cubre origen, destino, tamano y fecha, y se puede aplicar sin reescanear con --plan.

## idea

Crea y valida notas Markdown con frontmatter (titulo, creado, etiquetas, estado). Revisa enlaces rotos y campos obligatorios. Avisa si el titulo ya existe.

## index

Construye un indice SQLite con FTS5 sobre las notas. Permite buscar, actualizar de forma incremental por mtime y exportar a JSON. El indice vive en %LOCALAPPDATA%\devkit\index.sqlite.

## ocr

Extrae texto y metricas de confianza en modo de solo lectura con Tesseract y PyMuPDF. Soporta imagenes y PDFs. Genera notas con origen ocr listas para idea e index. No mueve, borra ni clasifica archivos.

## migrate

Migra un plan o una configuracion a la version vigente sobre una ruta explicita, con `--tipo plan|config`. Reporta la version de origen y la de destino, no escribe nada si el dato ya esta al dia y solo deja hito en el journal cuando cambio algo. `--desde` y `--hasta` exigen las versiones esperadas y fallan sin tocar el archivo si no coinciden. Las versiones desconocidas se rechazan con codigo estable.
