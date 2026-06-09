# Ampla logos

Drop the official artwork here, keeping these exact filenames — the `Logo`
component (`src/components/Logo.tsx`) references them by `variant` + `tone`.

| File | variant | tone | Use on |
|------|---------|------|--------|
| `ampla-icon-white.svg`  | `icon` (bolinha)   | `white` (clara)  | dark backgrounds |
| `ampla-icon-black.svg`  | `icon` (bolinha)   | `black` (escura) | light backgrounds |
| `ampla-full-white.svg`  | `full` (completa)  | `white` (clara)  | dark backgrounds |
| `ampla-full-black.svg`  | `full` (completa)  | `black` (escura) | light backgrounds |

The files committed now are **placeholders** (a beehive hexagon) — replace them
with the real logos. SVG preferred (crisp at any size); same `viewBox` keeps the
layout. The UI is dark, so it uses the `white` variants by default.
