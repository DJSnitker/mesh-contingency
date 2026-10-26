import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { Icon } from './icon';
import { Unread } from './unread';

/**
 * Chat's heading and its tabs, as the phone app's: the console's direct
 * messages, the radio's channels (each with its unread count) and its
 * contacts.
 */
@Component({
  selector: 'mc-chat-tabs',
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
      grid-template-columns: repeat(3, 1fr);
      max-width: 520px;
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
      <h1>Chat</h1>
      <p class="muted">
        Message the radio's contacts as the node, and read and post on its channels.
      </p>
    </header>
    <nav aria-label="Chat">
      <a routerLink="/chat" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }">
        <mc-icon name="chat" /> Chats
        @if (unread.dmTotal(); as n) {
          <span class="unread" [attr.aria-label]="n + ' unread'">{{ n }}</span>
        }
      </a>
      <a routerLink="/chat/channels" routerLinkActive="active">
        <mc-icon name="send" /> Channels
        @if (unread.channelTotal(); as n) {
          <span class="unread" [attr.aria-label]="n + ' unread'">{{ n }}</span>
        }
      </a>
      <a routerLink="/chat/contacts" routerLinkActive="active">
        <mc-icon name="users" /> Contacts
      </a>
    </nav>
  `,
})
export class ChatTabs {
  protected readonly unread = inject(Unread);
}
