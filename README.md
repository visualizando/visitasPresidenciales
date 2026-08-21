# Accesos públicos

Pipeline y sitio estático para explorar los registros públicos de acceso a Casa Rosada y la Quinta de Olivos. El proyecto descarga PDF desde una carpeta pública, normaliza los registros, conserva las tablas canónicas en Parquet y genera índices y agregados compactos para GitHub Pages.

La base incluida contiene 2.022.698 registros deduplicados y 91.199 personas entre el 8 de enero de 2016 y el 30 de junio de 2026. Combina 1.378 fuentes activas: PDF consolidados y mensuales de Casa Rosada, partes diarios de Olivos, el CSV histórico unificado de 2020-2021 y planillas XLSX/DOCX estructuradas de 2016, 2018, 2019 y 2020. Los 122 PDF vacíos de 2021 se conservan en el manifiesto como faltantes explicados, pero no generan filas.

Los índices de búsqueda, fichas y co-presencias se publican en shards JSON comprimidos con gzip y se descomprimen en el navegador. La salida estática completa ocupa aproximadamente 435 MB y el shard interactivo más grande queda debajo de 1,9 MB.

## Desarrollo

Requisitos: Python 3.12+, `uv`, Node 20+ y `pnpm`.

```bash
uv sync --all-extras
uv run pytest
pnpm --dir web install
pnpm --dir web test
pnpm --dir web build
```

Para generar el sitio desde las particiones existentes:

```bash
uv run accesos build-web --output web/public/data
```

Para importar los TSV históricos ya normalizados sin copiar los PDF al repositorio:

```bash
uv run accesos import-legacy "D:\_DATAVIZ\RosadaOlivos\old\normalized_tsv"
```

Para descargar recursivamente una carpeta pública de Google Drive durante un backfill puntual:

```bash
uv run accesos download-drive ID_DE_CARPETA tmp/historical-pdfs
```

Para incorporar PDF históricos legibles desde una carpeta local, dejando los formatos desconocidos en cuarentena:

```bash
uv run accesos backfill-local tmp/historical-pdfs --min-year 2019
```

Para incorporar las planillas XLSX y DOCX históricas estructuradas:

```bash
uv run accesos import-historical-office data/Raw
```

Para regenerar el CSV histórico unificado de Olivos 2020-2021:

```bash
uv run accesos import-olivos-csv old/datos_olivos-csv.csv
```

Si cambia un parser, puede reprocesarse sólo una sede aunque los checksum no hayan cambiado:

```bash
uv run accesos backfill-local tmp/historical-pdfs --min-year 2019 --force-location olivos
```

Para revisar una fuente pública:

```bash
SOURCE_BASE_URL=https://ejemplo.org/accesos/ uv run accesos update
```

Durante el desarrollo también se admite una carpeta local:

```powershell
uv run accesos update --source "D:\_DATAVIZ\RosadaOlivos\old"
```

La fuente debe organizarse como `casa-rosada/{año}/{mes}` y `olivos/{año}/{mes}`. Puede exponer un `index.json`, un listado HTTP de directorios o FTP anónimo. Los PDF originales sólo viven en el directorio temporal del runner.

## Datos y privacidad

Los resultados reproducen documentos publicados por la fuente y mantienen enlaces de procedencia. DNI y CUIL se muestran completos porque así fue definido para esta versión. Las coincidencias por documento se consolidan automáticamente; las coincidencias sólo por nombre se presentan como candidatos de revisión.

Cada regeneración crea `data/curation/candidates.csv`, un reporte auditable de posibles identidades duplicadas. El reporte compara nombres por tokens, orden, nombres adicionales y errores tipográficos pequeños; incluye puntaje, nivel de confianza, documentos, períodos, sedes y una explicación de cada propuesta. Nunca propone unir dos documentos distintos y respeta las fusiones y rechazos versionados en `data/curation/entity_merges.json`. Los candidatos no modifican la base hasta que una decisión sea incorporada explícitamente a ese archivo.

Para iterar sobre las reglas sin reconstruir todos los índices y gráficos:

```bash
uv run accesos identity-candidates
```

Para revisar los candidatos en una interfaz privada que sólo escucha en este equipo:

```bash
uv run accesos curate-identities
```

La herramienta abre `http://127.0.0.1:8765`, pagina el reporte local y guarda cada unificación, rechazo o postergación de forma atómica en `data/curation/entity_merges.json`. Una unificación con confianza de revisión, nombre frecuente o decisiones encadenadas exige confirmación adicional; los documentos incompatibles siempre quedan bloqueados. Ninguna decisión llega a la base publicada hasta revisar y commitear ese archivo y regenerar los datos.

El ranking de co-presencias se calcula únicamente cuando dos registros tienen entrada y salida válidas, comparten sede, fecha y destino normalizado, y sus intervalos se superponen durante al menos 10 minutos. Se deduplican los episodios repetidos y se priorizan días distintos, destinos específicos y minutos superpuestos. Es una señal de presencia compatible en los registros: no prueba un encuentro ni una interacción entre personas.

## Configuración

- `SOURCE_BASE_URL`: raíz HTTPS/HTTP/FTP pública.
- `MIN_YEAR`: primer año incluido; por defecto `2023`.
- `DATA_DIR`: estado del pipeline; por defecto `data`.
- `WEB_DATA_DIR`: salida estática; por defecto `web/public/data`.
- `LOCAL_SOURCE_ROOT`: ubicación opcional de PDF locales, por ejemplo `D:\_DATAVIZ\RosadaOlivos`.
- `SOURCE_PUBLIC_BASE_URL`: URL pública equivalente a las rutas locales, cuando esté disponible.

Los workflows de `.github/workflows` validan, actualizan y publican el sitio.
