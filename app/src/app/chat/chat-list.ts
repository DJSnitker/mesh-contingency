import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { RouterLink } from '@angular/router';

import { Icon } from '../icon';
import { NodeLink } from '../node/node-link';
import { COMPANION, Radio, RadioContact } from '../radio/radio';
import { channelKey, ChatHistory, dmKey, Line } from './chat-history';

/** A row in the list: a chat, where it opens, and its last message. */
interface Row {
  key: string;
  name: string;
  link: string[];
  last: Line | null;
  unread: number;
}

/**
 * The Chat screen: the radio's channels and its companion contacts, each
 * opening its chat, with the last message and how many are unread. The
 * node's contact opens the Node screen instead.
 */
@Component({
  selector: 'mc-chat-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, NgTemplateOutlet, RouterLink],
  styles: `
    .panel {
      display: grid;
      gap: 12px;
    }
    h2,
    p {
      margin: 0;
    }
    ul {
      display: grid;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    li + li {
      border-top: 1px solid var(--line);
    }
    a.chat {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 2px 12px;
      padding: 10px 0;
      color: inherit;
      text-decoration: none;
    }
    .name {
      font-weight: 600;
    }
    .last {
      grid-column: 1;
      overflow: hidden;
      color: var(--muted);
      font-size: 0.9rem;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .unread {
      grid-row: 1 / span 2;
      grid-column: 2;
      align-self: center;
      min-width: 1.6em;
      padding: 2px 6px;
      border-radius: 999px;
      background: var(--orange);
      color: var(--ink);
      font-size: 0.8rem;
      font-weight: 700;
      text-align: center;
    }
  `,
  template: `
    <h1><mc-icon name="chat" /> Chat</h1>

    @if (radio.state() !== 'connected') {
      <section class="panel">
        <p class="muted">
          Connect your radio first, on the <a routerLink="/node">Node</a> screen. Chats kept on the
          phone are below.
        </p>
      </section>
    }
    @if (problem(); as said) {
      <p class="said">{{ said }}</p>
    }

    <section class="panel channels">
      <h2>Channels</h2>
      @if (channelRows().length) {
        <ul>
          @for (row of channelRows(); track row.key) {
            <li><ng-container *ngTemplateOutlet="chat; context: { $implicit: row }" /></li>
          }
        </ul>
      } @else {
        <p class="muted">No channels yet.</p>
      }
    </section>

    <section class="panel direct">
      <h2>Direct messages</h2>
      @if (directRows().length) {
        <ul>
          @for (row of directRows(); track row.key) {
            <li><ng-container *ngTemplateOutlet="chat; context: { $implicit: row }" /></li>
          }
        </ul>
      } @else {
        <p class="muted">No contacts yet: they're added as the radio hears their adverts.</p>
      }
      @if (node(); as n) {
        <p class="muted">
          {{ n.name }} is the node: its commands are on the <a routerLink="/node">Node</a> screen.
        </p>
      }
    </section>

    <section class="panel">
      <div class="actions">
        <button
          class="btn btn-ghost btn-sm"
          type="button"
          [disabled]="radio.state() !== 'connected' || loading()"
          (click)="refresh()"
        >
          Refresh
        </button>
        <button
          class="btn btn-ghost btn-sm danger"
          type="button"
          [disabled]="!hasHistory()"
          (click)="clearAll()"
        >
          Clear every chat
        </button>
      </div>
      <p class="muted">Chats are kept on this phone only, until cleared.</p>
    </section>

    <ng-template #chat let-row>
      <a class="chat" [routerLink]="row.link">
        <span class="name">{{ row.name }}</span>
        <span class="last">{{ preview(row.last) }}</span>
        @if (row.unread) {
          <span class="unread" [attr.aria-label]="row.unread + ' unread'">{{ row.unread }}</span>
        }
      </a>
    </ng-template>
  `,
})
export class ChatList {
  protected readonly radio = inject(Radio);
  protected readonly history = inject(ChatHistory);
  private readonly link = inject(NodeLink);

  protected readonly contacts = signal<RadioContact[]>([]);
  protected readonly loading = signal(false);
  protected readonly problem = signal<string | null>(null);

  /** The node's contact, when the radio has it. */
  protected readonly node = computed(() =>
    this.contacts().find((c) => c.publicKey === this.link.node()?.publicKey),
  );

  protected readonly channelRows = computed<Row[]>(() => {
    const rows = this.history
      .channels()
      .map((channel) =>
        this.row(channelKey(channel.name), channel.name, ['/chat', 'channel', channel.name]),
      );
    // Kept chats on channels the radio hasn't listed (or isn't connected to say).
    const known = new Set(rows.map((r) => r.key));
    for (const key of Object.keys(this.history.chats())) {
      if (key.startsWith('ch:') && !known.has(key)) {
        rows.push(this.row(key, key.slice(3), ['/chat', 'channel', key.slice(3)]));
      }
    }
    return rows;
  });

  protected readonly directRows = computed<Row[]>(() => {
    const node = this.link.node()?.publicKey;
    const rows = this.contacts()
      .filter((c) => c.type === COMPANION && c.publicKey !== node)
      .map((c) => this.row(dmKey(c.publicKey), c.name, ['/chat', 'dm', c.publicKey]));
    // Chats with someone no longer in the contacts are kept, and listed by key.
    const known = new Set(rows.map((r) => r.key));
    for (const key of Object.keys(this.history.chats())) {
      if (key.startsWith('dm:') && !known.has(key)) {
        rows.push(this.row(key, key.slice(3), ['/chat', 'dm', key.slice(3)]));
      }
    }
    return rows;
  });

  protected readonly hasHistory = computed(() => Object.keys(this.history.chats()).length > 0);

  constructor() {
    // Read the contacts and channels once the radio is connected.
    effect(() => {
      if (this.radio.state() === 'connected') {
        void this.refresh();
      }
    });
  }

  protected async refresh(): Promise<void> {
    this.loading.set(true);
    this.problem.set(null);
    try {
      this.contacts.set(await this.radio.contacts());
      await this.history.loadChannels();
    } catch (error) {
      this.problem.set(`Couldn't read the radio's contacts and channels: ${String(error)}`);
    } finally {
      this.loading.set(false);
    }
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

  private row(key: string, name: string, link: string[]): Row {
    const chat = this.history.chats()[key];
    return { key, name, link, last: chat?.lines.at(-1) ?? null, unread: chat?.unread ?? 0 };
  }
}
