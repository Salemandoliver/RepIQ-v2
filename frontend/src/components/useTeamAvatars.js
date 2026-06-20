import { useEffect, useState } from "react";
import api from "../api";

// Map of userId -> profile-photo data URL, fetched once and shared across the app (module-level
// cache + in-flight de-dup) so call lists can show faces without each page refetching.
let _cache = null;
let _promise = null;

export function useTeamAvatars() {
  const [map, setMap] = useState(_cache || {});
  useEffect(() => {
    let live = true;
    if (_cache) { setMap(_cache); return; }
    if (!_promise) {
      _promise = api.get("/api/v1/hr/team/avatars")
        .then((d) => { _cache = d?.avatars || {}; return _cache; })
        .catch(() => ({}));
    }
    _promise.then((m) => { if (live) setMap(m || {}); });
    return () => { live = false; };
  }, []);
  return map;
}

// The name to show for a call host: their preferred / "known as" name, else their full name.
export function hostName(host) {
  return host?.short_name || host?.name || "Unknown host";
}
