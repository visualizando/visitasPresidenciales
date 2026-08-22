export function exactNameShardKeys(tokens: string[], available: string[]): Set<string> {
  const keys = new Set<string>();
  const availableSet = new Set(available);
  for (const token of tokens) {
    if (token.length >= 3) {
      const key = safeShard(token.slice(0, 3));
      if (availableSet.has(key)) keys.add(key);
    } else if (token.length === 2) {
      const prefix = safeShard(token);
      for (const key of available) if (key.startsWith(prefix)) keys.add(key);
    }
  }
  return keys;
}

export function broadNameShardKeys(tokens: string[], available: string[]): Set<string> {
  const initials = new Set(tokens.filter(Boolean).map((token) => safeShard(token[0])));
  return new Set(available.filter((key) => [...initials].some((initial) => key.startsWith(initial))));
}

function safeShard(value: string): string {
  const normalized = value.toLowerCase();
  return /^[a-z0-9]+$/.test(normalized) ? normalized : "_";
}
