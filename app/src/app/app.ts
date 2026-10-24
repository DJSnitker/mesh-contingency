import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { TABS } from './app.routes';
import { ChatHistory } from './chat/chat-history';
import { Icon } from './icon';
import { Radio } from './radio/radio';

@Component({
  selector: 'mc-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, RouterLink, RouterLinkActive, RouterOutlet],
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  protected readonly tabs = TABS;
  protected readonly radio = inject(Radio);
  /** Started with the app, so messages are kept while Chat isn't open. */
  protected readonly chats = inject(ChatHistory);

  /** The header's word on the radio. */
  protected readonly radioState = computed(() => {
    switch (this.radio.state()) {
      case 'connected':
        return this.radio.name();
      case 'connecting':
        return 'Connecting…';
      case 'lost':
        return 'Radio lost';
      default:
        return 'No radio';
    }
  });

  constructor() {
    // Back to the radio from last time, if there was one.
    void this.radio.reconnect();
  }
}
