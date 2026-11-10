import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';

import { Api, apiError } from './api';
import { Icon } from './icon';

/**
 * The remote console's login: a console user's name and password
 * (mesh_contingency/web/remote.py). Console users are separate from the
 * radio's users; they're made on the node with mesh-contingency-console
 * user add, or by another console user. The console on the node's own
 * computer never shows this.
 */
@Component({
  selector: 'mc-login',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  styleUrl: './forms.scss',
  template: `
    <section class="panel login" aria-labelledby="login-title">
      <mc-icon name="lock" />
      <h1 id="login-title">Log in to the console</h1>
      <p class="muted">
        As a console user of this node. Ask another console user, or whoever runs the node, if you
        don't have one.
      </p>
      <form (submit)="$event.preventDefault(); submit()">
        <label class="field">
          <span class="label">Name</span>
          <input
            name="name"
            autocomplete="username"
            autocapitalize="none"
            spellcheck="false"
            required
            [value]="name()"
            (input)="name.set(value($event))"
          />
        </label>
        <label class="field">
          <span class="label">Password</span>
          <input
            name="password"
            type="password"
            autocomplete="current-password"
            required
            [value]="password()"
            (input)="password.set(value($event))"
          />
        </label>
        @if (problem()) {
          <p class="problem" role="alert"><mc-icon name="alert" /> {{ problem() }}</p>
        }
        <button class="btn" type="submit" [disabled]="busy() || !name() || !password()">
          {{ busy() ? 'Logging in…' : 'Log in' }}
        </button>
      </form>
    </section>
  `,
})
export class Login {
  private readonly api = inject(Api);
  protected readonly name = signal('');
  protected readonly password = signal('');
  protected readonly busy = signal(false);
  protected readonly problem = signal<string | null>(null);

  protected value(event: Event): string {
    return (event.target as HTMLInputElement).value;
  }

  protected submit(): void {
    if (this.busy() || !this.name() || !this.password()) {
      return;
    }
    this.busy.set(true);
    this.problem.set(null);
    this.api.logIn(this.name(), this.password()).subscribe({
      next: () => this.password.set(''),
      error: (error) => {
        this.busy.set(false);
        this.password.set('');
        this.problem.set(apiError(error, "Can't reach the bot: is it running?"));
      },
    });
  }
}
