import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { Icon } from './icon';
import { Unread } from './unread';

/**
 * The Contacts section's heading and its tabs: the radio's channels (with
 * their unread count) and its contacts. The console doesn't chat: people
 * talk through msg and the channels, and direct messages to the node are
 * commands.
 */
@Component({
  selector: 'mc-contacts-tabs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, RouterLink, RouterLinkActive],
  styles: `
    :host {
      display: grid;
      gap: 12px;
    }
    h1,
    p {
      margin: 0;
    }
    nav {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      max-width: 360px;
      padding: 4px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--ink-2);
    }
    a {
      display: flex;
      gap: 6px;
      align-items: center;
      justify-content: center;
      padding: 8px;
      border-radius: 8px;
      color: var(--muted);
      font-weight: 600;
      text-decoration: none;
    }
    a.active {
      background: var(--ink-3);
      color: var(--text);
    }
    .unread {
      min-width: 1.4em;
      padding: 0 5px;
      border-radius: 999px;
      background: var(--orange);
      color: var(--ink);
      font-size: 0.75rem;
      line-height: 1.4em;
      text-align: center;
    }
  `,
  template: `
    <header>
      <h1>Contacts</h1>
      <p class="muted">The radio's channels, to read and post on, and its contacts.</p>
    </header>
    <nav aria-label="Contacts">
      <a routerLink="/contacts/channels" routerLinkActive="active">
        <mc-icon name="send" /> Channels
        @if (unread.total(); as n) {
          <span class="unread" [attr.aria-label]="n + ' unread'">{{ n }}</span>
        }
      </a>
      <a routerLink="/contacts/list" routerLinkActive="active">
        <mc-icon name="users" /> Contacts
      </a>
    </nav>
  `,
})
export class ContactsTabs {
  protected readonly unread = inject(Unread);
}
