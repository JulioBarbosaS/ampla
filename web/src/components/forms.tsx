/** Primitivas de formulário compartilhadas pelas telas de auth e agentes. */

import type { InputHTMLAttributes, ReactNode } from "react";

export function Field({
  label,
  ...props
}: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm text-zinc-400">{label}</span>
      <input
        {...props}
        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm outline-none transition-colors focus:border-emerald-500"
      />
    </label>
  );
}

export function PrimaryButton({ children, disabled }: { children: ReactNode; disabled?: boolean }) {
  return (
    <button
      type="submit"
      disabled={disabled}
      className="w-full rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
    >
      {children}
    </button>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md bg-red-950/60 px-3 py-2 text-sm text-red-300">
      {message}
    </p>
  );
}

export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-4">
        <div className="text-center">
          <span className="text-2xl font-bold text-emerald-400">Ampla</span>
          <h1 className="mt-1 text-lg font-medium text-zinc-200">{title}</h1>
        </div>
        {children}
      </div>
    </div>
  );
}
