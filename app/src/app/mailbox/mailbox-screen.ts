import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { Icon } from '../icon';
import { NeedsNode } from '../node/needs-node';
import { MAX_COMMAND, NodeLink } from '../node/node-link';
import {
  parseClearInbox,
  parseInbox,
  parseMsg,
  parseSetPass,
  Inbox,
  SetPass,
} from '../node/replies';
import { StepLine } from '../node/step-line';

/** The bot's passphrase rules (sealing.py): 12 to 16 characters, no spaces. */
export const PASSPHRASE = { min: 12, max: 16 };

/** A name as msg takes it: one with spaces goes in ( ). */
export function recipient(name: string): string {
  const trimmed = name.trim();
  return /\s/.test(trimmed) ? `(${trimmed})` : trimmed;
}

/** Why a new passphrase can't be used, or null. */
export function passphraseProblem(passphrase: string, again: string): string | null {
  if (passphrase.length < PASSPHRASE.min || passphrase.length > PASSPHRASE.max) {
    return `A passphrase is ${PASSPHRASE.min} to ${PASSPHRASE.max} characters.`;
  }
  if (/\s/.test(passphrase)) {
    return "A passphrase can't contain spaces.";
  }
  return passphrase === again ? null : "The two don't match.";
}

/**
 * The Mailbox screen: the messages left for the user on the node (inbox,
 * clearinbox), leaving one for another user (msg), and sealing theirs with
 * a passphrase (setpass). Passphrases are typed each time and kept only
 * while the screen is open; opened messages aren't kept after it.
 */
@Component({
  selector: 'mc-mailbox',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, NeedsNode, StepLine],
  styles: `
    .panel {
      display: grid;
      gap: 12px;
    }
    h2,
    p {
      margin: 0;
    }
    .messages {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .messages li {
      padding: 10px 12px;
      border-left: 3px solid var(--sky);
      background: var(--ink-3);
      overflow-wrap: anywhere;
    }
    .messages .from {
      display: block;
      color: var(--muted);
      font-size: 0.8rem;
    }
  `,
  template: `
    <h1><mc-icon name="inbox" /> Mailbox</h1>

    <mc-needs-node />

    @if (link.exchange(); as ex) {
      @if (ex.step !== 'answered') {
        <mc-step-line [exchange]="ex" />
      }
    }

    <section class="panel inbox">
      <h2>Your messages</h2>
      <label class="field">
        Passphrase, if you set one
        <input
          type="password"
          name="inbox-passphrase"
          autocomplete="off"
          [maxLength]="maxPassphrase"
          [value]="passphrase()"
          (input)="passphrase.set(value($event))"
        />
      </label>
      <div class="actions">
        <button class="btn btn-sm" type="button" [disabled]="!link.ready()" (click)="open(1)">
          Open inbox
        </button>
      </div>

      @if (inbox(); as box) {
        @switch (box.outcome) {
          @case ('empty') {
            <p class="result">No messages.</p>
          }
          @case ('sealed') {
            <p class="result">
              {{ box.count }} sealed message(s), from {{ senders(box) }}. Type your passphrase above
              to open them.
            </p>
          }
          @case ('messages') {
            <ul class="messages">
              @for (message of box.messages; track $index) {
                <li>
                  <span class="from">{{ message.from }}, {{ message.ago }}</span>
                  {{ message.text }}
                </li>
              }
            </ul>
            @if (box.page && box.pages && box.page < box.pages) {
              <div class="actions">
                <span class="count">Page {{ box.page }} of {{ box.pages }}</span>
                <button
                  class="btn btn-ghost btn-sm"
                  type="button"
                  [disabled]="!link.ready()"
                  (click)="open(box.page + 1)"
                >
                  Next page
                </button>
              </div>
            }
          }
        }
      }
      @if (inboxSaid(); as said) {
        <p class="said">{{ said }}</p>
      }

      <div class="actions">
        <button
          class="btn btn-ghost btn-sm"
          type="button"
          [disabled]="!link.ready()"
          (click)="clear(false)"
        >
          Clear the ones read
        </button>
        <button
          class="btn btn-ghost btn-sm danger"
          type="button"
          [disabled]="!link.ready()"
          (click)="clear(true)"
        >
          Clear all
        </button>
      </div>
      @if (cleared(); as c) {
        <p class="cleared">{{ c }}</p>
      }
    </section>

    <section class="panel send">
      <h2>Leave a message</h2>
      <label class="field">
        For (a user's name)
        <input
          type="text"
          name="msg-to"
          autocomplete="off"
          [value]="to()"
          (input)="to.set(value($event))"
        />
      </label>
      <label class="field">
        Message
        <textarea name="msg-text" [value]="text()" (input)="text.set(value($event))"></textarea>
      </label>
      <div class="actions">
        <button
          class="btn btn-sm"
          type="button"
          [disabled]="!link.ready() || !to().trim() || !text().trim() || left() < 0"
          (click)="send()"
        >
          <mc-icon name="send" /> Leave it
        </button>
        <span class="count" [class.problem]="left() < 0">{{ left() }} characters left</span>
      </div>
      @if (sent(); as s) {
        <p class="sent">{{ s }}</p>
      }
    </section>

    <section class="panel passphrase">
      <h2><mc-icon name="lock" /> Passphrase</h2>
      <p class="muted">
        With a passphrase, new messages to you are sealed on the node: only your passphrase opens
        them. A forgotten one can't be recovered, and the messages sealed with it are lost. The app
        never keeps it.
      </p>
      <label class="field">
        New passphrase ({{ minPassphrase }} to {{ maxPassphrase }} characters, no spaces)
        <input
          type="password"
          name="new-passphrase"
          autocomplete="new-password"
          [maxLength]="maxPassphrase"
          [value]="newPassphrase()"
          (input)="newPassphrase.set(value($event))"
        />
      </label>
      <label class="field">
        Again
        <input
          type="password"
          name="new-passphrase-again"
          autocomplete="new-password"
          [maxLength]="maxPassphrase"
          [value]="again()"
          (input)="again.set(value($event))"
        />
      </label>
      @if (newPassphrase() && passphraseProblem(); as problem) {
        <p class="muted">{{ problem }}</p>
      }
      <div class="actions">
        <button
          class="btn btn-sm"
          type="button"
          [disabled]="!link.ready() || passphraseProblem()"
          (click)="setPass()"
        >
          Set it
        </button>
      </div>
      @if (setPassResult(); as result) {
        @switch (result.outcome) {
          @case ('set') {
            <p class="set">
              Passphrase set: new messages to you are sealed.
              @if (result.deleted) {
                {{ result.deleted }} message(s) sealed with the old one were deleted.
              }
            </p>
          }
          @case ('already') {
            <p class="set">That's already your passphrase.</p>
          }
          @case ('confirm') {
            <p class="set problem">
              You have {{ result.sealed }} sealed message(s) that only your old passphrase opens; a
              new one deletes them. Read them first (Open inbox with the old passphrase), or:
            </p>
            <div class="actions">
              <button
                class="btn btn-sm danger"
                type="button"
                [disabled]="!link.ready()"
                (click)="setPass()"
              >
                Set it, and delete them
              </button>
            </div>
          }
        }
      }
      @if (setPassSaid(); as said) {
        <p class="said">{{ said }}</p>
      }
    </section>
  `,
})
export class MailboxScreen {
  protected readonly link = inject(NodeLink);
  protected readonly minPassphrase = PASSPHRASE.min;
  protected readonly maxPassphrase = PASSPHRASE.max;

