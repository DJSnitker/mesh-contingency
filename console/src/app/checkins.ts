import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { timer } from 'rxjs';

import { Api, Checkins as Found } from './api';
import { REFRESH_MS } from './dashboard';
import { Icon } from './icon';
import { Reply, Runner } from './runner';
import { ago } from './time';

/**
 * The roll call: who has checked in with ok, newest first, and the users
 * who haven't. clearstatus empties it; over the radio it acts at once, so
 * the page asks first.
 */
@Component({
  selector: 'mc-checkins',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, Reply],
  providers: [Runner],
  styleUrl: './records.scss',
  templateUrl: './checkins.html',
})
export class Checkins {
  private readonly api = inject(Api);
  protected readonly runner = inject(Runner);
  protected readonly found = signal<Found | null>(null);
  protected readonly problem = signal<string | null>(null);
  protected readonly now = signal(Date.now() / 1000);
  /** Clear was pressed once: it waits for Yes. */
  protected readonly clearing = signal(false);
  protected readonly ago = ago;

  constructor() {
    this.runner.onDone = () => this.load();
    timer(0, REFRESH_MS)
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.load());
  }

  load(): void {
    this.api.checkins().subscribe({
      next: (found) => {
        this.now.set(Date.now() / 1000);
        this.found.set(found);
        this.problem.set(null);
      },
      error: () => this.problem.set("can't read the check-ins: is the bot running?"),
    });
  }

  protected clear(): void {
    this.clearing.set(false);
    this.runner.run('clearstatus');
  }
}
