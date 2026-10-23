import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { timer } from 'rxjs';

import { Api, HistoryEntry } from './api';
import { REFRESH_MS } from './dashboard';
import { Icon } from './icon';
import { ago, when } from './time';

/** What admins (and the console) have done, and users leaving, newest first. */
@Component({
  selector: 'mc-history',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  styleUrl: './records.scss',
  templateUrl: './history.html',
})
export class History {
  private readonly api = inject(Api);
  protected readonly entries = signal<HistoryEntry[] | null>(null);
  protected readonly problem = signal<string | null>(null);
  protected readonly now = signal(Date.now() / 1000);
  protected readonly filter = signal('');
  protected readonly ago = ago;
  protected readonly when = when;
  /** The entries whose who or what has the filter's words in it. */
  protected readonly shown = computed(() => {
    const words = this.filter().toLowerCase().split(/\s+/).filter(Boolean);
    return (this.entries() ?? []).filter((e) => {
      const text = `${e.by} ${e.what}`.toLowerCase();
      return words.every((word) => text.includes(word));
    });
  });

  constructor() {
    timer(0, REFRESH_MS)
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.load());
  }

  load(): void {
    this.api.history().subscribe({
      next: (entries) => {
        this.now.set(Date.now() / 1000);
        this.entries.set(entries);
        this.problem.set(null);
      },
      error: () => this.problem.set("can't read the history: is the bot running?"),
    });
  }
}
