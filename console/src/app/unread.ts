import { computed, inject, Injectable, signal } from '@angular/core';
import { forkJoin } from 'rxjs';

import { Api, Channel } from './api';

/** Where what was seen on each channel is kept, in this browser. */
export const SEEN = 'mc.console.channels.seen';
/** How often the channels are read again for their unread counts (ms). */
export const UNREAD_REFRESH_MS = 20_000;

/** What was seen, as of a run of the bot: each slot's heard count when last looked at. */
interface Seen {
  started: number | null;
  slots: Record<number, number>;
}

/**
 * The channels' unread counts, as the phone app keeps its chats': each
 * channel's messages heard since the bot started, less those heard when it
 * was last open, kept in this browser. A restart of the bot starts the
 * counts again. Read every UNREAD_REFRESH_MS from the app's frame, for the
 * count beside Chat.
 */
@Injectable({ providedIn: 'root' })
export class Unread {
  private readonly api = inject(Api);
  readonly channels = signal<Channel[] | null>(null);
  readonly problem = signal<string | null>(null);
  private readonly started = signal<number | null>(null);
  private readonly seen = signal<Seen>(this.stored());

  /** Unread messages across the channels in use. */
  readonly total = computed(() =>
    (this.channels() ?? []).reduce((sum, c) => sum + this.count(c.slot, c.heard), 0),
  );

  refresh(): void {
    forkJoin({ channels: this.api.channels(), overview: this.api.overview() }).subscribe({
      next: ({ channels, overview }) => {
        this.started.set(overview.started);
        this.channels.set(channels);
        this.problem.set(null);
      },
      error: () => this.problem.set("can't read the radio's channels"),
    });
  }

  /** The slot's unread messages, given how many have been heard on it. */
  count(slot: number, heard: number | null): number {
    if (!heard) {
      return 0;
    }
    const seen = this.seen();
    const before = seen.started === this.started() ? (seen.slots[slot] ?? 0) : 0;
    return Math.max(0, heard - before);
  }

  unread(slot: number): number {
    return this.count(slot, this.channels()?.find((c) => c.slot === slot)?.heard ?? null);
  }

  /** The slot's messages have been seen, up to heard. */
  read(slot: number, heard: number | null): void {
    const started = this.started();
    if (heard === null || started === null) {
      return;
    }
    const seen = this.seen();
    const slots = seen.started === started ? { ...seen.slots } : {};
    slots[slot] = heard;
    this.seen.set({ started, slots });
    this.channels.update(
      (channels) =>
        channels?.map((c) =>
          c.slot === slot ? { ...c, heard: Math.max(c.heard ?? 0, heard) } : c,
        ) ?? null,
    );
    try {
      localStorage.setItem(SEEN, JSON.stringify(this.seen()));
    } catch {
      // Not kept (a private window): seen until the page closes.
    }
  }

  private stored(): Seen {
    try {
      const stored = JSON.parse(localStorage.getItem(SEEN) ?? 'null');
      if (stored && typeof stored === 'object' && typeof stored.slots === 'object') {
        return { started: stored.started ?? null, slots: stored.slots ?? {} };
      }
    } catch {
      // Unreadable: start again.
    }
    return { started: null, slots: {} };
  }
}
