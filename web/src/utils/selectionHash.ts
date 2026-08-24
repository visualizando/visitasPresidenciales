const PERSON_HASH_PREFIX = "#person=";

export function buildSelectionHash(entityIds: string[]) {
  const uniqueIds = [...new Set(entityIds.filter(isEntityId))];
  return uniqueIds.length ? `${PERSON_HASH_PREFIX}${uniqueIds.map(encodeURIComponent).join(",")}` : "";
}

export function parseSelectionHash(hash: string): string[] | null {
  if (!hash.startsWith(PERSON_HASH_PREFIX)) return null;
  const encodedIds = hash.slice(PERSON_HASH_PREFIX.length).split(",").filter(Boolean);
  const ids: string[] = [];
  for (const encodedId of encodedIds) {
    try {
      const entityId = decodeURIComponent(encodedId);
      if (isEntityId(entityId) && !ids.includes(entityId)) ids.push(entityId);
    } catch {
      // Ignore malformed URL fragments and retain any valid IDs.
    }
  }
  return ids;
}

export function selectionIdShard(entityId: string) {
  const suffix = entityId.slice(-2).toLowerCase();
  return /^[a-z0-9]+$/.test(suffix) ? suffix : "_";
}

function isEntityId(value: string) {
  return /^[a-zA-Z0-9_-]{1,128}$/.test(value);
}
