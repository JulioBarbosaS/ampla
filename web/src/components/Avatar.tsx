import { useState } from "react";
import type { User } from "../lib/api/types";
import { useAvatarStore } from "../stores/avatar";

/**
 * The user's avatar: their photo served by the hub when one is set, otherwise
 * the name's initial. The image is loaded from `/api/users/{id}/avatar` (same
 * origin → the session cookie rides along); a 404/!image falls back to the
 * initial. `version` cache-busts after an upload/remove.
 */
export function Avatar({
  user,
  sizeClass = "h-8 w-8",
  textClass = "text-sm",
  alt = "",
}: {
  user: User | null;
  sizeClass?: string;
  textClass?: string;
  alt?: string;
}) {
  const version = useAvatarStore((s) => (user ? (s.version[user.id] ?? 0) : 0));
  const setPresent = useAvatarStore((s) => s.setPresent);
  // Track the version that failed to load; a new version (upload/remove) clears
  // it implicitly (failedAt !== version), so the image is retried — no effect.
  const [failedAt, setFailedAt] = useState<number | null>(null);

  if (user && failedAt !== version) {
    return (
      <img
        key={version}
        src={`/api/users/${user.id}/avatar?v=${version}`}
        alt={alt}
        onLoad={() => setPresent(user.id, true)}
        onError={() => {
          setFailedAt(version);
          setPresent(user.id, false);
        }}
        className={`${sizeClass} shrink-0 rounded-full object-cover`}
      />
    );
  }

  return (
    <span
      aria-hidden="true"
      className={`flex ${sizeClass} ${textClass} shrink-0 items-center justify-center rounded-full bg-zinc-800 font-semibold text-amber-300`}
    >
      {user?.name?.charAt(0).toUpperCase() ?? "?"}
    </span>
  );
}
