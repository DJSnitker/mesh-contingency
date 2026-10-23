import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { timer } from 'rxjs';

import { Api, Mailbox } from './api';
import { REFRESH_MS } from './dashboard';
import { Icon } from './icon';
import { ago } from './time';

/**
 * Messages waiting on the node: for whom, from whom, when, read or not,
 * sealed or not. Never what they say: that's for the recipient, with inbox
 * over the radio (and their passphrase, if sealed).
 */
@Component({
  selector: 'mc-inbox',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  styleUrl: './records.scss',
  templateUrl: './inbox.html',
})
export class Inbox {
  private readonly api = inject(Api);
  protected readonly boxes = signal<Mailbox[] | null>(null);
  protected readonly problem = signal<string | null>(null);
  protected readonly now = signal(Date.now() / 1000);
  protected readonly ago = ago;
  protected readonly total = computed(() =>
    (this.boxes() ?? []).reduce((sum, box) => sum + box.messages.length, 0),
  );

  constructor() {
    timer(0, REFRESH_MS)
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.load());
  }

  load(): void {
    this.api.inbox().subscribe({
      next: (boxes) => {
        this.now.set(Date.now() / 1000);
        this.boxes.set(boxes);
        this.problem.set(null);
      },
      error: () => this.problem.set("can't read the inbox: is the bot running?"),
    });
  }

  protected unread(box: Mailbox): number {
    return box.messages.filter((m) => !m.read).length;
  }
}
