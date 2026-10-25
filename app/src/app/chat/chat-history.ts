import { computed, DestroyRef, effect, inject, Injectable, signal } from '@angular/core';

import { NodeLink } from '../node/node-link';
import { ChannelMessage, DirectMessage, Radio, RadioChannel, RadioContact } from '../radio/radio';

/** Where the chats are kept on the phone. */
export const HISTORY = 'mc.chat';
/** Messages kept in each chat; older ones are dropped. */
export const MAX_KEPT = 200;
/** The longest message the app sends, as for commands (characters). */
export const MAX_TEXT = 133;

/** How a message the user sent is going. */
export type Status = 'sending' | 'delivered' | 'not delivered' | 'sent' | 'failed';

/** One message in a chat. */
export interface Line {
  id: number;
  /** The user sent it. */
  mine: boolean;
  /** On a channel, who sent it (their radio's name). */
  from?: string;
  text: string;
  at: number;
  /** How it's going: the user's own messages only. */
  status?: Status;
}

/** A chat and what's in it. */
export interface Chat {
  lines: Line[];
  unread: number;
}

/**
 * A chat's key: "dm:" and the contact's key prefix (12 hex characters, as a
 * direct message names its sender), or "ch:" and the channel's name (its
 * slot can change).
 */
export function dmKey(publicKey: string): string {
  return `dm:${publicKey.slice(0, 12)}`;
}

export function channelKey(name: string): string {
  return `ch:${name}`;
}

/** The longest post a channel takes from this radio: it goes out as "<name>: <text>". */
export function channelLimit(radioName: string | null): number {
  return MAX_TEXT - (radioName ?? '').length - 2;
}

/**
 * The chats with the radio's contacts and channels, kept on the phone (the
 * radio holds a message only until it's fetched). The node isn't one of
 * them: what's said with it is the Node screens' and is never kept.
 */
@Injectable({ providedIn: 'root' })
export class ChatHistory {
  private readonly radio = inject(Radio);
  private readonly link = inject(NodeLink);

  readonly chats = signal<Record<string, Chat>>(this.load());
  private lastId = Math.max(
    0,
    ...Object.values(this.chats()).flatMap((chat) => chat.lines.map((line) => line.id)),
  );
  /** The radio's channels, as last read. */
  readonly channels = signal<RadioChannel[]>([]);
  /** The radio's contacts, as last read: null until they are. */
  readonly contacts = signal<RadioContact[] | null>(null);
  /** The channels are being read. */
  readonly loadingChannels = signal(false);
  /** The contacts are being read, which takes a while with many of them. */
  readonly loadingContacts = signal(false);
  private reading: Promise<void> | null = null;
  /** Read since the radio last connected. */
  private fresh = false;
  /** The chat on the screen: its messages arrive read. */
  readonly open = signal<string | null>(null);
  readonly unread = computed(() => this.unreadIn(''));
  readonly unreadDirect = computed(() => this.unreadIn('dm:'));
  readonly unreadChannels = computed(() => this.unreadIn('ch:'));

  constructor() {
    const direct = this.radio.messages.subscribe((message) => this.heardDirect(message));
    const channel = this.radio.channelMessages.subscribe(
      (message) => void this.heardChannel(message),
    );
    inject(DestroyRef).onDestroy(() => {
      direct.unsubscribe();
      channel.unsubscribe();
    });
    // Read again on the next connection: it may be another radio.
    effect(() => {
      if (this.radio.state() !== 'connected') {
        this.fresh = false;
      }
    });
  }

  /**
   * Read the radio's channels, then its contacts (the slow part), unless
   * they were read since it connected (or `again`). One read at a time: a
   * second call waits for it.
   */
  refresh(again = false): Promise<void> {
    if (this.reading) {
      return this.reading;
    }
    if (this.radio.state() !== 'connected' || (this.fresh && !again)) {
      return Promise.resolve();
    }
    this.loadingChannels.set(true);
    this.loadingContacts.set(true);
    this.reading = (async () => {
      try {
        try {
          await this.loadChannels();
        } finally {
          this.loadingChannels.set(false);
        }
        this.contacts.set(await this.radio.contacts());
        this.fresh = true;
      } finally {
        this.loadingChannels.set(false);
        this.loadingContacts.set(false);
        this.reading = null;
      }
    })();
    return this.reading;
  }

  /** The contact with this key, or key prefix, as last read. */
  contact(key: string): RadioContact | undefined {
    return key ? this.contacts()?.find((c) => c.publicKey.startsWith(key)) : undefined;
  }

