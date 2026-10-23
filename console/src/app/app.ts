import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { Api } from './api';
import { Icon } from './icon';

/** The pages, in the order of the rail. */
export const PAGES = [
  { path: '/', label: 'Dashboard', icon: 'gauge' },
  { path: '/users', label: 'Users', icon: 'users' },
  { path: '/checkins', label: 'Check-ins', icon: 'check' },
  { path: '/inbox', label: 'Inbox', icon: 'inbox' },
  { path: '/history', label: 'History', icon: 'clock' },
  { path: '/send', label: 'Send', icon: 'send' },
  { path: '/radio', label: 'Radio', icon: 'radio' },
];

@Component({
  selector: 'mc-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, RouterLink, RouterLinkActive, RouterOutlet],
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  protected readonly signedOut = inject(Api).signedOut;
  protected readonly pages = PAGES;
}
