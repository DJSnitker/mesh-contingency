import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { NodeLink } from './node-link';

/** Says to connect the radio and pick the node, on a screen that needs both. */
@Component({
  selector: 'mc-needs-node',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    @if (!link.node() || link.radioState() !== 'connected') {
      <section class="panel">
        <p class="muted">
          Connect your radio and pick the node first, on the <a routerLink="/node">Node</a> screen.
        </p>
      </section>
    }
  `,
  styles: `
    p {
      margin: 0;
    }
  `,
})
export class NeedsNode {
  protected readonly link = inject(NodeLink);
}
