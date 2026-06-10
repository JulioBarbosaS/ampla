import type { User } from "../lib/api/types";
import { useAvatarStore } from "../stores/avatar";

/**
 * The user's avatar: their cropped photo when one is set, otherwise the name's
 * initial. Presentational only (a span/img) so it can sit inside a button or a
 * header row.
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
  const photo = useAvatarStore((s) => (user ? (s.photos[user.id] ?? null) : null));

  if (photo) {
    return (
      <img src={photo} alt={alt} className={`${sizeClass} shrink-0 rounded-full object-cover`} />
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
