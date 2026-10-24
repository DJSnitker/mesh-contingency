import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { Icon } from '../icon';
import { NeedsNode } from '../node/needs-node';
import { MAX_COMMAND, NodeLink } from '../node/node-link';
import { parseOk, parseStatus, Status } from '../node/replies';
import { StepLine } from '../node/step-line';

/** One-press check-ins: what `ok` is sent with ("" for plain ok). */
export const QUICK = [
  { label: "I'm ok", status: '' },
  { label: 'Need help', status: 'need help' },
  { label: 'Need medical', status: 'need medical help' },
  { label: 'Sheltering in place', status: 'sheltering in place' },
  { label: 'Evacuating', status: 'evacuating' },
  { label: 'No power', status: 'ok, no power' },
];

/**
 * The Check-ins screen: tell the others how you are (ok [status], after
 * confirming), and look
 * up someone's last check-in, or your own (status [name]). Anyone may check
 * in; the roll call (checkins) is for admins, so it isn't here.
 */
@Component({
  selector: 'mc-checkins',
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
    .quick {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
    }
    .confirm {
      display: grid;
      gap: 10px;
      padding: 12px;
      border: 1px solid var(--orange);
      border-radius: 10px;
      background: rgb(255 95 31 / 8%);
    }
    .confirm p {
      margin: 0;
    }
    .quick button {
      justify-content: center;
    }
    .entries {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .entries li {
      padding: 10px 12px;
      border-left: 3px solid var(--green);
      background: var(--ink-3);
      overflow-wrap: anywhere;
    }
    .entries .who {
      display: block;
      color: var(--muted);
      font-size: 0.8rem;
    }
  `,
  template: `
    <h1><mc-icon name="check" /> Check-ins</h1>

    <mc-needs-node />

    @if (link.exchange(); as ex) {
      @if (ex.step !== 'answered') {
        <mc-step-line [exchange]="ex" />
      }
    }

    <section class="panel check-in">
      <h2>Check in</h2>
      <p class="muted">
        Tell the others how you are. Your latest check-in replaces the one before.
      </p>
      <div class="quick">
        @for (choice of quick; track choice.label) {
          <button
            class="btn btn-ghost"
            type="button"
            [disabled]="!link.ready()"
            (click)="ask(choice.status)"
          >
            {{ choice.label }}
          </button>
        }
      </div>
      <label class="field">
        Or in your own words
        <input
          type="text"
          name="status"
          autocomplete="off"
          [value]="status()"
          (input)="status.set(value($event))"
        />
      </label>
      <div class="actions">
        <button
          class="btn btn-sm"
          type="button"
          [disabled]="!link.ready() || !status().trim() || left() < 0"
          (click)="ask(status().trim())"
        >
          <mc-icon name="send" /> Check in
        </button>
        <span class="count" [class.problem]="left() < 0">{{ left() }} characters left</span>
      </div>
      @if (pending() !== null) {
        <div class="confirm" role="alertdialog" aria-labelledby="confirm-text">
          <p id="confirm-text">
            Send this check-in? <strong>“{{ pending() || 'ok' }}”</strong> replaces your last one,
            and anyone can look it up.
          </p>
          <div class="actions">
            <button class="btn btn-sm" type="button" [disabled]="!link.ready()" (click)="checkIn()">
              <mc-icon name="send" /> Send
            </button>
            <button class="btn btn-ghost btn-sm" type="button" (click)="pending.set(null)">
              Cancel
            </button>
          </div>
        </div>
      }
      @if (checkedIn(); as said) {
        <p class="checked-in">{{ said }}</p>
      }
    </section>

    <section class="panel look-up">
      <h2>Look someone up</h2>
      <label class="field">
        A name (or part of one); empty for your own
        <input
          type="text"
          name="who"
          autocomplete="off"
          [value]="who()"
          (input)="who.set(value($event))"
        />
      </label>
      <div class="actions">
        <button class="btn btn-sm" type="button" [disabled]="!link.ready()" (click)="lookUp()">
          Look up
        </button>
      </div>
      @if (found(); as result) {
        @if (result.outcome === 'found') {
          <ul class="entries">
            @for (entry of result.entries; track $index) {
              <li>
                <span class="who">
                  {{ entry.name }}{{ entry.keyPrefix ? ' (' + entry.keyPrefix + ')' : '' }},
                  {{ entry.ago }}
                </span>
                {{ entry.status }}
              </li>
            }
          </ul>
        } @else {
          <p class="none">
            {{ asked() ? 'No check-in from ' + asked() + '.' : "You haven't checked in yet." }}
          </p>
        }
      }
      @if (lookUpSaid(); as said) {
        <p class="said">{{ said }}</p>
      }
    </section>
  `,
})
export class CheckinsScreen {
  protected readonly link = inject(NodeLink);
  protected readonly quick = QUICK;

  protected readonly status = signal('');
  protected readonly left = computed(() => MAX_COMMAND - `ok ${this.status().trim()}`.length);
  protected readonly checkedIn = signal<string | null>(null);
  /** The check-in waiting to be confirmed ("" for plain ok), or null. */
  protected readonly pending = signal<string | null>(null);

  protected readonly who = signal('');
  /** Who the last look-up was for ("" for your own). */
  protected readonly asked = signal('');
  protected readonly found = signal<Status | null>(null);
  protected readonly lookUpSaid = signal<string | null>(null);

  protected value(event: Event): string {
    return (event.target as HTMLInputElement).value;
  }

  /** Ask before checking in: what's sent is seen by anyone who looks. */
  protected ask(status: string): void {
    this.checkedIn.set(null);
    this.pending.set(status);
  }

  /** Send the check-in waiting to be confirmed. */
  protected async checkIn(): Promise<void> {
    const status = this.pending();
    if (status === null) {
      return;
    }
    this.pending.set(null);
    const exchange = await this.link.ask(status ? `ok ${status}` : 'ok', { one: true });
    if (!exchange.text) {
      return;
    }
    const result = parseOk(exchange.text);
    if (result?.outcome === 'saved') {
      this.checkedIn.set(`Checked in as ${result.name}: ${status || 'ok'}.`);
      this.status.set('');
    } else {
      this.checkedIn.set(exchange.text);
    }
  }

  protected async lookUp(): Promise<void> {
    const who = this.who().trim();
    this.found.set(null);
    this.lookUpSaid.set(null);
    this.asked.set(who);
    const exchange = await this.link.ask(who ? `status ${who}` : 'status', { one: true });
    if (!exchange.text) {
      return;
    }
    const result = parseStatus(exchange.text);
    this.found.set(result);
    this.lookUpSaid.set(result ? null : exchange.text);
  }
}
