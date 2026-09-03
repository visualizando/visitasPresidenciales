# Explorador de accesos a Olivos y Casa Rosada

Sitio estático y pipeline reproducible para explorar registros públicos de ingreso a Casa Rosada y la Quinta de Olivos. Los datos fueron obtenidos por [Poder Ciudadano](https://poderciudadano.org/) mediante pedidos periódicos de acceso a la información pública.

El proyecto descarga o incorpora documentos oficiales, extrae sus tablas, normaliza personas y movimientos, conserva una base canónica en Parquet y genera archivos compactos para publicar todo en GitHub Pages, sin backend ni base de datos externa.

## Estado de la base

La versión incluida actualmente contiene:

- **2.022.698 registros deduplicados**.
- **87.080 identidades publicadas**, luego de aplicar las unificaciones curadas.
- **1.378 fuentes activas**.
- Registros entre el **8 de enero de 2016** y el **30 de junio de 2026**.
- CSV anuales disponibles para 2016 y para el período 2018–2026.
- Aproximadamente **472 MB** de salida estática completa.

La cobertura no es continua: hay años, meses y archivos sin datos. La propia interfaz incluye un informe que distingue períodos sin una fuente incorporada, archivos vacíos y documentos que no pudieron procesarse. Los PDF escaneados sin una capa de texto utilizable permanecen en cuarentena; OCR todavía no forma parte del proceso automático.

La base combina PDF consolidados y mensuales de Casa Rosada, partes diarios de Olivos, el CSV histórico unificado de 2020–2021 y planillas XLSX/DOCX estructuradas de 2016, 2018, 2019 y 2020. Los PDF originales no se versionan en Git.

## Qué permite hacer el sitio

- Buscar por nombre, DNI o CUIL, tolerando acentos, puntuación, orden de palabras y errores menores.
- Filtrar por sede, año y tipo de registro.
- Seleccionar varias variantes de una misma persona y compararlas con colores consistentes.
- Compartir una selección mediante un hotlink como `#person=id1,id2`.
- Consultar fichas con cronología, sede, destino, motivo, calidad y vínculo a la fuente.
- Descargar en CSV todos los registros de las personas seleccionadas.
- Ordenar la tabla de movimientos por columna y recorrerla en bloques de 100 filas.
- Explorar actividad diaria y mensual, calendario anual, ritmos por día y hora, destinos y motivos.
- Distinguir días compartidos por varias personas y marcar los días con registros de Javier Milei en Casa Rosada.
- Consultar coincidencias temporales entre personas cuando existen horarios y destinos compatibles.
- Ver rankings de visitas diarias por sede, año o presidencia.
- Descargar un CSV comprimido por año.
- Auditar períodos y archivos faltantes desde el informe de cobertura.

Los gráficos consumen agregados precalculados: nunca recorren los dos millones de registros en el navegador. La búsqueda se ejecuta en un Web Worker y utiliza índices fragmentados y comprimidos. Las fichas, hotlinks y co-presencias también se distribuyen en shards pequeños.

## Arquitectura

```mermaid
flowchart LR
    A[PDF, XLSX, DOCX y CSV públicos] --> B[Descubrimiento y descarga]
    B --> C[Parsers por sede y formato]
    C --> D[Normalización y validación]
    D --> E[Particiones Parquet]
    E --> F[DuckDB durante el build]
    G[Curación de identidades] --> F
    F --> H[Índices de búsqueda y hotlinks]
    F --> I[Agregados para gráficos y rankings]
    F --> J[CSV anuales]
    H --> K[React + TypeScript + D3]
    I --> K
    J --> K
    K --> L[GitHub Pages]
```

Componentes principales:

- `pipeline/`: descubrimiento, parsers, importadores históricos, normalización y generación web.
- `data/partitions/`: base canónica particionada en Parquet.
- `data/manifest.json`: inventario y estado de las fuentes.
- `data/curation/`: candidatos y decisiones versionadas sobre identidades.
- `web/`: interfaz en React, TypeScript, Vite y D3.
- `.github/workflows/`: validación, actualización mensual y publicación.

## Desarrollo local

Requisitos:

- Python 3.12 o superior.
- [`uv`](https://docs.astral.sh/uv/).
- Node.js 20 o superior.
- pnpm 10.

Instalación y pruebas:

```bash
uv sync --all-extras
uv run pytest
pnpm --dir web install
pnpm --dir web test
pnpm --dir web build
```

Regenerar índices, analíticas y exportaciones desde las particiones existentes:

```bash
uv run accesos build-web --output web/public/data
```

Levantar la interfaz local:

```bash
pnpm --dir web dev
```

La aplicación queda disponible normalmente en `http://127.0.0.1:5173/`.

## Actualización de datos

La fuente pública esperada puede organizarse así:

```text
casa-rosada/{año}/{mes}/
olivos/{año}/{mes}/
```

El descubrimiento admite `index.json`, listados públicos HTTP de Apache/nginx y FTP anónimo. Para revisar una fuente sin procesarla:

```bash
SOURCE_BASE_URL=https://ejemplo.org/accesos/ uv run accesos discover
```

Para descubrir, descargar y procesar novedades:

```bash
SOURCE_BASE_URL=https://ejemplo.org/accesos/ uv run accesos update
```

Durante el desarrollo también puede utilizarse una carpeta local:

```powershell
uv run accesos update --source "D:\_DATAVIZ\RosadaOlivos\data\Raw"
```

El procesamiento es incremental. El manifiesto compara metadatos y checksum; si una fuente cambió, reemplaza todos los registros procedentes de ese archivo. Una fuente eliminada queda marcada como ausente, pero sus registros históricos no se borran automáticamente.

## Audiencias de gestión de intereses

El proyecto también incorpora los CSV anuales del [Registro Único de Audiencias de Gestión de Intereses](https://datos.gob.ar/dataset/registro-unico-de-audiencias-de-gestion-de-intereses) (Poder Ejecutivo Nacional, Decreto 1172/2003). A diferencia de los PDF de acceso, estos se conservan como un dataset tabular único y no alimentan (todavía) el sitio web.

Actualizar las audiencias (descubre los CSV del año en curso, descarga solo los que cambiaron y re-genera el unificado):

```bash
uv run accesos update-audiencias
```

Opciones:

- `--data-dir`: directorio de estado (por defecto `data`).
- `--raw`: carpeta con los CSV descargados (por defecto `<data>/raw`).
- `--output`: CSV unificado de salida (por defecto `<data>/audiencias_unificado.csv`).
- `--force`: re-descarga todos los CSV y re-unifica, ignorando el estado previo.

Salidas:

- `<data>/raw/` — CSV anuales descargados (originales, latin-1).
- `<data>/audiencias_unificado.csv` — serie completa (2004-2025) normalizada a un esquema único de 48 columnas en UTF-8.
- `<data>/audiencias_state.json` — estado de cada fuente (URL, sha256, tamaño, formato) usado para la detección incremental de cambios.

El portal expone dos esquemas a lo largo de los años: uno antiguo (2004-2016, columnas `*_sujeto_obligado`, `fecha_hora_audiencia`, `id_audiencia`, etc.) y uno moderno (2016 bis y 2017-2025, con `fecha`, `sujeto_obligado_nombre`, `participantes_json`, etc.). La unificación normaliza el esquema antiguo al moderno y conserva como columnas adicionales los campos antiguos sin equivalente (por ejemplo `id_audiencia`, `estado_audiencia`, `es_persona_juridica`), de modo que no se pierde información.

La actualización mensual del workflow ejecuta `update-audiencias` luego de procesar los PDF de acceso.

### Enriquecimiento de personas desde las audiencias

Las audiencias identifican personas (sujeto obligado/funcionario, solicitante y persona representada). Para enriquecer la base de identidades, un paso opcional extrae esas personas, las cruza con las personas ya publicadas y consolida nombres, documentos, cargos e instituciones:

```bash
uv run accesos enrich-audiencias
```

Opciones:

- `--unificado`: CSV unificado de entrada (por defecto `data/audiencias_unificado.csv`).
- `--base-doc-dir`: carpeta con los shards de personas con documento de la base (por defecto `web/public/data/search/document`). Requiere un build-web previo.
- `--name-threshold`: umbral de similitud (0-100, por defecto `96`) para el cruce por nombre cuando no hay documento.

Salidas:

- `<data>/audiencias_personas.csv` — una fila por (audiencia, rol, persona) con cargo e institución.
- `<data>/audiencias_personas_master.json` — consolidación por `entity_id`: nombre canónico, documento, lista de cargos, instituciones por tipo (`dependencia`, `persona_juridica`, `organismo_estatal`, `grupo`), y el vínculo con la base (`match_type`: `dni` o `nombre`).
- `<data>/audiencias_personas_state.json` — estadísticas de la corrida.

El cruce asigna a cada persona de audiencia un `entity_id` idéntico al de la base (`normalize.entity_id`), de modo que el cruce por documento es directo. Cuando no hay documento se intenta un cruce por nombre casi exacto, con un umbral alto para evitar falsos positivos; los resultados quedan etiquetados como `dni` o `nombre` para su revisión. Este dataset es independiente del sitio web: no modifica los índices publicados.

### Revisión y curación de las coincidencias

Los cruces por **nombre** (sin documento coincidente) son los únicos inciertos y merecen revisión antes de usarse: en ellos una identidad de audiencias que no tiene documento se propone fusionar con una identidad ya existente en la base. El proyecto reutiliza la misma interfaz local de curación que ya se usa para las identidades duplicadas.

Generar los candidatos de curación del cruce audiencias ↔ base:

```bash
uv run accesos curate-audiencias
```

Esto produce `data/curation/audiencias_candidates.csv` y `data/curation/audiencias_decisions.json` en el mismo esquema de `curate-identities`. Para revisarlos uno por uno (aceptar `merge`, `reject` o `defer`):

```bash
uv run accesos curate-identities \
    --candidates data/curation/audiencias_candidates.csv \
    --decisions data/curation/audiencias_decisions.json
```

Notas:

- Los cruces por **documento** no generan candidato: coinciden en `entity_id` por construcción y no requieren fusión.
- Un candidato cuyas dos identidades tienen documentos distintos (señal típica de falso positivo por nombre) es bloqueado por la interfaz con un conflicto de documento; conviene rechazarlo.
- Las decisiones quedan en `data/curation/audiencias_decisions.json` y son la base para aplicar el enriquecimiento en un paso posterior (aún no publicado en el sitio).

## Importaciones históricas

Importar TSV previamente normalizados:

```bash
uv run accesos import-legacy "D:\_DATAVIZ\RosadaOlivos\old\normalized_tsv"
```

Descargar recursivamente una carpeta pública de Google Drive para un backfill puntual:

```bash
uv run accesos download-drive ID_DE_CARPETA tmp/historical-pdfs
```

Incorporar PDF históricos legibles y enviar formatos desconocidos a cuarentena:

```bash
uv run accesos backfill-local tmp/historical-pdfs --min-year 2016
```

Reprocesar una sede después de modificar su parser:

```bash
uv run accesos backfill-local tmp/historical-pdfs --min-year 2016 --force-location olivos
```

Importar planillas XLS, XLSX y DOCX históricas:

```bash
uv run accesos import-historical-office data/Raw
```

El importador reconoce tanto las planillas de visitas con horarios como los partes diarios de
personas y vehículos. Cuando una planilla diaria no informa horas, conserva la fecha sin inventar
un horario y marca el registro con calidad media. Los archivos escaneados, dañados o con un formato
todavía no reconocido quedan identificados en cuarentena y aparecen en el informe de cobertura del
sitio. Las ejecuciones siguientes comparan metadatos y checksum, y sólo reconstruyen los datos si
alguna fuente cambió.

Importar el CSV histórico unificado de Olivos 2020–2021:

```bash
uv run accesos import-olivos-csv old/datos_olivos-csv.csv
```

## Curación de identidades

Los documentos coincidentes pueden consolidarse automáticamente. Las similitudes basadas sólo en nombres generan candidatos de revisión y nunca producen una fusión automática.

Cada regeneración actualiza `data/curation/candidates.csv` con puntaje, nivel de confianza, documentos, períodos, sedes y explicación. El proceso rechaza candidatos con documentos incompatibles y respeta las decisiones guardadas en `data/curation/entity_merges.json`.

Regenerar únicamente los candidatos:

```bash
uv run accesos identity-candidates
```

Abrir la interfaz privada de revisión:

```bash
uv run accesos curate-identities
```

La herramienta escucha sólo en `http://127.0.0.1:8765`. Permite filtrar candidatos por cantidad de visitas, aprobar todas las coincidencias de máxima confianza y guardar unificaciones, rechazos o postergaciones de manera atómica. Ninguna decisión modifica el sitio publicado hasta que `entity_merges.json` sea revisado, versionado y los datos sean regenerados.

## Co-presencias y límites interpretativos

Una co-presencia se calcula sólo cuando dos registros:

- Tienen entrada y salida completas, válidas y de calidad alta.
- Comparten sede, fecha y un destino específico normalizado.
- Sus entradas difieren como máximo 15 minutos y sus salidas, otros 15 minutos.
- Superponen sus intervalos durante al menos 5 minutos.
- Ninguna identidad tiene intervalos incompletos ni 80 o más días de actividad en un año.

Los episodios repetidos se deduplican y sólo se muestran hasta cinco resultados. Es una señal de presencia compatible en los registros: **no demuestra un encuentro ni una interacción entre personas**.

Los datos personales y documentos visibles reproducen información publicada en las fuentes oficiales. La interfaz conserva referencias al archivo y la página de origen para facilitar la auditoría.

## Automatización en GitHub

- `validate.yml` se ejecuta en cada pull request y cada push a `main`: valida Python, frontend, curación, build y límites de tamaño.
- `deploy-pages.yml` publica GitHub Pages sólo después de una validación exitosa originada por un push.
- `update-data.yml` se ejecuta el día 8 de cada mes a las 09:00 UTC y también admite ejecución manual.

La actualización mensual comienza la detección automática en 2023, pero conserva toda la base histórica ya incorporada. Si falla una extracción, no se publica una base parcial: se adjunta un diagnóstico y se abre o actualiza un issue.

Límites comprobados durante CI:

- Aplicación inicial menor de 500 KiB comprimidos.
- Cada shard menor de 3 MB.
- Cada dataset analítico menor de 1 MB.
- Sitio completo menor de 750 MB.

## Variables de configuración

- `SOURCE_BASE_URL`: raíz pública HTTPS, HTTP o FTP.
- `MIN_YEAR`: primer año que recorre la actualización automática; por defecto `2023`.
- `DATA_DIR`: estado y particiones del pipeline; por defecto `data`.
- `WEB_DATA_DIR`: salida estática; por defecto `web/public/data`.
- `LOCAL_SOURCE_ROOT`: carpeta local opcional con archivos fuente.
- `SOURCE_PUBLIC_BASE_URL`: URL pública equivalente a las rutas locales, cuando exista.

## Créditos

- Datos: [Poder Ciudadano](https://poderciudadano.org/).
- Creación y diseño: [Andrés Snitcofsky · Visualizando](https://visualizando.ar/).
