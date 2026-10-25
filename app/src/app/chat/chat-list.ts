import { ChangeDetectionStrategy, Component, computed, effect, inject, input } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';

import { Radio } from '../radio/radio';
import { channelKey, ChatHistory, Line } from './chat-history';
import { ChatTabs } from './chat-tabs';

/** A chat in the list: where it opens, and its newest message. */
interface Row {
  key: string;
  name: string;
  link: string[];
  last: Line | null;
  unread: number;
}

/** A message's time: the time today, else the day. */
export function when(at: number, now = Date.now()): 'h:mm a' | 'MMM d' {
  return new Date(at).toDateString() === new Date(now).toDateString() ? 'h:mm a' : 'MMM d';
}

/**
 * The Chat tab (`kind` "dm"): the chats with people kept on the phone,
 * newest first, each with its last message and how many are unread; new
 * ones start from Contacts. The Channels tab (`kind` "ch"): the radio's
 * channels, and any others with chats kept, in the same way.
 */
@Component({
  selector: 'mc-chat-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ChatTabs, DatePipe, RouterLink],
  styles: `
    :host {
      display: grid;
      gap: 16px;
    }
    .panel {
      display: grid;
      gap: 12px;
    }
    p {
      margin: 0;
    }
    .loading {
      font-size: 0.9rem;
    }
  `,
  template: `
    <mc-chat-tabs />

    @if (radio.state() !== 'connected') {
      <p class="muted">
        Connect your radio on the <a routerLink="/node">Node</a> screen to send. Chats kept on the
        phone are below.
      </p>
    }

    <section class="panel">
      @if (loading()) {
        <p class="loading" role="status">
          <span class="spinner small"></span>
          {{
            kind() === 'ch' ? 'Reading the channels from your radio…' : "Reading contacts' names…"
          }}
        </p>
      }
      @if (rows().length) {
        <ul class="rows">
          @for (row of rows(); track row.key) {
            <li>
              <a [routerLink]="row.link">
                <span class="name">{{ row.name }}</span>
                @if (row.last; as last) {
                  <span class="side">{{ last.at | date: when(last.at) }}</span>
                }
                <span class="sub">{{ preview(row.last) }}</span>
                @if (row.unread) {
                  <span class="unread" [attr.aria-label]="row.unread + ' unread'">{{
                    row.unread
                  }}</span>
                }
              </a>
            </li>
          }
        </ul>
      } @else if (kind() === 'ch') {
        @if (!loading()) {
          <p class="muted">No channels on the radio.</p>
        }
      } @else {
        <p class="muted">
          No chats yet. Start one from <a routerLink="/chat/contacts">Contacts</a>.
        </p>
      }
    </section>

    @if (kept()) {
      <section class="panel">
        <div class="actions">
          <button class="btn btn-ghost btn-sm danger" type="button" (click)="clearAll()">
            Clear every chat
          </button>
        </div>
        <p class="muted">Chats are kept on this phone only, until cleared.</p>
      </section>
    }
  `,
})
export class ChatList {
  protected readonly radio = inject(Radio);
  protected readonly history = inject(ChatHistory);
  protected readonly when = when;

  /** Which chats: with people ("dm"), or on channels ("ch"). From the route's data. */
  readonly data = input<'dm' | 'ch' | undefined>(undefined, { alias: 'kind' });
  protected readonly kind = computed(() => this.data() ?? 'dm');

  protected readonly rows = computed<Row[]>(() => {
    const chats = this.history.chats();
    const row = (key: string, name: string, link: string[]): Row => ({
      key,
      name,
      link,
      last: chats[key]?.lines.at(-1) ?? null,
      unread: chats[key]?.unread ?? 0,
    });
    const prefix = `${this.kind()}:`;
    const rows: Row[] = [];
    if (this.kind() === 'ch') {
      // Every channel on the radio, chatted on or not.
      for (const channel of this.history.channels()) {
        rows.push(row(channelKey(channel.name), channel.name, ['/chat', 'channel', channel.name]));
      }
    }
    const listed = new Set(rows.map((r) => r.key));
    for (const key of Object.keys(chats)) {
      if (!key.startsWith(prefix) || listed.has(key)) {
        continue;
      }
      const id = key.slice(3);
      if (this.kind() === 'ch') {
        rows.push(row(key, id, ['/chat', 'channel', id]));
      } else {
        const contact = this.history.contact(id);
        rows.push(row(key, contact?.name ?? id, ['/chat', 'dm', contact?.publicKey ?? id]));
      }
    }
    // Chatted on, newest first; then the rest as the radio lists them.
    return rows.sort((a, b) => (b.last?.at ?? 0) - (a.last?.at ?? 0));
  });

  /** Waiting on the radio: for the channels, or for the names of people shown by key. */
  protected readonly loading = computed(() =>
    this.kind() === 'ch'
      ? this.history.loadingChannels()
      : this.history.loadingContacts() && this.rows().some((row) => row.name === row.key.slice(3)),
  );

  protected readonly kept = computed(() => Object.keys(this.history.chats()).length > 0);

  constructor() {
    effect(() => {
      if (this.radio.state() === 'connected') {
        this.history.refresh().catch(() => undefined);
      }
    });
  }

  protected preview(line: Line | null): string {
    if (!line) {
      return 'No messages';
    }
    return `${line.mine ? 'You: ' : line.from ? `${line.from}: ` : ''}${line.text}`;
  }

  protected clearAll(): void {
    if (confirm('Clear every chat kept on this phone?')) {
      this.history.clearAll();
    }
  }
}
