import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Icon } from './icon';
import { Radio } from './radio/radio';

/** The Node screen: connecting to the user's radio; the node itself comes next. */
@Component({
  selector: 'mc-node',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, RouterLink],
  styles: `
    .panel {
      display: grid;
      gap: 12px;
    }
    h2,
    p {
      margin: 0;
    }
    dl {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 4px 16px;
      margin: 0;
    }
    dt {
      color: var(--muted);
    }
    dd {
      margin: 0;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
  `,
  template: `
    <h1><mc-icon name="radio" /> Node</h1>

    <section class="panel radio">
      <h2>Your radio</h2>
      @switch (radio.state()) {
        @case ('connected') {
          <dl>
            <dt>Name</dt>
            <dd class="radio-name">{{ radio.name() }}</dd>
            @if (radio.batteryMilliVolts(); as mv) {
              <dt>Battery</dt>
              <dd class="battery">{{ (mv / 1000).toFixed(2) }} V</dd>
            }
            @if (radio.firmware(); as firmware) {
              <dt>Firmware</dt>
              <dd>{{ firmware }}</dd>
            }
          </dl>
          <div class="actions">
            <button class="btn btn-ghost btn-sm" type="button" (click)="radio.disconnect()">
              Disconnect
            </button>
            <button class="btn btn-ghost btn-sm danger" type="button" (click)="radio.forget()">
              Forget it
            </button>
          </div>
        }
        @case ('connecting') {
          <p>Connecting to {{ radio.name() ?? 'your radio' }}…</p>
        }
        @default {
          @if (radio.hasRemembered()) {
            <p>
              <span class="radio-name">{{ radio.name() }}</span>
              <span class="muted"> isn't connected.</span>
            </p>
            <div class="actions">
              <button class="btn btn-sm" type="button" (click)="radio.reconnect()">
                Reconnect
              </button>
              <button class="btn btn-ghost btn-sm" type="button" (click)="radio.pick()">
                Pick another
              </button>
            </div>
          } @else {
            <p class="muted">
              Turn on your MeshCore radio near the phone, then pick it from the list. The phone asks
              for its Bluetooth PIN the first time.
            </p>
            <div class="actions">
              <button class="btn" type="button" (click)="radio.pick()">
                <mc-icon name="radio" /> Find my radio
              </button>
            </div>
          }
        }
      }
      @if (radio.problem(); as problem) {
        <p class="problem" role="alert"><mc-icon name="alert" /> {{ problem }}</p>
      }
    </section>

    <section class="panel">
      <p class="muted">
        Picking the node, seeing whether you are a user, and asking to join come in the app's
        "Commands over the mesh" step.
      </p>
    </section>

    <ul class="more">
      <li>
        <a routerLink="/email"><mc-icon name="mail" /> Email</a>
      </li>
      <li>
        <a routerLink="/weather"><mc-icon name="cloud" /> Weather and verse</a>
      </li>
    </ul>
  `,
})
export class Node {
  protected readonly radio = inject(Radio);
}
