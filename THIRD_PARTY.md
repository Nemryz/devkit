# Dependencias de terceros

## Dependencias centrales

| Paquete | Licencia | Uso |
|---|---|---|
| typer | MIT | Interfaz de linea de comandos |
| rich | MIT | Formato de salida y tablas |
| psutil | BSD-3-Clause | Informacion de procesos y sistema |
| pydantic | MIT | Validacion de modelos |
| orjson | Apache-2.0 / MIT | Serializacion JSON |
| blake3 | CC0 / Apache-2.0 | Hash de contenido |
| send2trash | BSD-3-Clause | Papelera de Windows |
| pytesseract | Apache-2.0 | Envoltorio de Tesseract |
| pillow | MIT-CMU (HPND) | Procesamiento de imagenes |
| platformdirs | MIT | Rutas de configuracion por plataforma |

## Extras opcionales

### ocr (contiene componente AGPL)

| Paquete | Licencia | Uso |
|---|---|---|
| pytesseract | Apache-2.0 | Envoltorio de Tesseract |
| pillow | MIT-CMU (HPND) | Procesamiento de imagenes |
| pymupdf | AGPL-3.0 o comercial | Renderizado de PDF (transitorio) |

PyMuPDF se distribuye bajo doble licencia AGPL-3.0 o comercial. Su presencia en el extra `ocr` es una medida transitoria mientras se completa la sustitucion por `pypdfium2` y `pypdf` (ver ADR 0001 y el bloque diferido de OCR en el roadmap).

### docs

| Paquete | Licencia | Uso |
|---|---|---|
| python-docx | MIT | Documentos Word |
| readability-lxml | Apache-2.0 | Extraccion de texto |

### data

| Paquete | Licencia | Uso |
|---|---|---|
| pandas | BSD-3-Clause | Analisis de datos |
| pyarrow | Apache-2.0 | Formato columnar |

### fs

| Paquete | Licencia | Uso |
|---|---|---|
| send2trash | BSD-3-Clause | Papelera de Windows |

## Dependencias de desarrollo

| Paquete | Licencia |
|---|---|
| pytest | MIT |
| pytest-cov | MIT |
| ruff | MIT |
| mypy | Apache-2.0 |

## Auditoria

La auditoria de licencias se ejecuta en CI y distingue dependencias centrales de extras opcionales. Las dependencias centrales no deben contener licencias copyleft.
