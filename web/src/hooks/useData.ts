import {useEffect, useState} from "react";

export function useData<T>(path: string): {data: T | null; error: string | null; loading: boolean} {
  const [state, setState] = useState<{data: T | null; error: string | null; loading: boolean}>({data: null, error: null, loading: true});
  useEffect(() => {
    const controller = new AbortController();
    setState({data: null, error: null, loading: true});
    fetch(new URL(`data/${path}`, document.baseURI), {signal: controller.signal})
      .then((response) => {
        if (!response.ok) throw new Error("No se pudieron cargar los datos publicados");
        return response.json() as Promise<T>;
      })
      .then((data) => setState({data, error: null, loading: false}))
      .catch((error: unknown) => {
        if ((error as Error).name !== "AbortError") setState({data: null, error: (error as Error).message, loading: false});
      });
    return () => controller.abort();
  }, [path]);
  return state;
}
