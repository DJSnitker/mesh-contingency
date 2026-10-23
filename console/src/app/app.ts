import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { Api } from './api';
import { Icon } from './icon';

/** The pages, in the order of the rail. */
/** The rail's pages: the Dashboard first, set apart, then the rest A–Z. */
export const PAGES = [
  { path: '/', label: 'Dashboard', icon: 'gauge' },
  { path: '/weather', label: 'Area Weather', icon: 'cloud' },
  { path: '/checkins', label: 'Check-ins', icon: 'check' },
  { path: '/history', label: 'History', icon: 'clock' },
  { path: '/inbox', label: 'Inbox', icon: 'inbox' },
  { path: '/radio', label: 'Radio', icon: 'radio' },
  { path: '/send', label: 'Send', icon: 'send' },
  { path: '/users', label: 'Users', icon: 'users' },
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
