import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { forkJoin } from 'rxjs';

import { Api, JoinRequest, User } from './api';
import { Icon } from './icon';
import { Reply, Runner } from './runner';
import { ago } from './time';

/**
 * Users and join requests: approve or deny a request, whois, resetpass or
 * remove a user, and reload the users file after editing it, through the
 * same commands an admin sends over the radio. Users are named by their full
 * key, so two radios with the same name can't be mixed up.
 */
@Component({
  selector: 'mc-users',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, Reply],
  providers: [Runner],
  styleUrl: './users.scss',
  templateUrl: './users.html',
})
export class Users {
  private readonly api = inject(Api);
  protected readonly runner = inject(Runner);
  protected readonly users = signal<User[] | null>(null);
  protected readonly requests = signal<JoinRequest[]>([]);
  protected readonly problem = signal<string | null>(null);
  /** Whether the console may run reload (the users file, read again now). */
  protected readonly canReload = signal(false);
  /** When the lists were read, for "last seen 5m ago". */
  protected readonly now = signal(Date.now() / 1000);
  protected readonly ago = ago;
  protected readonly counts = computed(() => {
    const users = this.users() ?? [];
    return {
      users: users.filter((u) => u.user).length,
      admins: users.filter((u) => u.admin).length,
    };
  });

  constructor() {
    this.runner.onDone = () => this.load();
    this.load();
    this.api.commands().subscribe({
      next: (commands) => this.canReload.set(commands.some((c) => c.name === 'reload')),
      error: () => undefined, // load() says the bot can't be reached
    });
  }

  load(): void {
    forkJoin({ users: this.api.users(), requests: this.api.requests() }).subscribe({
      next: ({ users, requests }) => {
        this.now.set(Date.now() / 1000);
        this.users.set(users);
        this.requests.set(requests);
        this.problem.set(null);
      },
      error: () => this.problem.set("can't read the users: is the bot running?"),
    });
  }

  /** A user's addresses and other settings, briefly. */
  protected settings(user: User): string[] {
    return Object.entries(user.settings).map(([name, value]) =>
      Array.isArray(value) ? `${name}: ${value.length} addresses` : `${name}: ${value}`,
    );
  }
}
