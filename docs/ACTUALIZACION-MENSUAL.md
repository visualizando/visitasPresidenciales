# Actualización mensual desde las carpetas de la ONG

El workflow **Actualizar datos** revisa Casa Rosada y Olivos el día **8 de cada mes a las 09:17 UTC (06:17 de Argentina)**. GitHub puede demorar el inicio programado. También puede ejecutarse desde **Actions → Actualizar datos → Run workflow**, y se ejecuta al cambiar en `main` el workflow o los módulos de Drive.

Fuentes configuradas en `pipeline/drive_sync.py`:

- Casa Rosada: `1ZgFqfWYnsGQh5gRdwrbP5cmUjb-BqL-0`.
- Olivos: `1hFUlnyYj1MmGiKsvnWrChIZHpbwmX_xh`.

## Qué hace cada ejecución

1. Prueba el código y recorre todas las subcarpetas, incluidos años históricos.
2. Identifica archivos por ID de Drive y SHA256. Un renombre no genera una fuente nueva. Consulta PDF, XLS, XLSX y DOCX; los temporales de Office se ignoran.
3. Vincula archivos idénticos a las fuentes existentes. Procesa contenidos nuevos y versiones cambiadas con el parser de su sede y formato, sin el filtro antiguo de años Office.
4. Reconcilia registros por identidad, sede, tipo, fecha/hora, salida, dirección, dispositivo y destino normalizados. Mantiene el ID histórico cuando hay equivalencia, sin fusionar personas por nombres parecidos. Las distintas fuentes conservan su procedencia y el sitio deduplica por ID de registro.
5. Construye una generación candidata en `.drive-update/`, manteniendo intacta la entrada. Los archivos vacíos, inválidos, escaneados o sin parser compatible pasan a cuarentena. Si falla una versión que reemplaza una fuente válida, se conserva la versión anterior.
6. Si cambian datos, regenera la web y verifica pruebas, tamaño y rendimiento de búsqueda. Sólo después promueve el candidato y hace un commit de particiones, manifiesto y estado de Drive.
7. Dispara explícitamente **Publicar GitHub Pages**, porque el push con `GITHUB_TOKEN` no dispara el workflow normal de push. La publicación verifica que no esté por reemplazar una generación más reciente.

Las fuentes retiradas de Drive no eliminan registros históricos. Un fallo de red aborta la ejecución antes de promover la generación. Un push concurrente a `main` hace que el push del bot sea rechazado; no hay force-push.

## Estado, informes y credenciales

- `data/drive/state.json` es el estado incremental versionado. No depende de que sobreviva la caché.
- Cada revisión guarda su fecha en ese estado, incluso cuando no hay novedades; los datos y la web sólo se regeneran cuando cambia contenido procesado.
- `data/drive/raw/` conserva versiones descargadas, fuera de Git y en caché de Actions cuando está disponible. Su pérdida sólo afecta rendimiento.
- El resumen de cada ejecución muestra fuentes vinculadas, procesadas, registros coincidentes/nuevos y cuarentena.
- El artifact `revision-drive-<run_id>` guarda el informe detallado por 90 días. No contiene filas de visitas ni credenciales.
- El token automático de GitHub tiene permisos `contents: write` y `actions: write`. No se necesita un PAT para la ejecución mensual o la publicación explícita.
- **Opcional:** el secret del repositorio `GOOGLE_DRIVE_API_KEY` activa Drive API v3, con paginación y checksums remotos. Con ese checksum, archivos procesados sin cambios no necesitan descargarse de nuevo.

Sin API key se usa el listado HTML público y se descargan los archivos para verificar su contenido. No se puede certificar la exhaustividad del HTML; un listado posiblemente paginado (50 entradas o más) o una raíz ilegible aborta la ejecución, en lugar de publicar una actualización truncada. Las carpetas vacías quedan como limitación del listado público. Si las carpetas dejan de ser públicas se requiere adaptar autenticación; no introducir una credencial privada en el código.

Una fuente histórica que corresponde a varias procedencias locales y luego cambia queda en revisión (`ambiguous_legacy_replacement`): no se elige arbitrariamente qué fuente reemplazar.

## Operación local

Desde `D:\_DATAVIZ\RosadaOlivos`, con una carpeta de trabajo que aún no exista:

```powershell
uv run python -m pipeline.drive_update --work-dir .drive-update
uv run accesos build-web --data-dir .drive-update/data --output web/public/data
# Después de validar el candidato:
uv run python -m pipeline.drive_update --promote .drive-update/data
```

La promoción conserva una copia de recuperación en `.drive-update/backup/` y revierte los movimientos si falla. No ejecutar dos promociones locales a la vez. Actions serializa las ejecuciones con el grupo de concurrencia `update-data`.

Las audiencias de gestión de intereses tienen una fuente y un pipeline separados. El nuevo workflow mensual se ocupa de los accesos de Drive; los comandos `update-audiencias`, enriquecimiento y cruce siguen disponibles manualmente y no bloquean la incorporación de accesos.

## Validación

Se prueban renombres, idempotencia, reemplazos válidos e inválidos, checksums, archivos vacíos, pérdida de fuentes, Office de años nuevos, deduplicación con historia repartida en particiones de otros años y rollback de la promoción. Los PDF escaneados requieren OCR futuro y permanecen en cuarentena.

## Reintentos de publicación

Cada intento de GitHub Pages usa un nombre de artefacto único y espera hasta dos minutos a que GitHub confirme su disponibilidad. Esto evita confundir archivos de intentos anteriores y desplegar antes de que el archivo subido sea visible. Si GitHub falla, se puede reintentar el workflow de publicación sin volver a importar los datos.
