import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  Injectable,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { Answer, Api } from './api';
import { Icon } from './icon';

/** A command the page ran, and what came of it. */
export interface Ran {
  command: string;
  text: string;
  answer?: Answer;
  error?: string;
}

/**
 * Runs commands for one page, one at a time, and keeps the last one's
 * reply. A command that only asks to confirm (remove, resetpass) waits for
 * confirm(), which sends the same again, as an admin would over the radio.
 * Provide it in the page's component.
 */
@Injectable()
export class Runner {
  private readonly api = inject(Api);
  readonly busy = signal(false);
  readonly last = signal<Ran | null>(null);
  /** Called after a command that may have changed something has run. */
  onDone: () => void = () => undefined;

  run(command: string, text = ''): void {
    if (this.busy()) {
      return;
    }
    this.busy.set(true);
    this.api.run(command, text).subscribe({
      next: (answer) => {
        this.busy.set(false);
        this.last.set({ command, text, answer });
        if (!answer.asks) {
          this.onDone();
        }
      },
      error: (error: HttpErrorResponse) => {
        this.busy.set(false);
        const said = typeof error.error === 'object' && error.error?.error;
        this.last.set({
          command,
          text,
          error:
            said || (error.status === 0 ? "can't reach the bot" : `the bot said ${error.status}`),
        });
      },
    });
  }

  /** Send the command that asked to confirm again. */
  confirm(): void {
    const last = this.last();
    if (last?.answer?.asks) {
      this.run(last.command, last.text);
    }
  }

  dismiss(): void {
    this.last.set(null);
  }
}

/** The last command's reply, with Confirm and Cancel when it asks. */
@Component({
  selector: 'mc-reply',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  styleUrl: './reply.scss',
  template: `
    @if (ran(); as r) {
      <section
        class="panel reply"
        [class.asks]="r.answer?.asks"
        [class.failed]="r.error"
        role="status"
        aria-live="polite"
      >
        <mc-icon [name]="r.error ? 'alert' : r.answer?.asks ? 'lock' : 'terminal'" />
        <div class="body">
          @if (r.error) {
            <p>{{ r.error }}</p>
          } @else {
            @for (message of r.answer?.messages; track $index) {
              <p>{{ message }}</p>
            } @empty {
              <p class="muted">{{ r.command }}: no reply</p>
            }
          }
          @if (r.answer?.asks) {
            <div class="actions">
              <button
                class="btn btn-sm"
                type="button"
                [disabled]="busy()"
                (click)="confirmed.emit()"
              >
                Confirm
              </button>
              <button class="btn btn-ghost btn-sm" type="button" (click)="dismissed.emit()">
                Cancel
              </button>
            </div>
          }
        </div>
        @if (!r.answer?.asks) {
          <button class="close" type="button" aria-label="Dismiss" (click)="dismissed.emit()">
            ×
          </button>
        }
      </section>
    }
  `,
})
export class Reply {
  readonly ran = input<Ran | null>(null);
  readonly busy = input(false);
  readonly confirmed = output();
  readonly dismissed = output();
}
