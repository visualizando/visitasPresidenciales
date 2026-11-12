> Informe de la auditoría inicial. La implementación posterior del flujo mensual está documentada en [ACTUALIZACION-MENSUAL.md](ACTUALIZACION-MENSUAL.md); las menciones a tareas pendientes describen el estado previo a esa implementación.

# Revisión y consolidación — 12 de noviembre de 2026

La raíz de trabajo es `D:\_DATAVIZ\RosadaOlivos`. La copia en Documents era anterior: se compararon 4.463 archivos útiles, todos tenían equivalente en D:, y todas sus particiones coincidían byte por byte. Se conservaron las versiones diferentes y los scripts de investigación en `archive/consolidation-2026-11-12/`. Las copias originales no se eliminaron. Los entornos, cachés y salidas de pruebas se consideran regenerables.

## Fuentes de aquí en adelante

| Sede | Carpeta de la ONG |
|---|---|
| Casa Rosada | https://drive.google.com/drive/folders/1ZgFqfWYnsGQh5gRdwrbP5cmUjb-BqL-0 |
| Olivos | https://drive.google.com/drive/folders/1hFUlnyYj1MmGiKsvnWrChIZHpbwmX_xh |

Las carpetas determinan la sede. No debe inferirse de nombres como `Enero.pdf`. Deben recorrerse todos los años, porque la ONG puede agregar una respuesta histórica en cualquier momento.

## Estado verificado de la base

- 4.273 fuentes en el manifiesto: 4.124 activas y 149 en cuarentena.
- 2.167.481 filas en las particiones y 2.077.919 identificadores de registro distintos; estas cifras no equivalen a visitas únicas ni a personas.
- No hay particiones referenciadas que falten ni particiones sin referencia en el manifiesto.
- Se conservaron las decisiones de identidad y la base canónica. El build regenera los candidatos y las salidas web.
- Casa Rosada: 41 archivos visibles (40 PDF, 1 XLSX); los 41 coinciden por SHA256 con fuentes de la base. Las coincidencias de contenido incluyen cambios de nombre.
- Olivos: 2.074 entradas visibles (864 PDF, 1.188 XLSX, 22 DOCX), incluyendo archivos temporales de Office. El resultado detallado de la comparación está en `audit-2026-11-12/summary.json` y los inventarios de esa carpeta.
- La fuente histórica `historical/olivos/datos_olivos-csv.csv` ya aporta 37.451 registros de 2020–2021. Los 611 archivos de ese período sin coincidencia de checksum (489 XLSX y 122 PDF) requieren contraste con esos registros; no deben sumarse como si todos fueran nuevos.

Resultado final de las 2.115 entradas visibles:

| Resultado | Casa Rosada | Olivos |
|---|---:|---:|
| Contenido idéntico a fuentes registradas | 41 | 1.336 |
| Sin coincidencia de checksum; requiere reconciliar registros | 0 | 611 |
| Archivo vacío, cero bytes | 0 | 120 |
| Archivo temporal de Office | 0 | 4 |
| Archivo con extensión XLSX pero contenido inválido (165 bytes) | 0 | 3 |

No quedaron errores de conexión pendientes en la comparación final. Los tres archivos inválidos se conservaron como evidencia; no se interpretaron como datos. Los 611 archivos a reconciliar se distribuyen en 366 de 2020 y 245 de 2021.

El listado público HTML es una observación de lo visible, no una garantía de exhaustividad. Las carpetas vacías o no verificables quedan registradas como advertencias. No se interpreta una ausencia en ese listado como una baja de datos.

## Cambios implementados