  protected readonly passphrase = signal('');
  protected readonly inbox = signal<Inbox | null>(null);
  /** The node's answer as it came, when the app couldn't read it or it said no. */
  protected readonly inboxSaid = signal<string | null>(null);
  protected readonly cleared = signal<string | null>(null);

  protected readonly to = signal('');
  protected readonly text = signal('');
  protected readonly sent = signal<string | null>(null);
  protected readonly left = computed(
    () => MAX_COMMAND - `msg ${recipient(this.to())} ${this.text().trim()}`.length,
  );

  protected readonly newPassphrase = signal('');
  protected readonly again = signal('');
  protected readonly passphraseProblem = computed(() =>
    passphraseProblem(this.newPassphrase(), this.again()),
  );
  protected readonly setPassResult = signal<SetPass | null>(null);
  protected readonly setPassSaid = signal<string | null>(null);

  protected value(event: Event): string {
    return (event.target as HTMLInputElement | HTMLTextAreaElement).value;
  }

  protected senders(box: Extract<Inbox, { outcome: 'sealed' }>): string {
    return box.senders.map((s) => `${s.from} ${s.ago}`).join(', ');
  }

  /** inbox, or inbox <passphrase>, at a page. */
  protected async open(page: number): Promise<void> {
    const words = ['inbox', this.passphrase().trim(), page > 1 ? String(page) : ''].filter(Boolean);
    this.inbox.set(null);
    this.inboxSaid.set(null);
    const exchange = await this.link.ask(words.join(' '), { label: 'inbox', keep: false });
    if (!exchange.text) {
      return;
    }
    const box = parseInbox(exchange.messages);
    this.inbox.set(box && box.outcome !== 'refused' ? box : null);
    this.inboxSaid.set(box && box.outcome !== 'refused' ? null : exchange.text);
  }

  protected async clear(all: boolean): Promise<void> {
    if (all && !confirm('Delete every message in your inbox, read or not?')) {
      return;
    }
    this.cleared.set(null);
    const exchange = await this.link.ask(all ? 'clearinbox all' : 'clearinbox', { one: true });
    if (!exchange.text) {
      return;
    }
    const result = parseClearInbox(exchange.text);
    this.cleared.set(
      result
        ? `Deleted ${result.deleted} message(s)` +
            (result.kept ? `; ${result.kept} new one(s) kept, not read yet.` : '.')
        : exchange.text,
    );
    if (result) {
      this.inbox.set(null);
    }
  }

  protected async send(): Promise<void> {
    const to = recipient(this.to());
    this.sent.set(null);
    const exchange = await this.link.ask(`msg ${to} ${this.text().trim()}`, {
      one: true,
      label: `msg to ${to}`,
    });
    if (!exchange.text) {
      return;
    }
    const result = parseMsg(exchange.text);
    if (result?.outcome === 'saved') {
      this.sent.set(`Left for ${result.to} (${result.waiting} in their inbox).`);
      this.text.set('');
    } else {
      this.sent.set(exchange.text);
    }
  }

  protected async setPass(): Promise<void> {
    this.setPassResult.set(null);
    this.setPassSaid.set(null);
    const exchange = await this.link.ask(`setpass ${this.newPassphrase()}`, {
      label: 'setpass',
      keep: false,
    });
    if (!exchange.text) {
      return;
    }
    const result = parseSetPass(exchange.messages);
    if (result && result.outcome !== 'refused') {
      this.setPassResult.set(result);
    } else {
      this.setPassSaid.set(exchange.text);
    }
    if (result?.outcome === 'set' || result?.outcome === 'already') {
      this.newPassphrase.set('');
      this.again.set('');
    }
  }
}
