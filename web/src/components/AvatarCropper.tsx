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
      {/* Sizes to the photo (capped to the viewport); not forced full-screen. */}
      <div className="flex max-h-[92vh] max-w-[92vw] flex-col overflow-hidden rounded border border-zinc-800 bg-zinc-900 shadow-lg shadow-black/40">
        <h2 className="border-b border-zinc-800 px-4 py-3 text-sm font-medium text-zinc-200">
          Recortar foto
        </h2>
        <div className="min-h-0 overflow-auto bg-zinc-950">
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
              className="block max-h-[78vh] max-w-[90vw] w-auto"
            />
          </ReactCrop>
        </div>
        {error && (
          <p role="alert" className="border-t border-zinc-800 px-4 py-2 text-xs text-red-400">
            {error}
          </p>
        )}
        {/* Split footer: half cancel, half save. */}
        <div className="flex border-t border-zinc-800">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 py-3 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-800"
          >
            Cancelar
          </button>
          <div aria-hidden="true" className="w-px bg-zinc-800" />
          <button
            type="button"
            onClick={handleSave}
            disabled={busy || !completed?.width}
            className="flex-1 py-3 text-sm font-semibold text-amber-400 transition-colors hover:bg-amber-500/10 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
          >
            Salvar
          </button>
        </div>
      </div>
    </div>
  );
}
