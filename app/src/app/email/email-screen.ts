import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { RouterLink } from '@angular/router';

import { Icon } from '../icon';
import { NeedsNode } from '../node/needs-node';
import { MAX_COMMAND, NodeLink } from '../node/node-link';
import { parseAddGroup, parseClearGroup, parseEmail, parseSetQm } from '../node/replies';
import { StepLine } from '../node/step-line';

/** Who an email goes to: the command that sends it. */
export type To = 'qm' | 'emailall' | 'email';

export const TO: { value: To; label: string }[] = [
  { value: 'qm', label: 'My preset contact' },
  { value: 'emailall', label: 'My group' },
  { value: 'email', label: 'An address' },
];

/** The address check the bot makes (mail.py's ADDRESS_RE), so a typo is caught before it's sent. */
export const ADDRESS =
  /^[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/;

/**
 * The Email screen: the node emails the user's message, when it has the
 * internet, to their preset contact (qm), their group (emailall) or any
 * address (email), after they confirm; and their addresses for qm and the
 * group (setqm, addgroup, cleargroup).
 */
@Component({
  selector: 'mc-email',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, NeedsNode, RouterLink, StepLine],
  styles: `
    .head {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .head h1 {
      margin: 0;
    }
    .panel {
      display: grid;
      gap: 12px;
    }
    h2,
    p {
      margin: 0;
    }
    .to {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .to button[aria-pressed='true'] {
      border-color: var(--orange);
      color: var(--orange);
    }
    .confirm {
      display: grid;
      gap: 10px;
      padding: 12px;
      border: 1px solid var(--orange);
      border-radius: 10px;
      background: rgb(255 95 31 / 8%);
    }
    dl {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 4px 16px;
      margin: 0;
      overflow-wrap: anywhere;
    }
    dt {
      color: var(--muted);
    }
    dd {
      margin: 0;
    }
  `,
  template: `
    <div class="head">
      <a class="btn btn-ghost btn-sm" routerLink="/mailbox" aria-label="Back to Mailbox">‹</a>
      <h1><mc-icon name="mail" /> Email</h1>
    </div>

    <mc-needs-node />
    @if (link.whoami()?.user === false) {
      <section class="panel">
        <p class="muted">Email is for the node's users. Join on the Node screen first.</p>
      </section>
    }

    @if (link.exchange(); as ex) {
      @if (ex.step !== 'answered') {
        <mc-step-line [exchange]="ex" />
      }
    }

    <section class="panel send">
      <h2>Send an email</h2>
      <p class="muted">The node emails it when it has the internet. Replies to it go nowhere.</p>
      <div class="to" role="group" aria-label="To">
        @for (choice of choices; track choice.value) {
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            [attr.aria-pressed]="to() === choice.value"
            (click)="to.set(choice.value)"
          >
            {{ choice.label }}
          </button>
        }
      </div>
      @if (to() === 'email') {
        <label class="field">
          Address
          <input
            type="email"
            name="address"
            autocomplete="email"
            [value]="address()"
            (input)="address.set(value($event))"
          />
        </label>
        @if (address() && !addressOk()) {
          <p class="muted">That isn't an email address the node can send to.</p>
        }
      }
      <label class="field">
        Message
        <textarea name="email-text" [value]="text()" (input)="text.set(value($event))"></textarea>
      </label>
      <div class="actions">
        <button
          class="btn btn-sm"
          type="button"
          [disabled]="!canSend()"
          (click)="pending.set(true)"
        >
          <mc-icon name="send" /> Send
        </button>
        <span class="count" [class.problem]="left() < 0">{{ left() }} characters left</span>
      </div>
      @if (pending()) {
        <div class="confirm" role="alertdialog" aria-labelledby="email-confirm">
          <p id="email-confirm">
            Email this to {{ toWords() }}? It can't be taken back once it's sent.
          </p>
          <div class="actions">
            <button class="btn btn-sm" type="button" [disabled]="!link.ready()" (click)="send()">
              <mc-icon name="send" /> Send it
            </button>
            <button class="btn btn-ghost btn-sm" type="button" (click)="pending.set(false)">
              Cancel
            </button>
          </div>
        </div>
      }
      @if (sent(); as said) {
        <p class="sent" [class.problem]="!sentOk()">{{ said }}</p>
      }
    </section>

    <section class="panel addresses">
      <h2>Your addresses</h2>
      <div class="actions">
        <button
          class="btn btn-ghost btn-sm"
          type="button"
          [disabled]="!link.ready()"
          (click)="show()"
        >
          Show them
        </button>
      </div>
      @if (qm() !== null || group() !== null) {
        <dl>
          <dt>Preset contact</dt>
          <dd class="qm">{{ qm()?.length ? qm()!.join(', ') : 'none set' }}</dd>
          <dt>Group</dt>
          <dd class="group">{{ group()?.length ? group()!.join(', ') : 'no addresses' }}</dd>
        </dl>
      }
      <label class="field">
        Set your preset contact
        <input
          type="email"
          name="qm-address"
          autocomplete="email"
          [value]="newQm()"
          (input)="newQm.set(value($event))"
        />
      </label>
      <div class="actions">
        <button
          class="btn btn-sm"
          type="button"
          [disabled]="!link.ready() || !isAddress(newQm())"
          (click)="setQm()"
        >
          Set it
        </button>
      </div>
      <label class="field">
        Add to your group
        <input
          type="email"
          name="group-address"
          autocomplete="email"
          [value]="newGroup()"
          (input)="newGroup.set(value($event))"
        />
      </label>
      <div class="actions">
        <button
          class="btn btn-sm"
          type="button"
          [disabled]="!link.ready() || !isAddress(newGroup())"
          (click)="addGroup()"
        >
          Add it
        </button>
        <button
          class="btn btn-ghost btn-sm danger"
          type="button"
          [disabled]="!link.ready()"
          (click)="clearGroup()"
        >
          Clear the group
        </button>
      </div>
      @if (changed(); as said) {
        <p class="changed">{{ said }}</p>
      }
    </section>
  `,
})
export class EmailScreen {
  protected readonly link = inject(NodeLink);
  protected readonly choices = TO;

