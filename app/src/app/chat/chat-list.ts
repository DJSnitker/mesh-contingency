import { ChangeDetectionStrategy, Component, computed, effect, inject } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';

import { Radio } from '../radio/radio';
import { ChatHistory, Line } from './chat-history';
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
 * The Chat tab: the chats kept on the phone, newest first, each with its
 * last message and how many are unread. New ones start from Contacts.
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
    .loading .spinner {
      width: 1em;
      height: 1em;
      border-width: 2px;
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
      @if (history.loading() && unnamed()) {
        <p class="loading" role="status"><span class="spinner"></span> Reading contacts' names…</p>
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
      } @else {
        <p class="muted">
          No chats yet. Start one from <a routerLink="/chat/contacts">Contacts</a>: a person, or a
          channel.
        </p>
      }
    </section>

    @if (rows().length) {
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

  protected readonly rows = computed<Row[]>(() =>
    Object.entries(this.history.chats())
      .map(([key, chat]) => {
        const id = key.slice(3);
        const channel = key.startsWith('ch:');
        const contact = channel ? undefined : this.history.contact(id);
        return {
          key,
          name: channel ? id : (contact?.name ?? id),
          link: ['/chat', channel ? 'channel' : 'dm', contact?.publicKey ?? id],
          last: chat.lines.at(-1) ?? null,
          unread: chat.unread,
        };
      })
      .sort((a, b) => (b.last?.at ?? 0) - (a.last?.at ?? 0)),
  );

  /** A direct chat still shown by its key, for want of the contacts. */
  protected readonly unnamed = computed(() =>
    this.rows().some((row) => row.key.startsWith('dm:') && row.name === row.key.slice(3)),
  );

  constructor() {
    // The contacts' names, once the radio is connected.
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
