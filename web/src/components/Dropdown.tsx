import { useEffect, useRef, useState } from "react";

export interface DropdownOption {
  value: string;
  label: string;
}

/** Custom select: a styled trigger + popover list (native <select> can't be
 * themed). Keeps an aria-label on the trigger so it's reachable by label.
 * `up` opens the list upward (for triggers near the bottom, e.g. the composer). */
export function Dropdown({
  value,
  onChange,
  options,
  ariaLabel,
  placeholder = "—",
  up = false,
  className = "",
}: {
  value: string;
  onChange: (value: string) => void;
  options: DropdownOption[];
  ariaLabel?: string;
  placeholder?: string;
  up?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const selected = options.find((o) => o.value === value);

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        className="flex w-full items-center justify-between gap-2 rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-left text-sm text-zinc-200 outline-none transition-colors hover:border-zinc-600 focus:border-amber-500"
      >
        <span className="truncate">{selected ? selected.label : placeholder}</span>
        <span className="shrink-0 text-xs text-zinc-500" aria-hidden>
          ▾
        </span>
      </button>
      {open && (
        <div
          role="listbox"
          className={`absolute z-20 flex max-h-64 w-full min-w-max flex-col overflow-auto rounded-md border border-zinc-700 bg-zinc-900 py-1 shadow-lg shadow-black/40 ${
            up ? "bottom-full mb-1" : "top-full mt-1"
          }`}
        >
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              role="option"
              aria-selected={o.value === value}
              onClick={() => {
                onChange(o.value);
                setOpen(false);
              }}
              className={`flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-zinc-800 ${
                o.value === value ? "text-amber-300" : "text-zinc-300"
              }`}
            >
              <span className="w-3 shrink-0" aria-hidden>
                {o.value === value ? "✓" : ""}
              </span>
              <span className="truncate">{o.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
