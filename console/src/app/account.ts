import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { Api, apiError } from './api';
import { Icon } from './icon';

/** The shortest password the bot takes (console_users.PASSWORD_MIN). */
export const PASSWORD_MIN = 12;

/**
 * Who this browser is, and for a console user on the remote console their
 * own password (the current one first) and logging out. The console on the
 * node's computer has no password: it's opened with the console.url link.
 */
@Component({
  selector: 'mc-account',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  styleUrl: './forms.scss',
  template: `
    <header class="title">
      <div>
        <h1>Account</h1>
        <p class="muted">
          @if (me()?.user; as user) {
            Logged in as <strong>{{ user }}</strong
            >, a console user. What you do shows in History as <code>{{ me()?.name }}</code
            >.
          } @else if (me()) {
            The console on the node's own computer, opened with its link. What it does shows in
            History as <code>console</code>.
          }
        </p>
      </div>
      @if (remote()) {
        <button class="btn btn-ghost btn-sm" type="button" (click)="logOut()">Log out</button>
      }
    </header>

    @if (remote()) {
      <section class="panel narrow" aria-labelledby="password-title">
        <h2 id="password-title"><mc-icon name="lock" /> Change password</h2>
        <form (submit)="$event.preventDefault(); save()">
          <label class="field">
            <span class="label">Current password</span>
            <input
              type="password"
              autocomplete="current-password"
              [value]="current()"
              (input)="current.set(value($event))"
            />
          </label>
          <label class="field">
            <span class="label">New password, {{ min }} or more characters</span>
            <input
              type="password"
              autocomplete="new-password"
              [value]="next()"
              (input)="next.set(value($event))"
            />
          </label>
          <label class="field">
            <span class="label">New password again</span>
            <input
              type="password"
              autocomplete="new-password"
              [value]="again()"
              (input)="again.set(value($event))"
            />
          </label>
          @if (problem()) {
            <p class="problem" role="alert"><mc-icon name="alert" /> {{ problem() }}</p>
          }
          @if (done()) {
            <p class="done" role="status">
              Password changed. You stay logged in here; your other logins have ended.
            </p>
          }
          <div class="actions">
            <button class="btn" type="submit" [disabled]="busy() || !ready()">
              Change password
            </button>
          </div>
        </form>
      </section>
    }
  `,
})
export class Account {
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  protected readonly me = this.api.me;
  protected readonly remote = computed(() => Boolean(this.me()?.remote && this.me()?.user));
  protected readonly min = PASSWORD_MIN;
  protected readonly current = signal('');
  protected readonly next = signal('');
  protected readonly again = signal('');
  protected readonly busy = signal(false);
  protected readonly problem = signal<string | null>(null);
  protected readonly done = signal(false);
  protected readonly ready = computed(() => Boolean(this.current() && this.next() && this.again()));

  protected value(event: Event): string {
    return (event.target as HTMLInputElement).value;
  }

  protected save(): void {
    this.done.set(false);
    if (this.next() !== this.again()) {
      this.problem.set("The new passwords don't match.");
      return;
    }
    if (this.next().length < PASSWORD_MIN) {
      this.problem.set(`A password is ${PASSWORD_MIN} or more characters.`);
      return;
    }
    this.busy.set(true);
    this.problem.set(null);
    this.api.changePassword(this.current(), this.next()).subscribe({
      next: () => {
        this.busy.set(false);
        this.done.set(true);
        this.current.set('');
        this.next.set('');
        this.again.set('');
      },
      error: (error) => {
        this.busy.set(false);
        this.problem.set(apiError(error, "Can't change it: is the bot running?"));
      },
    });
  }

  protected logOut(): void {
    this.api.logOut().subscribe({
      next: () => void this.router.navigateByUrl('/'),
      error: () => void this.router.navigateByUrl('/'),
    });
  }
}
