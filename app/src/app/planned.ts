import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';

import { Icon } from './icon';

/** What a screen not built yet will do, from its route's data. */
export interface PlannedData {
  icon: string;
  what: string;
  /** The PR that builds it, as docs/plans/mobile-app.md names it. */
  pr: string;
}

/** A screen that isn't built yet: what it will do, and where it's planned. */
@Component({
  selector: 'mc-planned',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  styles: `
    .panel {
      display: grid;
      gap: 10px;
    }
  `,
  template: `
    @if (data(); as d) {
      <h1><mc-icon [name]="d['icon']" /> {{ title() }}</h1>
      <section class="panel">
        <p>{{ d['what'] }}</p>
        <p class="muted">Coming in the app's "{{ d['pr'] }}" step.</p>
      </section>
    }
  `,
})
export class Planned {
  private readonly route = inject(ActivatedRoute);
  protected readonly data = toSignal(this.route.data);
  protected readonly title = toSignal(this.route.title);
}
