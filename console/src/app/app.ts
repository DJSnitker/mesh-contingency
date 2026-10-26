import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map, timer } from 'rxjs';

import { Api } from './api';
import { Icon } from './icon';
import { Unread, UNREAD_REFRESH_MS } from './unread';

/**
 * The rail's pages, grouped as the phone app's tabs are: the Dashboard first,
 * set apart; what people do (Mailbox to Bible); then what only admins look
 * after (Radio, Users, History).
 */
export const PAGES = [
  { path: '/', label: 'Dashboard', icon: 'gauge' },
  { path: '/mailbox', label: 'Mailbox', icon: 'inbox' },
  { path: '/checkins', label: 'Check-ins', icon: 'check' },
  { path: '/contacts', label: 'Contacts', icon: 'users' },
  { path: '/weather', label: 'Weather', icon: 'cloud' },
  { path: '/bible', label: 'Bible', icon: 'book' },
  { path: '/radio', label: 'Radio', icon: 'radio' },
  { path: '/users', label: 'Users', icon: 'users' },
  { path: '/history', label: 'History', icon: 'clock' },
];

/** At phone width, the bottom bar's tabs; More lists the other pages. */
export const TABS = ['/', '/mailbox', '/contacts', '/weather'];
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
  /** The channels' unread messages, beside Chat. */
  protected readonly unread = inject(Unread).total;

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

  constructor() {
    const unread = inject(Unread);
    timer(0, UNREAD_REFRESH_MS)
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        if (!this.signedOut()) {
          unread.refresh();
        }
      });
  }
}
