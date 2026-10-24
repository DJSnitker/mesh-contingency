import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  effect,
  ElementRef,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';

import { Icon } from '../icon';
import { Radio, RadioContact } from '../radio/radio';
import { channelKey, channelLimit, ChatHistory, dmKey, MAX_TEXT, Status } from './chat-history';

/** What each status says under the user's message. */
const SAID: Record<Status, string> = {
  sending: 'Sending…',
  delivered: 'Delivered',
  'not delivered': 'Not delivered',
  sent: 'Sent',
  failed: "Couldn't send",
};

/**
 * One chat: a direct message thread with a contact (route dm/:key, the full
 * key) or a channel (channel/:name). Its messages, and a box to send more.
 */
@Component({
  selector: 'mc-chat',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, Icon, RouterLink],
  styles: `
    :host {
      display: grid;
      gap: 12px;
    }
    .head {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .head h1 {
      flex: 1;
      margin: 0;
      overflow-wrap: anywhere;
    }
    .lines {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .lines li {
      display: grid;
      gap: 2px;
      max-width: 85%;
      padding: 8px 12px;
      border-radius: 12px;
      background: var(--ink-3);
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }
    .lines li.mine {
      justify-self: end;
      background: rgb(255 95 31 / 16%);
    }
    .from {
      color: var(--sky);
      font-size: 0.85rem;
      font-weight: 600;
    }
    .meta {
      color: var(--muted);
      font-size: 0.75rem;
    }
    .meta.problem {
      color: var(--orange);
    }
    .compose {
      display: grid;
      gap: 8px;
    }
    p {
      margin: 0;
    }
  `,
  template: `
    <div class="head">
      <a class="btn btn-ghost btn-sm" routerLink="/chat" aria-label="All chats">‹</a>
      <h1>{{ title() }}</h1>
      <button
        class="btn btn-ghost btn-sm danger"
        type="button"
        [disabled]="!lines().length"
        (click)="clear()"
      >
        Clear
      </button>
    </div>

    @if (lines().length) {
      <ul class="lines">
        @for (line of lines(); track line.id) {
          <li [class.mine]="line.mine">
            @if (line.from) {
              <span class="from">{{ line.from }}</span>
            }
            <span class="text">{{ line.text }}</span>
            <span
              class="meta"
              [class.problem]="line.status === 'not delivered' || line.status === 'failed'"
            >
              {{ line.at | date: 'MMM d, h:mm a' }}
              @if (line.status) {
                · {{ said[line.status] }}
              }
            </span>
          </li>
        }
      </ul>
    } @else {
      <p class="muted">No messages yet.</p>
    }

    @if (channelName() && !channel()) {
      <p class="muted">The radio has no channel {{ channelName() }} now.</p>
    }
    @if (radio.state() !== 'connected') {
      <p class="muted">Connect your radio on the <a routerLink="/node">Node</a> screen to send.</p>
    }

    <div class="compose" #compose>
      <label class="field">
        Message
        <textarea name="chat-text" [value]="text()" (input)="text.set(value($event))"></textarea>
      </label>
      <div class="actions">
        <button class="btn btn-sm" type="button" [disabled]="!canSend()" (click)="send()">
          <mc-icon name="send" /> Send
        </button>
        <span class="count" [class.problem]="left() < 0">{{ left() }} characters left</span>
      </div>
    </div>
  `,
})
export class ChatScreen {
  protected readonly radio = inject(Radio);
  private readonly history = inject(ChatHistory);
  protected readonly said = SAID;

  /** The contact's full key, for a direct chat (from the route). */
  readonly key = input<string>();
  /** The channel's name, for a channel (from the route). */
  readonly name = input<string>();

  protected readonly text = signal('');
  protected readonly contact = signal<RadioContact | null>(null);
  private readonly compose = viewChild<ElementRef<HTMLElement>>('compose');

  protected readonly channelName = computed(() => this.name() ?? null);
  protected readonly channel = computed(
    () => this.history.channels().find((c) => c.name === this.name()) ?? null,
  );
  protected readonly chatKey = computed(() => {
    const name = this.name();
    return name ? channelKey(name) : dmKey(this.key() ?? '');
  });
  protected readonly title = computed(
    () => this.name() ?? this.contact()?.name ?? this.key()?.slice(0, 12) ?? '',
  );
  protected readonly lines = computed(() => this.history.lines(this.chatKey()));
  protected readonly limit = computed(() =>
    this.name() ? channelLimit(this.radio.name()) : MAX_TEXT,
  );
  protected readonly left = computed(() => this.limit() - this.text().trim().length);
  protected readonly canSend = computed(
    () =>
      this.radio.state() === 'connected' &&
      !!this.text().trim() &&
      this.left() >= 0 &&
      // A direct message needs the full key; a channel, its slot.
      (this.name() ? !!this.channel() : (this.key()?.length ?? 0) === 64),
  );

  constructor() {
    // The open chat's messages arrive read.
    effect(() => {
      const key = this.chatKey();
      this.history.open.set(key);
      this.history.read(key);
    });
    inject(DestroyRef).onDestroy(() => this.history.open.set(null));
    // Its name, and the channel's slot, from the radio.
    effect(() => {
      if (this.radio.state() === 'connected') {
        void this.lookUp();
      }
    });
    // Keep the newest message in view.
    effect(() => {
      this.lines();
      queueMicrotask(() => this.compose()?.nativeElement.scrollIntoView?.({ block: 'end' }));
    });
  }

  protected value(event: Event): string {
    return (event.target as HTMLTextAreaElement).value;
  }

  protected async send(): Promise<void> {
    const text = this.text().trim();
    this.text.set('');
    const channel = this.channel();
    if (this.name() && channel) {
      await this.history.sendToChannel(channel, text);
    } else if (this.key()) {
      await this.history.sendDirect(this.key()!, text);
    }
  }

  protected clear(): void {
    if (confirm(`Clear the chat with ${this.title()} from this phone?`)) {
      this.history.clear(this.chatKey());
    }
  }

  private async lookUp(): Promise<void> {
    try {
      if (this.name()) {
        if (!this.channel()) {
          await this.history.loadChannels();
        }
      } else {
        this.contact.set(
          (await this.radio.contacts()).find((c) => c.publicKey === this.key()) ?? null,
        );
      }
    } catch {
      // The title stays the key, and sending waits for the channel.
    }
  }
}
