import { useCallback, useEffect, useState } from "react";
import api, { getStoredUser } from "./api";

// In-memory GET cache that survives client-side navigation (it lives at module scope, so leaving a
// page and coming back reuses the last result instead of re-hitting slow endpoints). Within `ttl`
// the cached value is served instantly with no network call; `refresh()` always refetches and
// updates the cache. Keys are scoped to the signed-in user id AND the URL, so that switching
// accounts on the same browser never serves one user's data to another (e.g. "You vs the team").

const mem = new Map();              // "<userId>|<url>" -> { data, at }
const _key = (url) => `${getStoredUser()?.id ?? "anon"}|${url}`;

export function bustCache(prefix) {
  if (!prefix) { mem.clear(); return; }
  for (const k of Array.from(mem.keys())) if (k.includes(prefix)) mem.delete(k);
}

export function peekCache(url) {
  const c = mem.get(_key(url));
  return c ? c.data : null;
}

export function useCachedGet(url, { ttl = 10 * 60 * 1000, enabled = true } = {}) {
  const initial = (enabled && url) ? mem.get(_key(url)) : null;
  const [data, setData] = useState(initial ? initial.data : null);
  const [loading, setLoading] = useState(enabled && !!url && !initial);
  const [error, setError] = useState(false);

  // Write-through setter: optimistic UI updates (e.g. removing an actioned card) also update the
  // module cache, so they survive navigation instead of reappearing on return.
  const setBoth = useCallback((updater) => {
    setData((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      if (url) mem.set(_key(url), { data: next, at: Date.now() });
      return next;
    });
  }, [url]);

  const fetchNow = useCallback(() => {
    if (!url || !enabled) return Promise.resolve();
    setLoading(true); setError(false);
    return api.get(url)
      .then((d) => { mem.set(_key(url), { data: d, at: Date.now() }); setData(d); return d; })
      .catch((e) => { setError(true); throw e; })
      .finally(() => setLoading(false));
  }, [url, enabled]);

  useEffect(() => {
    if (!enabled || !url) return;
    const c = mem.get(_key(url));
    if (c && Date.now() - c.at < ttl) {     // fresh enough → serve instantly, no fetch
      setData(c.data); setLoading(false); return;
    }
    if (c) setData(c.data);                 // show stale immediately while we refetch
    fetchNow().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, enabled]);

  return { data, loading, error, refresh: fetchNow, setData: setBoth };
}
