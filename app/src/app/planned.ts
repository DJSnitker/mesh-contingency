import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { Icon } from './icon';

/** What a screen not built yet will do, from its route's data. */
export interface PlannedData {
  icon: string;
  what: string;
  /** The PR that builds it, as docs/plans/mobile-app.md names it. */
  pr: string;
  more?: { path: string; label: string; icon: string }[];
}

/** A screen that isn't built yet: what it will do, and where it's planned. */
@Component({
  selector: 'mc-planned',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, RouterLink],
  styles: `
    h1 {
      display: flex;
      gap: 10px;
      align-items: center;
    }
    .panel {
      display: grid;
      gap: 10px;
    }
    .more {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .more a {
      display: flex;
      gap: 10px;
      align-items: center;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--panel);
      color: var(--text);
      text-decoration: none;
    }
  `,
  template: `
    @if (data(); as d) {
      <h1><mc-icon [name]="d['icon']" /> {{ title() }}</h1>
      <section class="panel">
        <p>{{ d['what'] }}</p>
        <p class="muted">Coming in the app's "{{ d['pr'] }}" step.</p>
      </section>
      @if (d['more']; as more) {
        <ul class="more">
          @for (link of more; track link.path) {
            <li>
              <a [routerLink]="link.path"><mc-icon [name]="link.icon" /> {{ link.label }}</a>
            </li>
          }
        </ul>
      }
    }
  `,
})
export class Planned {
  private readonly route = inject(ActivatedRoute);
  protected readonly data = toSignal(this.route.data);
  protected readonly title = toSignal(this.route.title);
}
