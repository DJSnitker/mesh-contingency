import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { catchError, EMPTY, switchMap, tap, timer } from 'rxjs';

import { Api, Overview } from './api';
import { Icon } from './icon';
import { LiveLog } from './live-log';
import { ago, duration } from './time';

/** How often the overview is read again (ms). */
export const REFRESH_MS = 30_000;

/** How the node is doing, at a glance: what health says, as tiles. */
@Component({
  selector: 'mc-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, LiveLog, RouterLink],
  styleUrl: './dashboard.scss',
  templateUrl: './dashboard.html',
})
export class Dashboard {
  private readonly api = inject(Api);
  protected readonly overview = signal<Overview | null>(null);
  /** Why the last read failed, until one works. */
  protected readonly problem = signal<string | null>(null);

  protected readonly up = computed(() => {
    const o = this.overview();
    return o ? duration(o.now - o.started) : '';
  });
  protected readonly watch = computed(() => {
    const problems = this.overview()?.watch;
    if (problems == null) {
      return { ok: true, text: 'off' };
    }
    return problems.length
      ? { ok: false, text: problems.join(', ') }
      : { ok: true, text: 'no problems' };
  });
  /** The weather alerts out now, each with the counties it covers, by name. */
  protected readonly alerts = computed(() => {
    const alerts = this.overview()?.alerts;
    if (!alerts) {
      return { ok: true, text: 'off' };
    }
    if (alerts.active.length) {
      const named = alerts.active.map(
        (alert) => `${alert.event} (${alert.counties.map((c) => c.split(', ')[0]).join(', ')})`,
      );
      return { ok: false, text: named.join('; ') };
    }
    if (alerts.problem) {
      return { ok: false, text: `can't check: ${alerts.problem}` };
    }
    return { ok: true, text: alerts.checked ? 'none' : 'not checked yet' };
  });
  protected readonly backup = computed(() => {
    const o = this.overview();
    if (!o?.backup) {
      return { ok: true, text: 'off' };
    }
    if (o.backup.failing) {
      return { ok: false, text: `failing: ${o.backup.failing}` };
    }
    return o.backup.last
      ? { ok: true, text: `last ${ago(o.backup.last, o.now)}` }
      : { ok: true, text: 'no backup yet' };
  });

  constructor() {
    timer(0, REFRESH_MS)
      .pipe(
        switchMap(() =>
          this.api.overview().pipe(
            tap(() => this.problem.set(null)),
            catchError((error: HttpErrorResponse) => {
              this.problem.set(
                error.status === 0
                  ? "can't reach the bot: is it running?"
                  : `the bot said ${error.status}`,
              );
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(),
      )
      .subscribe((overview) => this.overview.set(overview));
  }
}
