/**
 * Daily auto-respond usage counter (Epic 03 · 3.4). Tracks tokens + cost spent
 * since local midnight and enforces the per-agent daily budget. Persisted to
 * disk so a daemon restart can't reset the budget mid-day; the clock is
 * injectable so the day-boundary reset is testable.
 */

import { existsSync, readFileSync, writeFileSync } from "node:fs";

export interface UsageDelta {
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
}

interface DailyState {
  day: string; // local YYYY-M-D
  tokens: number;
  cost: number;
}

export class DailyUsageTracker {
  private state: DailyState;

  constructor(
    private readonly path: string,
    private readonly now: () => number = Date.now,
  ) {
    this.state = this.load();
  }

  /** Local calendar day key (resets at local midnight, per the spec). */
  private dayKey(): string {
    const d = new Date(this.now());
    return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
  }

  private load(): DailyState {
    try {
      if (existsSync(this.path)) {
        const raw = JSON.parse(readFileSync(this.path, "utf-8"));
        if (typeof raw?.day === "string") {
          return { day: raw.day, tokens: Number(raw.tokens) || 0, cost: Number(raw.cost) || 0 };
        }
      }
    } catch {
      // corrupt/unreadable counter → start fresh (fail safe, not fail open)
    }
    return { day: this.dayKey(), tokens: 0, cost: 0 };
  }

  private persist(): void {
    try {
      writeFileSync(this.path, JSON.stringify(this.state), { mode: 0o600 });
    } catch {
      // best-effort: a missed write only risks under-counting after a crash
    }
  }

  /** Rolls the counter to today if the local day changed since the last write. */
  private roll(): void {
    const today = this.dayKey();
    if (this.state.day !== today) {
      this.state = { day: today, tokens: 0, cost: 0 };
      this.persist();
    }
  }

  /** True if today's spend already meets/exceeds either cap. null = unlimited. */
  exceeds(maxTokens: number | null, maxCost: number | null): boolean {
    this.roll();
    if (maxTokens != null && this.state.tokens >= maxTokens) return true;
    if (maxCost != null && this.state.cost >= maxCost) return true;
    return false;
  }

  /** Adds a run's usage to today's totals. No-op when usage wasn't captured. */
  add(usage: UsageDelta | null): void {
    if (!usage) return;
    this.roll();
    this.state.tokens += (usage.input_tokens ?? 0) + (usage.output_tokens ?? 0);
    this.state.cost += usage.cost_usd ?? 0;
    this.persist();
  }

  /** Today's accumulated totals (for metrics/tests). */
  today(): { tokens: number; cost: number } {
    this.roll();
    return { tokens: this.state.tokens, cost: this.state.cost };
  }
}
