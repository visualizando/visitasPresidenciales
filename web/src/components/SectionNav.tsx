import {useEffect, useState} from "react";

const ITEMS = [
  {id: "buscar", label: "Buscar"},
  {id: "panorama", label: "Actividad"},
  {id: "descargas", label: "Descargas"},
  {id: "rankings", label: "Rankings"},
  {id: "cobertura", label: "Cobertura"},
] as const;

export function SectionNav({preserveHash = false}: {preserveHash?: boolean}) {
  const [activeId, setActiveId] = useState<(typeof ITEMS)[number]["id"]>(ITEMS[0].id);

  useEffect(() => {
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const threshold = Math.min(180, window.innerHeight * 0.28);
        let current: (typeof ITEMS)[number]["id"] = ITEMS[0].id;
        for (const item of ITEMS) {
          const section = document.getElementById(item.id);
          if (section && section.getBoundingClientRect().top <= threshold) current = item.id;
        }
        setActiveId(current);
      });
    };
    update();
    window.addEventListener("scroll", update, {passive: true});
    window.addEventListener("resize", update);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  return <div className="section-nav-wrap">
    <nav className="section-nav" aria-label="Secciones de la página">
      {ITEMS.map((item) => <a key={item.id} href={`#${item.id}`} aria-current={activeId === item.id ? "location" : undefined} onClick={(event) => {
        if (!preserveHash) return;
        event.preventDefault();
        document.getElementById(item.id)?.scrollIntoView({behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start"});
      }}>{item.label}</a>)}
    </nav>
  </div>;
}
