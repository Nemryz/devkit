# ADR 0001 — Distribucion y licencias de DevKit

**Estado:** aprobado.
**Fecha:** 2026-11-06.
**Contexto:** DevKit evoluciona de toolkit de mantenimiento a plataforma de ejecucion controlada con clientes humanos y agentes. Antes de distribuir se debe resolver la licencia del codigo propio y la presencia de una dependencia con licencia AGPL.

## Problema

1. El codigo propio de DevKit no tenia licencia explicita.
2. PyMuPDF, con licencia AGPL-3.0 o comercial, estaba entre las dependencias centrales aunque solo se usa en el OCR y el import es perezoso.
3. `ebooklib`, tambien AGPL, figuraba en el extra `docs` sin uso real en `src`.
4. La version del paquete (`0.1.0`) no coincidia con la etiqueta publicada (`v1.2.0`).

## Decisiones

### 1. Modelo de distribucion

DevKit se distribuye como paquete publico (PyPI / wheel), porque es la hipotesis mas exigente y la que mejor encaja con la direccion de plataforma. Esta decision condiciona todas las demas.

### 2. Licencia del codigo propio

Apache-2.0. Motivos:

- Concesion explicita de patentes, relevante si DevKit se integra en productos de terceros.
- Compatibilidad con la mayoria de licencias permisivas del ecosistema.
- Condiciones claras sobre redistribucion y contribuciones.

MIT fue considerada y descartada por la ausencia de concesion de patentes explicita.

### 3. PyMuPDF

PyMuPDF se ofrece bajo doble licencia AGPL-3.0 o comercial. Su presencia en dependencias centrales es incompatible con distribuir DevKit bajo Apache-2.0 sin obligaciones adicionales.

Decision: **aislar ahora, sustituir despues.**

- PyMuPDF se mueve fuera de `dependencies` y se declara solo en el extra `ocr`.
- El extra `ocr` documenta la licencia y las obligaciones aplicables.
- El aislamiento es transitorio. El bloque diferido de OCR sustituira PyMuPDF por `pypdfium2` (Apache-2.0 / BSD) y `pypdf` (BSD-3).
- La documentacion debe dejar claro que el aislamiento es transitorio y que la sustitucion es el objetivo.

### 4. ebooklib

Se elimina del extra `docs`. No se importa en `src` y su licencia AGPL no aporta valor al proyecto.

### 5. Fuente unica de version

`pyproject.toml` es la fuente de verdad. `dev --version` lee `importlib.metadata.version('devkit')`. La CI verifica que la etiqueta Git coincide con la version del paquete en cada push de etiqueta.

### 6. Auditoria de dependencias

La CI distingue dependencias centrales de extras opcionales. Las dependencias centrales no deben contener licencias copyleft. Los extras se auditan por separado y sus licencias se documentan en `THIRD_PARTY.md`.

## Consecuencias

- DevKit puede distribuirse bajo Apache-2.0 sin obligaciones copyleft en el nucleo.
- El OCR queda como capacidad opcional con una dependencia AGPL/comercial documentada.
- La sustitucion de PyMuPDF queda como deuda planificada con fecha.
- La version tiene una sola fuente y la CI la verifica.

## Alternativas consideradas

- Sustituir PyMuPDF inmediatamente: descartado porque bloquearia la consolidacion del nucleo y el OCR funciona.
- Asumir AGPL para todo el proyecto: descartado porque es incompatible con la direccion de plataforma y la integracion empresarial.
- Mantener PyMuPDF en el nucleo con nota: descartado porque no es una decision documentada y oculta el problema.
