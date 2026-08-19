export async function fetchGzipJson<T>(url: URL, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {signal});
  if (!response.ok) throw new Error(`No se pudo cargar ${url.pathname}`);
  if (response.headers.get("content-encoding")?.includes("gzip")) {
    return response.json() as Promise<T>;
  }
  if (!response.body) throw new Error(`La respuesta de ${url.pathname} está vacía`);
  const decompressed = response.body.pipeThrough(new DecompressionStream("gzip"));
  return new Response(decompressed).json() as Promise<T>;
}
