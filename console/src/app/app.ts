import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';

import { Api } from './api';
import { Icon } from './icon';

/**
 * The rail's pages, grouped as the phone app's tabs are: the Dashboard first,
 * set apart; what people do (Mailbox to Bible); then what only admins look
 * after (Radio, Users, History).
 */
export const PAGES = [
  { path: '/', label: 'Dashboard', icon: 'gauge' },
  { path: '/mailbox', label: 'Mailbox', icon: 'inbox' },
  { path: '/checkins', label: 'Check-ins', icon: 'check' },
  { path: '/chat', label: 'Chat', icon: 'chat' },
  { path: '/weather', label: 'Weather', icon: 'cloud' },
  { path: '/bible', label: 'Bible', icon: 'book' },
  { path: '/radio', label: 'Radio', icon: 'radio' },
  { path: '/users', label: 'Users', icon: 'users' },
  { path: '/history', label: 'History', icon: 'clock' },
];

/** At phone width, the bottom bar's tabs; More lists the other pages. */
export const TABS = ['/', '/mailbox', '/chat', '/weather'];
export const MORE = PAGES.filter((page) => !TABS.includes(page.path));

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
  protected readonly tabs = PAGES.filter((page) => TABS.includes(page.path));

  private readonly url = toSignal(
    inject(Router).events.pipe(
      filter((event) => event instanceof NavigationEnd),
      map((event) => event.urlAfterRedirects),
    ),
    { initialValue: '/' },
  );
  /** More is lit on its own page and on each page it lists. */
  protected readonly inMore = computed(() => {
    const path = this.url().split(/[?#]/)[0];
    return path === '/more' || MORE.some((page) => path.startsWith(page.path));
  });
}
