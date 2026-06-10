import { useRef, useState } from "react";
import ReactCrop, { type Crop, centerCrop, makeAspectCrop, type PixelCrop } from "react-image-crop";
import { getCroppedImage } from "../lib/crop";

/** Modal that crops a freshly-picked image into a square avatar (round preview)
 * via react-image-crop's selection handles, then hands the cropped data URL back
 * through onSave. */
export function AvatarCropper({
  image,
  onCancel,
  onSave,
}: {
  image: string;
  onCancel: () => void;
  onSave: (dataUrl: string) => void;
}) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [crop, setCrop] = useState<Crop>();
  const [completed, setCompleted] = useState<PixelCrop>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function onImageLoad(event: React.SyntheticEvent<HTMLImageElement>) {
    const { width, height } = event.currentTarget;
    // Start with a centered square covering most of the image.
    setCrop(centerCrop(makeAspectCrop({ unit: "%", width: 90 }, 1, width, height), width, height));
  }

  function handleSave() {
    if (!imgRef.current || !completed?.width) return;
    setBusy(true);
    setError(null);
    try {
      onSave(getCroppedImage(imgRef.current, completed));
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
      <div className="w-full max-w-2xl rounded-lg border border-zinc-800 bg-zinc-900 p-5 shadow-lg shadow-black/40">
        <h2 className="mb-3 text-sm font-medium text-zinc-200">Recortar foto</h2>
        <div className="flex max-h-[70vh] justify-center overflow-hidden rounded-md bg-zinc-950">
          <ReactCrop
            crop={crop}
            onChange={(_, percentCrop) => setCrop(percentCrop)}
            onComplete={setCompleted}
            aspect={1}
            circularCrop
            keepSelection
          >
            {/* alt empty: decorative — the dialog is already labelled */}
            <img
              ref={imgRef}
              src={image}
              alt=""
              onLoad={onImageLoad}
              className="max-h-[70vh] w-auto object-contain"
            />
          </ReactCrop>
        </div>
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
            disabled={busy || !completed?.width}
            className="rounded-md bg-amber-500 px-3 py-2 text-sm font-semibold text-black transition-colors hover:bg-amber-400 disabled:opacity-50"
          >
            Salvar
          </button>
        </div>
      </div>
    </div>
  );
}
