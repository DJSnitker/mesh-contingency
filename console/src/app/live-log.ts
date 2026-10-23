import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  afterRenderEffect,
  inject,
  signal,
  viewChild,
} from '@angular/core';

import { Api, LogLine } from './api';
import { Icon } from './icon';
import { clock } from './time';

/** Lines shown at most; the bot keeps 500. */
export const MAX_LINES = 500;

/** What the bot prints, as it prints it (GET /api/log). */
@Component({
  selector: 'mc-live-log',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  styleUrl: './live-log.scss',
  template: `
    <section class="panel log" aria-labelledby="log-title">
      <header>
        <h2 id="log-title"><mc-icon name="terminal" /> Live log</h2>
        <span class="state" [class.live]="connected()">{{
          connected() ? 'live' : 'reconnecting…'
        }}</span>
      </header>
      <div #scroller class="lines" role="log" aria-live="polite" (scroll)="onScroll()">
        @for (entry of lines(); track $index) {
          <div class="line">
            <time>{{ clock(entry.time) }}</time
            ><span>{{ entry.line }}</span>
          </div>
        } @empty {
          <p class="muted">Nothing printed yet.</p>
        }
      </div>
    </section>
  `,
})
export class LiveLog {
  protected readonly lines = signal<LogLine[]>([]);
  protected readonly connected = signal(false);
  protected readonly clock = clock;
  private readonly scroller = viewChild.required<ElementRef<HTMLElement>>('scroller');
  /** Follow new lines unless the reader has scrolled up. */
  private following = true;

  constructor() {
    const source = inject(Api).log();
    source.onopen = () => {
      // A reconnect sends the kept lines again: start over.
      this.lines.set([]);
      this.connected.set(true);
    };
    source.onerror = () => this.connected.set(false);
    source.onmessage = (event: MessageEvent<string>) => {
      const entry = JSON.parse(event.data) as LogLine;
      this.lines.update((lines) => [...lines, entry].slice(-MAX_LINES));
    };
    inject(DestroyRef).onDestroy(() => source.close());

    afterRenderEffect(() => {
      this.lines();
      if (this.following) {
        const element = this.scroller().nativeElement;
        element.scrollTop = element.scrollHeight;
      }
    });
  }

  protected onScroll(): void {
    const element = this.scroller().nativeElement;
    this.following = element.scrollHeight - element.scrollTop - element.clientHeight < 24;
  }
}
