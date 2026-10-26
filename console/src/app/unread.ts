import { computed, inject, Injectable, signal } from '@angular/core';
import { forkJoin } from 'rxjs';

import { Api, Channel, Conversation } from './api';

/** Where what was seen on each channel and conversation is kept, in this browser. */
export const SEEN = 'mc.console.channels.seen';
/** How often the channels and conversations are read again for their unread counts (ms). */
export const UNREAD_REFRESH_MS = 20_000;

/** What was seen, as of a run of the bot: each one's heard count when last looked at. */
interface Seen {
  started: number | null;
  /** By channel slot. */
  slots: Record<number, number>;
  /** By contact key. */
  dms: Record<string, number>;
}

/**
 * The unread counts of the channels and the console's conversations, as the
 * phone app keeps its chats': each one's messages heard since the bot
 * started, less those heard when it was last open, kept in this browser. A
 * restart of the bot starts the counts again. Read every UNREAD_REFRESH_MS
 * from the app's frame, for the count beside Chat.
 */
@Injectable({ providedIn: 'root' })
export class Unread {
  private readonly api = inject(Api);
  readonly channels = signal<Channel[] | null>(null);
  readonly problem = signal<string | null>(null);
  /** null until read, or if the bot keeps none. */
  readonly conversations = signal<Conversation[] | null>(null);
  readonly conversationsRead = signal(false);
  readonly conversationsProblem = signal<string | null>(null);
  private readonly started = signal<number | null>(null);
  private readonly seen = signal<Seen>(this.stored());

  /** Unread messages across the channels in use. */
  readonly channelTotal = computed(() =>
    (this.channels() ?? []).reduce((sum, c) => sum + this.count(c.slot, c.heard), 0),
  );
  /** Unread replies across the conversations. */
  readonly dmTotal = computed(() =>
    (this.conversations() ?? []).reduce((sum, c) => sum + this.dmCount(c.key, c.heard), 0),
  );
  readonly total = computed(() => this.channelTotal() + this.dmTotal());

  refresh(): void {
    forkJoin({ channels: this.api.channels(), overview: this.api.overview() }).subscribe({
      next: ({ channels, overview }) => {
        this.started.set(overview.started);
        this.channels.set(channels);
        this.problem.set(null);
      },
      error: () => this.problem.set("can't read the radio's channels"),
    });
    this.refreshConversations();
  }

  refreshConversations(): void {
    this.api.conversations().subscribe({
      next: (conversations) => {
        this.conversations.set(conversations);
        this.conversationsRead.set(true);
        this.conversationsProblem.set(null);
      },
      error: () => this.conversationsProblem.set("can't read the console's conversations"),
    });
  }

  /** The slot's unread messages, given how many have been heard on it. */
  count(slot: number, heard: number | null): number {
    return this.left(heard, this.current()?.slots[slot]);
  }

  /** The contact's unread replies, given how many have been heard. */
  dmCount(key: string, heard: number | null): number {
    return this.left(heard, this.current()?.dms[key]);
  }

  unread(slot: number): number {
    return this.count(slot, this.channels()?.find((c) => c.slot === slot)?.heard ?? null);
  }

  /** The slot's messages have been seen, up to heard. */
  read(slot: number, heard: number | null): void {
    if (this.mark(heard, (seen) => (seen.slots[slot] = heard!))) {
      this.channels.update(
        (channels) =>
          channels?.map((c) =>
            c.slot === slot ? { ...c, heard: Math.max(c.heard ?? 0, heard!) } : c,
          ) ?? null,
      );
    }
  }

  /** The contact's replies have been seen, up to heard. */
  readDm(key: string, heard: number | null): void {
    if (this.mark(heard, (seen) => (seen.dms[key] = heard!))) {
      this.conversations.update(
        (conversations) =>
          conversations?.map((c) =>
            c.key === key ? { ...c, heard: Math.max(c.heard, heard!) } : c,
          ) ?? null,
      );
    }
  }

  /** What was seen in this run of the bot; null if it's from another (or none yet). */
  private current(): Seen | null {
    const seen = this.seen();
    return seen.started === this.started() ? seen : null;
  }

  private left(heard: number | null, before: number | undefined): number {
    return heard ? Math.max(0, heard - (before ?? 0)) : 0;
  }

  /** Change what was seen and keep it; false if it can't be yet. */
  private mark(heard: number | null, change: (seen: Seen) => void): boolean {
    const started = this.started();
    if (heard === null || started === null) {
      return false;
    }
    const current = this.current();
    const seen: Seen = {
      started,
      slots: { ...(current?.slots ?? {}) },
      dms: { ...(current?.dms ?? {}) },
    };
    change(seen);
    this.seen.set(seen);
    try {
      localStorage.setItem(SEEN, JSON.stringify(seen));
    } catch {
      // Not kept (a private window): seen until the page closes.
    }
    return true;
  }

  private stored(): Seen {
    try {
      const stored = JSON.parse(localStorage.getItem(SEEN) ?? 'null');
      if (stored && typeof stored === 'object' && typeof stored.slots === 'object') {
        return {
          started: stored.started ?? null,
          slots: stored.slots ?? {},
          dms: typeof stored.dms === 'object' && stored.dms ? stored.dms : {},
        };
      }
    } catch {
      // Unreadable: start again.
    }
    return { started: null, slots: {}, dms: {} };
  }
}
