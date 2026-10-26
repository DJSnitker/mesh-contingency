import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { catchError, EMPTY, interval, startWith, switchMap, tap } from 'rxjs';

import { Api, DirectMessage } from './api';
import { Icon } from './icon';
import { ago, when } from './time';
import { Unread } from './unread';

/** How often a chat is read again (ms): often, so delivered and replies show soon. */
export const DM_REFRESH_MS = 5_000;
/** The longest direct message (the bot's MAX_REPLY_LEN). */
export const DM_LIMIT = 133;

/** What each status says under the console's message. */
const SAID: Record<NonNullable<DirectMessage['status']>, string> = {
  sending: 'Sending…',
  delivered: 'Delivered',
  'not delivered': 'Not delivered',
};

/**
 * The console's chat with one contact (route chat/dm/:key), as the phone
 * app's: the console's messages on the right, each sending, delivered or not,
 * and the contact's replies; oldest first, read again every DM_REFRESH_MS
 * and marked read (unread.ts) as it is. A box to send more as the node.
 */
@Component({
  selector: 'mc-dm',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, RouterLink],
  styleUrls: ['./compose.scss', './channel.scss'],
  template: `
    <header class="title">
      <div class="head">
        <a class="btn btn-ghost btn-sm" routerLink="/chat" aria-label="All chats">‹</a>
        <div>
          <h1>{{ name() ?? contact().slice(0, 12) }}</h1>
          <p class="muted">
            <code [title]="contact()">{{ contact().slice(0, 12) }}</code>
          </p>
        </div>
      </div>
    </header>

    <section class="panel thread" aria-label="Messages">
      @if (problem()) {
        <p class="problem" role="alert"><mc-icon name="alert" /> {{ problem() }}</p>
      }
      @if (read()) {
        @if (lines(); as list) {
          @if (list.length) {
            <ul class="lines">
              @for (line of list; track line.id) {
                <li [class.mine]="line.own">
                  <span class="text">{{ line.text }}</span>
                  <span class="meta" [class.failed]="line.status === 'not delivered'">
                    <time [title]="when(line.time)">{{ ago(line.time, now()) }}</time>
                    @if (line.status; as status) {
                      ·
                      @if (status === 'sending') {
                        <span class="spinner small"></span>
                      }
                      {{ said[status] }}
                    } @else if (route(line.hops, line.snr); as r) {
                      · {{ r }}
                    }
                  </span>
                </li>
              }
            </ul>
          } @else {
            <p class="muted">No messages yet: say hello below.</p>
          }
          <p class="muted note">
            The console's messages and the replies to them, the last {{ keep() }} in the bot's
            memory only. A reply comes here if it isn't a command, within a day of the console's
            last message.
          </p>
        } @else {
          <p class="muted">The bot isn't keeping the console's chats.</p>
        }
      } @else if (!problem()) {
        <p class="loading" role="status"><span class="spinner"></span> Reading the messages…</p>
      }
    </section>

    <section class="panel" aria-labelledby="send-title">
      <h2 id="send-title"><mc-icon name="send" /> Message {{ name() ?? 'them' }}</h2>
      <p class="muted">A direct message from the node, retried until the radio has an ack.</p>
      <label class="field">
        <span class="sr-only">Message to send</span>
        <textarea
          rows="3"
          placeholder="What to say"
          [value]="text()"
          (input)="text.set(value($event))"
          (keydown.control.enter)="send()"
        ></textarea>
      </label>
      <div class="row">
        <span class="count" [class.over]="tooLong()">
          {{ text().trim().length }} / {{ limit }} characters
        </span>
        <button class="btn" type="button" [disabled]="!canSend()" (click)="send()">
          @if (sending()) {
            <span class="spinner small"></span>
          } @else {
            <mc-icon name="send" />
          }
          Send
        </button>
      </div>
      @if (tooLong()) {
        <p class="hint">A direct message is one message: shorten it, or send it in parts.</p>
      }
      @if (refused(); as said) {
        <p class="problem" role="status"><mc-icon name="alert" /> {{ said }}</p>
      }
    </section>
  `,
  styles: `
    .meta.failed {
      color: var(--orange);
    }
  `,
})
export class DirectThread {
  private readonly api = inject(Api);
  private readonly unread = inject(Unread);
  protected readonly said = SAID;
  protected readonly limit = DM_LIMIT;
  protected readonly ago = ago;
  protected readonly when = when;

  /** The contact's key, from the route. */
  readonly key = input<string>();
  protected readonly contact = computed(() => (this.key() ?? '').toLowerCase());

  protected readonly name = signal<string | null>(null);
  /** Newest last; null until read, or if the bot keeps none. */
  protected readonly lines = signal<DirectMessage[] | null>(null);
  protected readonly keep = signal<number | null>(null);
  protected readonly read = signal(false);
  protected readonly problem = signal<string | null>(null);
  protected readonly now = signal(Date.now() / 1000);

  protected readonly text = signal('');
  protected readonly sending = signal(false);
  /** Why the last message wasn't taken, if it wasn't. */
  protected readonly refused = signal<string | null>(null);
  protected readonly tooLong = computed(() => this.text().trim().length > DM_LIMIT);
  protected readonly canSend = computed(
    () => !!this.text().trim() && !this.tooLong() && !this.sending(),
  );

  constructor() {
    toObservable(this.contact)
      .pipe(
        switchMap((key) => {
          this.lines.set(null);
          this.read.set(false);
          this.refused.set(null);
          return interval(DM_REFRESH_MS).pipe(
            startWith(0),
            switchMap(() => this.messages(key)),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe();
  }

  private messages(key: string) {
    return this.api.contactMessages(key).pipe(
      tap((found) => {
        this.now.set(Date.now() / 1000);
        this.name.set(found.name);
        this.keep.set(found.keep);
        this.lines.set(found.messages ? [...found.messages].reverse() : null);
        this.read.set(true);
        this.problem.set(null);
        this.unread.readDm(key, found.heard);
      }),
      catchError(() => {
        this.problem.set("can't read the chat");
        return EMPTY;
      }),
    );
  }

  /** How a reply came: "direct", "2 hops", and its signal. */
  protected route(hops: number | null, snr: number | null): string {
    const parts =
      hops === null ? [] : [hops === 0 ? 'direct' : `${hops} hop${hops === 1 ? '' : 's'}`];
    if (snr !== null) {
      parts.push(`SNR ${snr} dB`);
    }
    return parts.join(' · ');
  }

  /** Send the box's text; it's emptied once the bot took it, and shows as sending. */
  protected send(): void {
    if (!this.canSend()) {
      return;
    }
    const key = this.contact();
    this.sending.set(true);
    this.refused.set(null);
    this.api.messageContact(key, this.text().trim()).subscribe({
      next: ({ message }) => {
        this.sending.set(false);
        this.text.set('');
        this.lines.update((lines) => [...(lines ?? []), message]);
        this.unread.refreshConversations();
      },
      error: (error: HttpErrorResponse) => {
        this.sending.set(false);
        const said = typeof error.error === 'object' && error.error?.error;
        this.refused.set(
          said || (error.status === 0 ? "can't reach the bot" : `the bot said ${error.status}`),
        );
      },
    });
  }

  protected value(event: Event): string {
    return (event.target as HTMLTextAreaElement).value;
  }
}
