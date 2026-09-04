import {Check, Share2} from "lucide-react";
import {useEffect, useRef, useState} from "react";
import {copyText} from "../utils/clipboard";

export function ShareButton() {
  const timer = useRef<number | null>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);

  async function share() {
    try {
      await copyText(window.location.href);
      setCopied(true);
    } catch {
      setCopied(false);
    }
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCopied(false), 2_000);
  }

  return <button className="selection-download" type="button" onClick={share}>{copied ? <Check aria-hidden="true" /> : <Share2 aria-hidden="true" />}{copied ? "Copiado" : "Compartir"}</button>;
}
