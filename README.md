# Accesos públicos

Pipeline y sitio estático para explorar los registros públicos de acceso a Casa Rosada y la Quinta de Olivos. El proyecto descarga PDF desde una carpeta pública, normaliza los registros, conserva las tablas canónicas en Parquet y genera índices y agregados compactos para GitHub Pages.

La base incluida contiene 1.636.491 registros deduplicados y 71.849 personas entre el 11 de julio de 2019 y el 28 de febrero de 2026. Combina los datos normalizados existentes con 372 PDF históricos legibles: siete consolidados/listados de Casa Rosada y los 365 partes diarios de Olivos de 2022. Los PDF escaneados, vacíos o no descargables no se incorporan como filas.

Los índices de búsqueda, fichas y co-presencias se publican en shards JSON comprimidos con gzip y se descomprimen en el navegador. La salida estática completa ocupa aproximadamente 327 MB y el shard más grande queda debajo de 1,6 MB.

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

El ranking de co-presencias se calcula únicamente cuando dos registros tienen entrada y salida válidas, comparten sede, fecha y destino normalizado, y sus intervalos se superponen durante al menos 10 minutos. Se deduplican los episodios repetidos y se priorizan días distintos, destinos específicos y minutos superpuestos. Es una señal de presencia compatible en los registros: no prueba un encuentro ni una interacción entre personas.

## Configuración

- `SOURCE_BASE_URL`: raíz HTTPS/HTTP/FTP pública.
- `MIN_YEAR`: primer año incluido; por defecto `2023`.
- `DATA_DIR`: estado del pipeline; por defecto `data`.
- `WEB_DATA_DIR`: salida estática; por defecto `web/public/data`.
- `LOCAL_SOURCE_ROOT`: ubicación opcional de PDF locales, por ejemplo `D:\_DATAVIZ\RosadaOlivos`.
- `SOURCE_PUBLIC_BASE_URL`: URL pública equivalente a las rutas locales, cuando esté disponible.

Los workflows de `.github/workflows` validan, actualizan y publican el sitio.
