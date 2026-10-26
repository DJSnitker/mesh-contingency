import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Conversation } from './api';
import { ChatTabs } from './chat-tabs';
import { Icon } from './icon';
import { ago } from './time';
import { Unread } from './unread';

/**
 * Chat's Chats tab, as the phone app's: the console's direct conversations
 * with contacts, the most recent first, each opening its thread (dm.ts),
 * with its newest message and unread replies (unread.ts). A chat starts
 * from the Contacts tab. Only the console's messages and the replies to them
 * are kept, never commands sent to the node.
 */
@Component({
  selector: 'mc-chat',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ChatTabs, Icon, RouterLink],
  styles: `
    :host {
      display: grid;
      gap: 20px;
    }
    .panel {
      display: grid;
      gap: 12px;
    }
    p {
      margin: 0;
    }
    .sub .failed {
      color: var(--orange);
    }
  `,
  template: `
    <mc-chat-tabs />
    @if (unread.conversationsProblem(); as said) {
      <p class="problem" role="alert"><mc-icon name="alert" /> {{ said }}</p>
    }

    <section class="panel" aria-labelledby="chats-title">
      <h2 id="chats-title"><mc-icon name="chat" /> Chats</h2>
      @if (unread.conversationsRead()) {
        @if (unread.conversations(); as all) {
          @if (all.length) {
            <ul class="rows" aria-label="The console's chats">
              @for (chat of all; track chat.key) {
                <li>
                  <a [routerLink]="['/chat', 'dm', chat.key]">
                    <span class="name">{{ chat.name ?? chat.key.slice(0, 12) }}</span>
                    @if (chat.last; as last) {
                      <span class="side">{{ ago(last.time, now()) }}</span>
                      <span class="sub">
                        @if (last.own) {
                          You:
                        }
                        {{ last.text }}
                        @if (last.status === 'not delivered') {
                          <span class="failed">· not delivered</span>
                        }
                      </span>
                    }
                    @if (unread.dmCount(chat.key, chat.heard); as n) {
                      <span class="unread" [attr.aria-label]="n + ' unread'">{{ n }}</span>
                    }
                  </a>
                </li>
              }
            </ul>
          } @else {
            <p class="muted">
              No chats yet. Start one from <a routerLink="/chat/contacts">Contacts</a>: message
              anyone the radio has as a contact, as the node.
            </p>
          }
          <p class="muted">
            Only the console's messages and the replies to them, in the bot's memory: a restart
            forgets them. Commands people send the node, and its answers, are never kept.
          </p>
        } @else {
          <p class="muted">The bot isn't keeping the console's chats.</p>
        }
      } @else if (!unread.conversationsProblem()) {
        <p class="loading" role="status"><span class="spinner"></span> Reading the chats…</p>
      }
    </section>
  `,
})
export class Chat {
  protected readonly unread = inject(Unread);
  /** When the chats were read, for "5m ago". */
  protected readonly now = computed(
    () => (this.unread.conversations() as Conversation[] | null, Date.now() / 1000),
  );
  protected readonly ago = ago;

  constructor() {
    this.unread.refreshConversations();
  }
}
