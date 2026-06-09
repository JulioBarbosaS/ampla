/**
 * Ampla logo. Art lives in public/logo/ (see public/logo/README.md) and is
 * picked by variant (icon = bolinha · full = completa) and tone (white = clara,
 * for dark backgrounds · black = escura, for light). The UI is dark, so tone
 * defaults to "white". Replace the placeholder SVGs with the real artwork.
 */
export function Logo({
  variant = "full",
  tone = "white",
  className,
}: {
  variant?: "icon" | "full";
  tone?: "white" | "black";
  className?: string;
}) {
  return <img src={`/logo/ampla-${variant}-${tone}.svg`} alt="Ampla" className={className} />;
}
