import { api } from "./client";
import type { Preset, PresetSettings } from "./types";

export const presetsApi = {
  list: () => api.get<Preset[]>("/api/guardrail-presets"),
  create: (name: string, settings: PresetSettings) =>
    api.post<Preset>("/api/guardrail-presets", { name, settings }),
  remove: (id: number) => api.delete<void>(`/api/guardrail-presets/${id}`),
};
