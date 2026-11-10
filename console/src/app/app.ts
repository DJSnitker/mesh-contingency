import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map, timer } from 'rxjs';

import { Api } from './api';
import { Icon } from './icon';
import { Login } from './login';
import { Unread, UNREAD_REFRESH_MS } from './unread';

/**
 * The rail's pages, grouped as the phone app's tabs are: the Dashboard first,
 * set apart; what people do (Mailbox to Bible); then what only admins look
 * after (Radio, Users, Console users, History).
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
  { path: '/console-users', label: 'Console users', icon: 'lock' },
  { path: '/history', label: 'History', icon: 'clock' },
];

/** At phone width, the bottom bar's tabs; More lists the other pages. */
export const TABS = ['/', '/mailbox', '/contacts', '/weather'];
/** Who this is, and their password: at the foot of the rail, and in More at phone width. */
export const ACCOUNT = { path: '/account', label: 'Account', icon: 'lock' };
export const MORE = [...PAGES.filter((page) => !TABS.includes(page.path)), ACCOUNT];

@Component({
  selector: 'mc-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, Login, RouterLink, RouterLinkActive, RouterOutlet],
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  private readonly api = inject(Api);
  protected readonly signedOut = this.api.signedOut;
  /** The remote console wants a login, rather than the console.url link. */
  protected readonly loginNeeded = this.api.loginNeeded;
  protected readonly me = this.api.me;
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
    this.api.whoAmI();
    const unread = inject(Unread);
    timer(0, UNREAD_REFRESH_MS)
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        if (!this.signedOut()) {
          unread.refresh();
        }
      });
  }

  protected logOut(): void {
    this.api.logOut().subscribe({ error: () => undefined });
  }
}
