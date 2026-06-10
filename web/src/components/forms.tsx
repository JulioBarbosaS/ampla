/** Shared form primitives used by the auth and agents screens. */

import type { InputHTMLAttributes, ReactNode } from "react";
import { Logo } from "./Logo";

export function Field({
  label,
  ...props
}: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm text-zinc-400">{label}</span>
      <input
        {...props}
        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm outline-none transition-colors focus:border-amber-500"
      />
    </label>
  );
}

export function PrimaryButton({ children, disabled }: { children: ReactNode; disabled?: boolean }) {
  return (
    <button
      type="submit"
      disabled={disabled}
      className="w-full rounded-md bg-amber-500 px-3 py-2 text-sm font-semibold text-black transition-colors hover:bg-amber-400 disabled:opacity-50"
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
    <div className="flex h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-2">
          <Logo variant="full" className="h-11" />
          <h1 className="text-sm font-medium text-zinc-400">{title}</h1>
        </div>
        {children}
      </div>
    </div>
  );
}
