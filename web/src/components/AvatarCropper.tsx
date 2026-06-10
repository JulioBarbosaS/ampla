import { useCallback, useState } from "react";
import Cropper, { type Area } from "react-easy-crop";
import { getCroppedImage } from "../lib/crop";

/** Modal that crops a freshly-picked image into a square avatar (round preview)
 * with drag + zoom, then hands the cropped data URL back via onSave. */
export function AvatarCropper({
  image,
  onCancel,
  onSave,
}: {
  image: string;
  onCancel: () => void;
  onSave: (dataUrl: string) => void;
}) {
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [area, setArea] = useState<Area | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onCropComplete = useCallback((_: Area, areaPixels: Area) => setArea(areaPixels), []);

  async function handleSave() {
    if (!area) return;
    setBusy(true);
    setError(null);
    try {
      onSave(await getCroppedImage(image, area));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao recortar a imagem.");
      setBusy(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Recortar foto"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <div className="w-full max-w-sm rounded-lg border border-zinc-800 bg-zinc-900 p-4 shadow-lg shadow-black/40">
        <h2 className="mb-3 text-sm font-medium text-zinc-200">Recortar foto</h2>
        <div className="relative h-64 w-full overflow-hidden rounded-md bg-zinc-950">
          <Cropper
            image={image}
            crop={crop}
            zoom={zoom}
            aspect={1}
            cropShape="round"
            showGrid={false}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={onCropComplete}
          />
        </div>
        <label className="mt-3 block">
          <span className="mb-1 block text-xs text-zinc-500">Zoom</span>
          <input
            type="range"
            min={1}
            max={3}
            step={0.01}
            value={zoom}
            onChange={(event) => setZoom(Number(event.target.value))}
            aria-label="Zoom"
            className="w-full accent-amber-500"
          />
        </label>
        {error && (
          <p role="alert" className="mt-2 text-xs text-red-400">
            {error}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md px-3 py-2 text-sm text-zinc-300 transition-colors hover:bg-zinc-800"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={busy || !area}
            className="rounded-md bg-amber-500 px-3 py-2 text-sm font-semibold text-black transition-colors hover:bg-amber-400 disabled:opacity-50"
          >
            Salvar
          </button>
        </div>
      </div>
    </div>
  );
}
