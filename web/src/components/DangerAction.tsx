import { useState } from "react";

const dangerBtn =
  "rounded-md border border-red-700 px-2.5 py-1 text-xs font-medium text-red-300 hover:bg-red-950/40";

/** A high-risk action gated behind three confirmations (warn → reconfirm →
 * type the confirm word), GitHub danger-zone style. Reused for per-agent and
 * instance-wide controls (Epic 03 · 3.2 kill switch). */
export function DangerAction({
  trigger,
  warning,
  confirmWord,
  onConfirm,
}: {
  trigger: string;
  warning: string;
  confirmWord: string;
  onConfirm: () => void;
}) {
  const [step, setStep] = useState<0 | 1 | 2 | 3>(0);
  const [typed, setTyped] = useState("");
  const reset = () => {
    setStep(0);
    setTyped("");
  };

  if (step === 0) {
    return (
      <button type="button" onClick={() => setStep(1)} className={dangerBtn}>
        {trigger}
      </button>
    );
  }

  const cancel = (
    <button
      type="button"
      onClick={reset}
      className="rounded-md bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
    >
      Cancelar
    </button>
  );

  return (
    <div className="space-y-2 rounded-md border border-red-800 bg-red-950/40 p-2.5 text-xs">
      <p className="text-red-200">{warning}</p>
      {step === 1 && (
        <div className="flex gap-2">
          {cancel}
          <button type="button" onClick={() => setStep(2)} className={dangerBtn}>
            Entendo o risco
          </button>
        </div>
      )}
      {step === 2 && (
        <div className="flex gap-2">
          {cancel}
          <button type="button" onClick={() => setStep(3)} className={dangerBtn}>
            Confirmar de novo
          </button>
        </div>
      )}
      {step === 3 && (
        <div className="space-y-1.5">
          <p className="text-red-200">
            Digite <span className="font-mono font-semibold">{confirmWord}</span> para aplicar:
          </p>
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={confirmWord}
            className="w-full rounded-md border border-red-700 bg-zinc-900 px-2.5 py-1.5 text-sm outline-none focus:border-red-500"
          />
          <div className="flex gap-2">
            {cancel}
            <button
              type="button"
              disabled={typed !== confirmWord}
              onClick={() => {
                onConfirm();
                reset();
              }}
              className={`${dangerBtn} disabled:cursor-not-allowed disabled:opacity-40`}
            >
              Aplicar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
