import { ChangeDetectionStrategy, Component, effect, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';

import { Icon } from '../icon';
import { COMPANION, Radio, RadioContact } from '../radio/radio';
import { FIRST_REPLY_MS, NodeLink } from './node-link';

/** The Node screen: the user's radio, the node, and whether they're a user. */
@Component({
  selector: 'mc-node',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, Icon, RouterLink],
  styles: `
    .panel {
      display: grid;
      gap: 12px;
    }
    h2,
    p {
      margin: 0;
    }
    dl {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 4px 16px;
      margin: 0;
    }
    dt {
      color: var(--muted);
    }
    dd {
      margin: 0;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .contacts {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .contacts button {
      width: 100%;
      justify-content: flex-start;
    }
    .said {
      margin: 0;
      padding: 10px 12px;
      border-left: 3px solid var(--sky);
      background: var(--ink-3);
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .notices {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .notices time {
      display: block;
      color: var(--muted);
      font-size: 0.8rem;
    }
  `,
  template: `
    <h1><mc-icon name="radio" /> Node</h1>

    <section class="panel radio">
      <h2>Your radio</h2>
      @switch (radio.state()) {
        @case ('connected') {
          <dl>
            <dt>Name</dt>
            <dd class="radio-name">{{ radio.name() }}</dd>
            @if (radio.batteryMilliVolts(); as mv) {
              <dt>Battery</dt>
              <dd class="battery">{{ (mv / 1000).toFixed(2) }} V</dd>
            }
            @if (radio.firmware(); as firmware) {
              <dt>Firmware</dt>
              <dd>{{ firmware }}</dd>
            }
          </dl>
          <div class="actions">
            <button class="btn btn-ghost btn-sm" type="button" (click)="radio.disconnect()">
              Disconnect
            </button>
            <button class="btn btn-ghost btn-sm danger" type="button" (click)="radio.forget()">
              Forget it
            </button>
          </div>
        }
        @case ('connecting') {
          <p>Connecting to {{ radio.name() ?? 'your radio' }}…</p>
        }
        @default {
          @if (radio.hasRemembered()) {
            <p>
              <span class="radio-name">{{ radio.name() }}</span>
              <span class="muted"> isn't connected.</span>
            </p>
            <div class="actions">
              <button class="btn btn-sm" type="button" (click)="radio.reconnect()">
                Reconnect
              </button>
              <button class="btn btn-ghost btn-sm" type="button" (click)="radio.pick()">
                Pick another
              </button>
            </div>
          } @else {
            <p class="muted">
              Turn on your MeshCore radio near the phone, then pick it from the list. The phone asks
              for its Bluetooth PIN the first time.
            </p>
            <div class="actions">
              <button class="btn" type="button" (click)="radio.pick()">
                <mc-icon name="radio" /> Find my radio
              </button>
            </div>
          }
        }
      }
      @if (radio.problem(); as problem) {
        <p class="problem" role="alert"><mc-icon name="alert" /> {{ problem }}</p>
      }
    </section>

    <section class="panel node">
      @if (link.node(); as node) {
        <h2>{{ node.name }}</h2>
        @if (link.whoami(); as who) {
          @if (who.user) {
            <p class="membership">
              You're a user{{ who.admin ? ' and an admin' : '' }}.
              {{
                who.messages
                  ? who.messages + ' message(s), ' + who.unread + ' unread'
                  : 'No messages'
              }}; {{ who.passphrase ? 'passphrase set' : 'no passphrase' }}.
            </p>
          } @else {
            <p class="membership">
              You're not a user yet. Join asks the node's admins to make you one.
            </p>
          }
        } @else if (link.unanswered()) {
          <p class="membership">
            No answer. The node answers someone who isn't a user only once every 5 minutes, so you
            may not be one yet; or it's out of reach.
          </p>
        } @else {
          <p class="membership muted">Check asks the node whether you're one of its users.</p>
        }

        @if (link.joined(); as joined) {
          <p class="joined">
            @switch (joined.outcome) {
              @case ('sent') {
                Asked, as {{ joined.name }}. An admin approves it; their welcome shows here when it
                comes.
              }
              @case ('updated') {
                Asked again, as {{ joined.name }}. An admin approves it; their welcome shows here.
              }
              @case ('already') {
                You're already a user.
              }
              @default {
                The node turned it down; what it said is below.
              }
            }
          </p>
        }

        @if (link.exchange(); as ex) {
          <p class="step" [class.problem]="ex.step === 'not delivered' || ex.step === 'failed'">
            @switch (ex.step) {
              @case ('sending') {
                Sending {{ ex.label }}{{ ex.attempt > 1 ? ' (try ' + ex.attempt + ')' : '' }}…
              }
              @case ('waiting') {
                {{ ex.label }} delivered; waiting for the answer. Over several hops it can take
                {{ firstReplyMinutes }} minutes.
              }
              @case ('not delivered') {
                {{ ex.label }} wasn't delivered: the node's radio didn't acknowledge it. Is it in
                range?
              }
              @case ('no answer') {
                No answer to {{ ex.label }} in {{ firstReplyMinutes }} minutes.
              }
              @case ('failed') {
                {{ ex.label }} couldn't be sent: {{ ex.text }}
              }
              @default {
                The node answered {{ ex.label }}:
              }
            }
          </p>
          @if (ex.step === 'answered' && ex.text) {
            <p class="said">{{ ex.text }}</p>
          }
        }

        <div class="actions">
          <button class="btn btn-sm" type="button" [disabled]="!ready()" (click)="link.check()">
            Check
          </button>
          @if (!link.whoami()?.user) {
            <button class="btn btn-sm" type="button" [disabled]="!ready()" (click)="link.join()">
              Join
            </button>
          }
          <button class="btn btn-ghost btn-sm" type="button" (click)="link.unchoose()">
            Change node
          </button>
        </div>
        @if (radio.state() !== 'connected') {
          <p class="muted">Connect your radio to reach the node.</p>
        }
      } @else {
        <h2>The node</h2>
        @if (radio.state() === 'connected') {
          <p class="muted">Pick the node from your radio's contacts.</p>
          @if (contacts(); as list) {
            @if (list.length) {
              <ul class="contacts">
                @for (contact of list; track contact.publicKey) {
                  <li>
                    <button class="btn btn-ghost" type="button" (click)="pick(contact)">
                      {{ contact.name }}
                    </button>
                  </li>
                }
              </ul>
            } @else {
              <p>None yet.</p>
            }
          }
          <p class="muted">
            Not listed? It appears once your radio hears the node's advert. Send yours so the node
            hears you too.
          </p>
          <div class="actions">
            <button class="btn btn-ghost btn-sm" type="button" (click)="advert()">
              Send an advert
            </button>
            <button class="btn btn-ghost btn-sm" type="button" (click)="loadContacts()">
              Refresh
            </button>
          </div>
          @if (said(); as said) {
            <p class="muted">{{ said }}</p>
          }
        } @else {
          <p class="muted">Connect your radio, then pick the node from its contacts.</p>
        }
      }
    </section>

    @if (link.notices().length) {
      <section class="panel">
        <h2>From the node</h2>
        <ul class="notices">
          @for (notice of link.notices(); track notice.at + notice.text) {
            <li>
              <time>{{ notice.at | date: 'MMM d, h:mm a' }}</time>
              {{ notice.text }}
            </li>
          }
        </ul>
      </section>
    }

    <ul class="more">
      <li>
        <a routerLink="/email"><mc-icon name="mail" /> Email</a>
      </li>
      <li>
        <a routerLink="/weather"><mc-icon name="cloud" /> Weather and verse</a>
      </li>
    </ul>
  `,
})
export class NodeScreen {
  protected readonly radio = inject(Radio);
  protected readonly link = inject(NodeLink);
  protected readonly contacts = signal<RadioContact[] | null>(null);
  protected readonly said = signal<string | null>(null);
  protected readonly firstReplyMinutes = FIRST_REPLY_MS / 60_000;

  constructor() {
    // The radio's contacts, to pick the node from, once it's connected.
    effect(() => {
      if (this.radio.state() === 'connected' && !this.link.node()) {
        void this.loadContacts();
      }
    });
  }

  /** Commands can go out: a radio, and no command in flight. */
  protected ready(): boolean {
    const step = this.link.exchange()?.step;
    return this.radio.state() === 'connected' && step !== 'sending' && step !== 'waiting';
  }

  protected async loadContacts(): Promise<void> {
    try {
      const all = await this.radio.contacts();
      this.contacts.set(all.filter((c) => c.type === COMPANION));
    } catch {
      this.said.set("The radio didn't list its contacts. Try Refresh.");
    }
  }

  protected async advert(): Promise<void> {
    try {
      await this.radio.advert();
      this.said.set(
        'Advert sent. The node lists you once it hears it; its advert reaches you the same way.',
      );
    } catch {
      this.said.set("The advert wasn't sent. Try again.");
    }
  }

  protected pick(contact: RadioContact): void {
    this.link.choose(contact);
    void this.link.check();
  }
}
