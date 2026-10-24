import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { Exchange, FIRST_REPLY_MS } from './node-link';

/** How a command to the node is going: sending, waiting, not delivered… */
@Component({
  selector: 'mc-step-line',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    p {
      margin: 0;
    }
  `,
  template: `
    @let ex = exchange();
    <p class="step" [class.problem]="ex.step === 'not delivered' || ex.step === 'failed'">
      @switch (ex.step) {
        @case ('sending') {
          Sending {{ ex.label }}{{ ex.attempt > 1 ? ' (try ' + ex.attempt + ')' : '' }}…
        }
        @case ('waiting') {
          {{ ex.label }} delivered; waiting for the answer. Over several hops it can take
          {{ minutes }} minutes.
        }
        @case ('not delivered') {
          {{ ex.label }} wasn't delivered: the node's radio didn't acknowledge it. Is it in range?
        }
        @case ('no answer') {
          No answer to {{ ex.label }} in {{ minutes }} minutes.
        }
        @case ('failed') {
          {{ ex.label }} couldn't be sent: {{ ex.text }}
        }
        @default {
          The node answered {{ ex.label }}.
        }
      }
    </p>
  `,
})
export class StepLine {
  readonly exchange = input.required<Exchange>();
  protected readonly minutes = FIRST_REPLY_MS / 60_000;
}
