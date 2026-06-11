import { create } from "zustand";

/**
 * Global kill switch view-state (Epic 03 · 3.2). Source of truth is the hub; the
 * WS observer feeds it (hello_ack flag + live `kill_switch` frames). The panel
 * reads it to show an instance-wide banner when auto-respond is suspended.
 */
interface KillSwitchState {
  autoResponderEnabled: boolean;
  setAutoResponderEnabled: (enabled: boolean) => void;
}

export const useKillSwitchStore = create<KillSwitchState>()((set) => ({
  autoResponderEnabled: true,
  setAutoResponderEnabled: (enabled) =>
    set((s) => (s.autoResponderEnabled === enabled ? s : { autoResponderEnabled: enabled })),
}));
