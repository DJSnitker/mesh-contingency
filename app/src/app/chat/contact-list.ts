import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { NodeLink } from '../node/node-link';
import { COMPANION, Radio, RadioContact } from '../radio/radio';
import { ChatHistory } from './chat-history';
import { ChatTabs } from './chat-tabs';

/** Show the filter box from this many contacts. */
const FILTER_FROM = 8;

/** When a contact was last heard, and how far away it is. */
export function heard(contact: RadioContact, now = Date.now()): string {
  const parts: string[] = [];
  if (contact.lastAdvert) {
    const minutes = Math.max(0, Math.round((now / 1000 - contact.lastAdvert) / 60));
    parts.push(
      minutes < 60
        ? `Heard ${minutes} min ago`
        : minutes < 48 * 60
          ? `Heard ${Math.round(minutes / 60)} h ago`
          : `Heard ${Math.round(minutes / (24 * 60))} days ago`,
    );
  }
  parts.push(
    contact.hops === null
      ? 'no path yet'
      : contact.hops === 0
        ? 'direct'
        : contact.hops === 1
          ? '1 hop'
          : `${contact.hops} hops`,
  );
  return parts.join(' · ');
}

/**
 * The Contacts tab: the radio's companion contacts, each starting (or going
 * back to) its chat. The node's contact is left out: its
 * commands are on the Node screen.
 */
@Component({
  selector: 'mc-contact-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ChatTabs, RouterLink],
  styles: `
    :host {
      display: grid;
      gap: 16px;
    }
    .panel {
      display: grid;
      gap: 12px;
    }
    h2,
    p {
      margin: 0;
    }
    .loading {
      justify-content: center;
      padding: 32px 0;
      text-align: left;
    }
  `,
  template: `
    <mc-chat-tabs />

    @if (radio.state() !== 'connected') {
      <p class="muted">Connect your radio first, on the <a routerLink="/node">Node</a> screen.</p>
    }
    @if (problem(); as said) {
      <p class="said">{{ said }}</p>
    }

    @if (history.loadingContacts()) {
      <section class="panel">
        <div class="loading" role="status">
          <span class="spinner"></span>
          <span>Reading the contacts from your radio…<br />With many, it takes a while.</span>
        </div>
      </section>
    } @else if (radio.state() === 'connected' || history.contacts()) {
      @if (people().length >= filterFrom) {
        <label class="field">
          Find
          <input
            name="find"
            type="search"
            autocomplete="off"
            [value]="find()"
            (input)="find.set(value($event))"
          />
        </label>
      }

      <section class="panel direct">
        <h2>Contacts</h2>
        @if (shown().length) {
          <ul class="rows">
            @for (contact of shown(); track contact.publicKey) {
              <li>
                <a [routerLink]="['/chat', 'dm', contact.publicKey]">
                  <span class="name">{{ contact.name }}</span>
                  <span class="sub">{{ heard(contact) }}</span>
                </a>
              </li>
            }
          </ul>
        } @else if (find()) {
          <p class="muted">None by that name.</p>
        } @else {
          <p class="muted">No contacts yet: they're added as the radio hears their adverts.</p>
        }
        @if (node(); as n) {
          <p class="muted">
            {{ n.name }} is the node: its commands are on the <a routerLink="/node">Node</a> screen.
          </p>
        }
      </section>

      <div class="actions">
        <button
          class="btn btn-ghost btn-sm"
          type="button"
          [disabled]="radio.state() !== 'connected'"
          (click)="refresh()"
        >
          Refresh
        </button>
      </div>
    }
  `,
})
export class ContactList {
  protected readonly radio = inject(Radio);
  protected readonly history = inject(ChatHistory);
  private readonly link = inject(NodeLink);
  protected readonly heard = heard;
  protected readonly filterFrom = FILTER_FROM;

  protected readonly find = signal('');
  protected readonly problem = signal<string | null>(null);

  /** The node's contact, when the radio has it. */
  protected readonly node = computed(() =>
    this.history.contacts()?.find((c) => c.publicKey === this.link.node()?.publicKey),
  );
  /** The companions, which can be sent to: not repeaters or rooms, and not the node. */
  protected readonly people = computed(() =>
    (this.history.contacts() ?? []).filter(
      (c) => c.type === COMPANION && c.publicKey !== this.link.node()?.publicKey,
    ),
  );
  protected readonly shown = computed(() => this.people().filter((c) => this.matches(c.name)));

  constructor() {
    effect(() => {
      if (this.radio.state() === 'connected') {
        void this.refresh(false);
      }
    });
  }

  protected value(event: Event): string {
    return (event.target as HTMLInputElement).value;
  }

  protected async refresh(again = true): Promise<void> {
    this.problem.set(null);
    try {
      await this.history.refresh(again);
    } catch (error) {
      this.problem.set(`Couldn't read the radio's contacts and channels: ${String(error)}`);
    }
  }

  private matches(name: string): boolean {
    return name.toLowerCase().includes(this.find().trim().toLowerCase());
  }
}
