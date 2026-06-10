import type { Area } from "react-easy-crop";

/** Square side of the exported avatar, in pixels. */
const OUTPUT_SIZE = 256;
const MAX_BYTES = 5 * 1024 * 1024;

/** Reject anything that isn't a reasonably sized image before we read it. */
export function validateImageFile(file: File): string | null {
  if (!file.type.startsWith("image/")) return "Selecione um arquivo de imagem.";
  if (file.size > MAX_BYTES) return "A imagem deve ter no máximo 5 MB.";
  return null;
}

export function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("Falha ao ler o arquivo."));
    reader.readAsDataURL(file);
  });
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Falha ao carregar a imagem."));
    image.src = src;
  });
}

/**
 * Render the cropped region to a fixed-size square canvas and return a JPEG data
 * URL. Re-encoding through the canvas also strips EXIF/metadata, so we only ever
 * store our own pixels.
 */
export async function getCroppedImage(src: string, area: Area): Promise<string> {
  const image = await loadImage(src);
  const canvas = document.createElement("canvas");
  canvas.width = OUTPUT_SIZE;
  canvas.height = OUTPUT_SIZE;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Não foi possível processar a imagem.");
  ctx.drawImage(image, area.x, area.y, area.width, area.height, 0, 0, OUTPUT_SIZE, OUTPUT_SIZE);
  return canvas.toDataURL("image/jpeg", 0.9);
}
