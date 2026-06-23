import { api } from "./client";
import type { Preset, PresetSettings } from "./types";

export const presetsApi = {
  list: () => api.get<Preset[]>("/api/guardrail-presets"),
  create: (name: string, settings: PresetSettings) =>
    api.post<Preset>("/api/guardrail-presets", { name, settings }),
  // Edit a preset's name and/or settings (owner-only on the hub).
  update: (id: number, data: { name?: string; settings?: PresetSettings }) =>
    api.patch<Preset>(`/api/guardrail-presets/${id}`, data),
  remove: (id: number) => api.delete<void>(`/api/guardrail-presets/${id}`),
};