  /** Unread messages in the chats whose keys start so. */
  private unreadIn(prefix: string): number {
    return Object.entries(this.chats())
      .filter(([key]) => key.startsWith(prefix))
      .reduce((total, [, chat]) => total + chat.unread, 0);
  }

  /** Read the radio's channels again. */
  async loadChannels(): Promise<RadioChannel[]> {
    const channels = await this.radio.channels();
    this.channels.set(channels);
    return channels;
  }

  lines(key: string): Line[] {
    return this.chats()[key]?.lines ?? [];
  }

  read(key: string): void {
    if (this.chats()[key]?.unread) {
      this.change(key, (chat) => ({ ...chat, unread: 0 }));
    }
  }

  clear(key: string): void {
    const chats = { ...this.chats() };
    delete chats[key];
    this.save(chats);
  }

  clearAll(): void {
    this.save({});
  }

  /** Send a direct message, shown at once and marked delivered or not. */
  async sendDirect(publicKey: string, text: string): Promise<void> {
    const key = dmKey(publicKey);
    const line = this.add(key, { mine: true, text, at: Date.now(), status: 'sending' });
    let status: Status;
    try {
      status = (await this.radio.sendText(publicKey, text)) ? 'delivered' : 'not delivered';
    } catch {
      status = 'failed';
    }
    this.mark(key, line, status);
  }

  /** Post to a channel. Nothing acknowledges it: "sent" is the radio taking it. */
  async sendToChannel(channel: RadioChannel, text: string): Promise<void> {
    const key = channelKey(channel.name);
    const line = this.add(key, { mine: true, text, at: Date.now(), status: 'sending' });
    let status: Status;
    try {
      await this.radio.sendToChannel(channel.index, text);
      status = 'sent';
    } catch {
      status = 'failed';
    }
    this.mark(key, line, status);
  }

  private heardDirect(message: DirectMessage): void {
    const node = this.link.node();
    if (node?.publicKey.startsWith(message.from)) {
      return; // the node's: never kept
    }
    this.add(`dm:${message.from}`, { mine: false, text: message.text, at: message.receivedAt });
  }

  private async heardChannel(message: ChannelMessage): Promise<void> {
    let channel = this.channels().find((c) => c.index === message.channel);
    if (!channel) {
      channel = (await this.loadChannels().catch(() => [])).find(
        (c) => c.index === message.channel,
      );
    }
    const name = channel?.name ?? `Channel ${message.channel}`;
    // Sent as "<sender's name>: <text>".
    const split = /^([^:]{1,32}): ([\s\S]*)$/.exec(message.text);
    this.add(channelKey(name), {
      mine: false,
      from: split?.[1],
      text: split ? split[2] : message.text,
      at: message.receivedAt,
    });
  }

  /** Add a line; someone else's is unread unless the chat is open. */
  private add(key: string, line: Omit<Line, 'id'>): Line {
    const added = { id: ++this.lastId, ...line };
    const unread = !line.mine && this.open() !== key ? 1 : 0;
    this.change(key, (chat) => ({
      lines: [...chat.lines, added].slice(-MAX_KEPT),
      unread: chat.unread + unread,
    }));
    return added;
  }

  private mark(key: string, line: Line, status: Status): void {
    this.change(key, (chat) => ({
      ...chat,
      lines: chat.lines.map((l) => (l.id === line.id ? { ...l, status } : l)),
    }));
  }

  private change(key: string, update: (chat: Chat) => Chat): void {
    const chats = this.chats();
    this.save({ ...chats, [key]: update(chats[key] ?? { lines: [], unread: 0 }) });
  }

  private save(chats: Record<string, Chat>): void {
    this.chats.set(chats);
    try {
      localStorage.setItem(HISTORY, JSON.stringify(chats));
    } catch {
      // Kept until the app closes, then.
    }
  }

  private load(): Record<string, Chat> {
    try {
      const stored: Record<string, Chat> = JSON.parse(localStorage.getItem(HISTORY) ?? '{}');
      if (!stored || typeof stored !== 'object') {
        return {};
      }
      // A message still sending when the app closed: it's unknown whether it went.
      for (const chat of Object.values(stored)) {
        chat.lines = chat.lines.map((line) =>
          line.status === 'sending' ? { ...line, status: 'failed' } : line,
        );
      }
      return stored;
    } catch {
      return {};
    }
  }
}