  protected readonly to = signal<To>('qm');
  protected readonly address = signal('');
  protected readonly text = signal('');
  protected readonly pending = signal(false);
  protected readonly sent = signal<string | null>(null);
  protected readonly sentOk = signal(true);
  protected readonly addressOk = computed(() => this.isAddress(this.address()));
  protected readonly command = computed(() => {
    const to = this.to();
    const words =
      to === 'email' ? [to, this.address().trim(), this.text().trim()] : [to, this.text().trim()];
    return words.join(' ');
  });
  protected readonly left = computed(() => MAX_COMMAND - this.command().length);
  protected readonly canSend = computed(
    () =>
      this.link.ready() &&
      !!this.text().trim() &&
      this.left() >= 0 &&
      (this.to() !== 'email' || this.addressOk()),
  );
  protected readonly toWords = computed(() => {
    switch (this.to()) {
      case 'qm':
        return 'your preset contact';
      case 'emailall':
        return 'your group';
      default:
        return this.address().trim();
    }
  });

  protected readonly qm = signal<string[] | null>(null);
  protected readonly group = signal<string[] | null>(null);
  protected readonly newQm = signal('');
  protected readonly newGroup = signal('');
  protected readonly changed = signal<string | null>(null);

  protected value(event: Event): string {
    return (event.target as HTMLInputElement | HTMLTextAreaElement).value;
  }

  protected isAddress(text: string): boolean {
    return ADDRESS.test(text.trim());
  }

  protected async send(): Promise<void> {
    this.pending.set(false);
    this.sent.set(null);
    const command = this.command();
    const name = this.to();
    const exchange = await this.link.ask(command, { one: true, label: name });
    if (!exchange.text) {
      return;
    }
    const result = parseEmail(name, exchange.text);
    this.sentOk.set(result?.outcome === 'sent');
    if (result?.outcome === 'sent') {
      this.sent.set(`Sent to ${this.toWords()}.`);
      this.text.set('');
    } else if (result?.outcome === 'not sent') {
      this.sent.set(`Not sent: ${result.why}.`);
    } else {
      this.sent.set(exchange.text);
    }
  }

  /** Ask the node for both: the preset contact (setqm) and the group (addgroup). */
  protected async show(): Promise<void> {
    this.changed.set(null);
    const qm = await this.link.ask('setqm', { one: true });
    const shownQm = qm.text ? parseSetQm(qm.text) : null;
    if (shownQm?.outcome === 'shown') {
      this.qm.set(shownQm.addresses);
    } else if (qm.text) {
      this.changed.set(qm.text);
    }
    const group = await this.link.ask('addgroup', { one: true });
    const shownGroup = group.text ? parseAddGroup(group.text) : null;
    if (shownGroup?.outcome === 'shown') {
      this.group.set(shownGroup.addresses);
    } else if (group.text) {
      this.changed.set(group.text);
    }
  }

  protected async setQm(): Promise<void> {
    this.changed.set(null);
    const exchange = await this.link.ask(`setqm ${this.newQm().trim()}`, { one: true });
    if (!exchange.text) {
      return;
    }
    const result = parseSetQm(exchange.text);
    if (result?.outcome === 'set') {
      this.qm.set(result.addresses);
      this.changed.set(`Your preset contact is now ${result.addresses[0]}.`);
      this.newQm.set('');
    } else {
      this.changed.set(exchange.text);
    }
  }

  protected async addGroup(): Promise<void> {
    this.changed.set(null);
    const exchange = await this.link.ask(`addgroup ${this.newGroup().trim()}`, { one: true });
    if (!exchange.text) {
      return;
    }
    const result = parseAddGroup(exchange.text);
    if (result?.outcome === 'added') {
      this.group.update((group) => (group ? [...group, result.address] : null));
      this.changed.set(`Added ${result.address} (${result.count} in your group).`);
      this.newGroup.set('');
    } else {
      this.changed.set(exchange.text);
    }
  }

  protected async clearGroup(): Promise<void> {
    if (!confirm('Remove every address from your group?')) {
      return;
    }
    this.changed.set(null);
    const exchange = await this.link.ask('cleargroup', { one: true });
    if (!exchange.text) {
      return;
    }
    const result = parseClearGroup(exchange.text);
    if (result) {
      this.group.set([]);
      this.changed.set(`Removed ${result.removed} address(es) from your group.`);
    } else {
      this.changed.set(exchange.text);
    }
  }
}
