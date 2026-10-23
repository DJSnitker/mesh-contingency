import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { Api } from './api';
import { Icon } from './icon';

/** The pages, in the order of the rail. */
export const PAGES = [{ path: '/', label: 'Dashboard', icon: 'gauge' }];

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