1. `pipeline/drive_sync.py`: inventaría ambas carpetas, descarga PDF/XLS/XLSX/DOCX, valida firmas, calcula SHA256 y compara con el manifiesto. Usa el ID de Drive y la huella del contenido para conservar cada versión; un renombre no colisiona con otro archivo. Omite los archivos temporales `~$`.
2. Soporte opcional de Drive API v3 con paginación y detección de búsquedas incompletas. Con `GOOGLE_DRIVE_API_KEY`, reutiliza una versión local sólo cuando coinciden el checksum remoto y el hash local. Sin esa configuración consulta el HTML público y vuelve a descargar al pedir una comparación.
3. Un fallo al procesar una planilla que reemplaza una fuente activa conserva sus particiones y su entrada anterior. El diagnóstico se escribe en `data/quarantine/`. Esto cubre el fallo de extracción; no convierte todo el importador antiguo en una transacción.
4. Se reparó la instalación del frontend con Node 24 y pnpm 10, respetando el lockfile. El Node global del equipo es 18: usar Node >=20 y pnpm 10 para este proyecto.

Consultar las fuentes (sin descargar documentos):

```powershell
Set-Location D:\_DATAVIZ\RosadaOlivos
uv run python -m pipeline.drive_sync
```

Descargar, conservar versiones y comparar por contenido:

```powershell
uv run python -m pipeline.drive_sync --download
# Equivalente desde cualquier carpeta:
& D:\_DATAVIZ\RosadaOlivos\scripts\Sync-Drive.ps1 -Download
```

Cada sede guarda su comparación descargada en `data/drive/<folder_id>/inventory.json`. Una consulta sin descarga escribe `listing.json` por separado para no perder las huellas verificadas. Los originales versionados se conservan en `data/drive/raw/<file_id>/<sha256>.<extension>`, fuera de Git. Una descarga fallida devuelve código de salida distinto de cero y deja identificados los pendientes.

**El sincronizador todavía no agrega registros a las particiones ni publica el sitio.** Es la primera etapa de la adaptación solicitada; permite revisar novedades y preparar la reconciliación sin duplicar la base histórica. No se cambiaron ni activaron automatizaciones remotas.

## Hallazgos que condicionan la incorporación automática

| Prioridad | Hallazgo | Acción necesaria |
|---|---|---|
| Alta | `download-drive` antiguo sólo descarga PDF y omite archivos existentes aunque cambien | Usar `pipeline.drive_sync` para la revisión nueva; retirar el comando anterior al completar la migración |
| Alta | `update` sólo descubre PDF y espera sede/año/mes en rutas HTTP/FTP/locales | Agregar un adaptador basado en ID de Drive y sede configurada; no pasarle directamente la URL de la carpeta |
| Alta | El importador Office filtra Olivos 2016–2019 y Casa Rosada XLSX 2020 | Separar selección de archivos y parsers; validar planillas de años posteriores sin restricciones históricas |
| Alta | Planillas 2020–2021 pueden representar registros ya incluidos en el CSV histórico | Comparar registros normalizados antes de sumar fuentes; conservar ambas procedencias |
| Alta | Los importadores Office/CSV y el commit del pipeline PDF no son transacciones completas; el CSV histórico elimina particiones antes de leer todo el archivo | Preparar nueva generación en staging, validar y promover la generación completa; probar fallos durante lectura, escritura y build |
| Alta | El job mensual sigue usando `SOURCE_BASE_URL` y corte en 2023 | Cambiarlo por revisión de las dos carpetas sólo cuando termine la reconciliación y las pruebas de incorporación |
| Media | El job actual usa `git diff --quiet` antes de agregar archivos: puede ignorar novedades sólo no versionadas | Evaluar cambios incluyendo untracked y verificar la lista exacta antes del commit |
| Media | En audiencias, `_audiencia_is_current` compara tamaño local con su estado; no verifica cambios remotos | Incorporar ETag/Last-Modified o checksum remoto y descarga temporal con reemplazo atómico |
| Media | `data/Raw` de accesos y `data/raw` de audiencias son la misma ruta en Windows | Separar explícitamente los originales de audiencias, con migración de rutas y pruebas |
| Media | Los PDF escaneados no tienen OCR automático | Mantener cuarentena y diseñar OCR como una etapa con revisión y métricas de calidad |
| Media | Varias fuentes históricas conservan URLs locales | Usar el vínculo público de Drive en los derivados mediante el mapa de procedencias, conservando los IDs de fuente históricos |

