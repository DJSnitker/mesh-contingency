import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { MORE } from './app';
import { Icon } from './icon';

/** At phone width, the More tab: the pages that aren't in the tab bar. */
@Component({
  selector: 'mc-more',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, RouterLink],
  styles: `
    :host {
      display: grid;
      gap: 20px;
    }
  `,
  template: `
    <header class="title"><h1>More</h1></header>
    <ul class="more">
      @for (page of pages; track page.path) {
        <li>
          <a [routerLink]="page.path"><mc-icon [name]="page.icon" /> {{ page.label }}</a>
        </li>
      }
    </ul>
  `,
})
export class More {
  protected readonly pages = MORE;
}
