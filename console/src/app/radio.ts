import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';

import { Api, CommandInfo } from './api';
import { Icon } from './icon';
import { Reply, Runner } from './runner';

/**
 * Controlling the node rather than sending messages: the radio's advert
 * (nearby, or flooded across the mesh) and a backup of the bot's data now.
 * Each offered only if /api/commands has it.
 */
@Component({
  selector: 'mc-radio',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, Reply],
  providers: [Runner],
  styleUrl: './radio.scss',
  templateUrl: './radio.html',
})
export class Radio {
  private readonly api = inject(Api);
  protected readonly runner = inject(Runner);
  protected readonly offered = signal<CommandInfo[] | null>(null);
  protected readonly problem = signal<string | null>(null);

  constructor() {
    this.api.commands().subscribe({
      next: (commands) => {
        this.offered.set(commands);
        this.problem.set(null);
      },
      error: () => this.problem.set("can't reach the bot: is it running?"),
    });
  }

  protected has(name: string): boolean {
    return (this.offered() ?? []).some((c) => c.name === name);
  }
}