El registro de audiencias de gestión de intereses sigue siendo una fuente complementaria separada del Drive de accesos. El workflow tampoco ejecuta toda la cadena de enriquecimiento/cruce después de actualizar audiencias; incluir esa dependencia antes de regenerar la web.

## Plan de implementación

1. **Cerrar el inventario y la procedencia.** Habilitar una API key de Google Cloud con Drive API para estas carpetas públicas (o autenticación de sólo lectura si dejan de ser públicas). Validar acceso real, paginación y correspondencia con el listado de la ONG. Vincular por checksum los IDs de Drive a los `source_id` históricos sin renombrar identidades ni reimportar copias idénticas.
2. **Reconciliar Olivos.** Procesar las planillas nuevas en un espacio de comparación, conservando fecha, persona/documento, sede, tipo, horas y referencia de hoja/página. Distinguir duplicados exactos, datos complementarios y discrepancias. Un hash de archivo distinto no demuestra que sus visitas sean nuevas. No fusionar personas únicamente por semejanza de nombre.
3. **Unificar el ingreso de novedades.** Un solo comando que consulte Drive, clasifique novedades/reemplazos, despache al parser por formato y sede, valide fechas/conteos/esquema y produzca un informe. Los formatos nuevos, cero filas inesperadas y cambios abruptos pasan a revisión. Conservar la generación anterior ante fallos.
4. **Activar actualización periódica.** Reutilizar la cadencia mensual existente, persistir el estado de Drive y los originales, incorporar novedades aprobadas, regenerar derivados y verificar la web. Preparar un PR de datos con resumen de fuentes/filas/períodos y diagnóstico; publicar sólo después de validación. Separar los fallos de audiencias de los de accesos.

Pruebas de aceptación: segunda ejecución sin cambios no altera la base; renombrar un archivo no duplica datos; reemplazarlo conserva historial; XLSX de 2026 llega al parser; archivos idénticos en varias carpetas tienen una sola incorporación; una descarga incompleta, un error de parser o un fallo de build no elimina la generación válida; archivos retirados del Drive no borran historia automáticamente.

## Validación final

- 89 pruebas Python aprobadas, incluidas las regresiones de Drive y la conservación de una fuente activa ante una planilla inválida.
- 39 pruebas del frontend aprobadas en 18 archivos.
- Ruff aprobado para los archivos Python modificados.
- Reconstrucción completa de los datos web: 2.077.917 registros publicados, 99.409 personas y 11 exportaciones anuales.
- Paquete completo en `web/dist`: 307.600 KiB; aplicación comprimida: 103 KiB. Ambos dentro de los presupuestos existentes.
- Prueba de búsqueda caliente: p95 de 37,8 ms sobre 14.346 personas en la muestra de rendimiento.
- Los candidatos de curación, que son derivados regenerables, fueron reconstruidos. Las decisiones de identidad se conservaron.
- Verificación por SHA256: 4.349 archivos canónicos comparados permanecen idénticos, incluidas las particiones, el manifiesto y las decisiones de identidad.
- Cambios locales sin commit, push ni publicación. Los comprobantes están en `audit-2026-11-12/validation.json`.

## Referencias de Drive

- [Drive API: búsqueda de archivos y consulta por carpeta](https://developers.google.com/workspace/drive/api/guides/search-files).
- [Drive API: paginación y respuesta de files.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list).

La API está implementada y probada con respuestas simuladas; su validación contra Google con una API key real queda pendiente de configurar esa credencial. La revisión de esta sesión se realizó contra el HTML público y los archivos descargables.
