import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { Icon } from '../icon';
import { ChatHistory } from './chat-history';

/** The Chat screen's heading, and its tabs: chats with people, the channels, and the contacts. */
@Component({
  selector: 'mc-chat-tabs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, RouterLink, RouterLinkActive],
  styles: `
    :host {
      display: grid;
      gap: 12px;
    }
    h1 {
      margin: 0;
    }
    nav {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
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
    .badge {
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
    <h1><mc-icon name="chat" /> Chat</h1>
    <nav aria-label="Chat">
      <a
        routerLink="/chat"
        routerLinkActive="active"
        [routerLinkActiveOptions]="{ exact: true }"
        ariaCurrentWhenActive="page"
      >
        Chat
        @if (history.unreadDirect()) {
          <span class="badge" [attr.aria-label]="history.unreadDirect() + ' unread'">{{
            history.unreadDirect()
          }}</span>
        }
      </a>
      <a routerLink="/chat/channels" routerLinkActive="active" ariaCurrentWhenActive="page">
        Channels
        @if (history.unreadChannels()) {
          <span class="badge" [attr.aria-label]="history.unreadChannels() + ' unread'">{{
            history.unreadChannels()
          }}</span>
        }
      </a>
      <a routerLink="/chat/contacts" routerLinkActive="active" ariaCurrentWhenActive="page">
        Contacts
      </a>
    </nav>
  `,
})
export class ChatTabs {
  protected readonly history = inject(ChatHistory);
}
