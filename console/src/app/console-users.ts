import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { PASSWORD_MIN } from './account';
import { Api, apiError, ConsoleUser } from './api';
import { Icon } from './icon';
import { ago } from './time';

/**
 * The console users: the people who log in to the console from other
 * computers on the network (mesh_contingency/web/console_users.py). They're
 * separate from the radio's users and admins on the Users page: a console
 * user needs no radio, and a radio is never one. Add one, give someone a new
 * password (which logs them out), or remove one. Your own password is on the
 * Account page, and you can't remove yourself.
 */
@Component({
  selector: 'mc-console-users',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, RouterLink],
  styleUrl: './forms.scss',
  template: `
    <header class="title">
      <div>
        <h1>Console users</h1>
        <p class="muted">
          Who can log in to this console from another computer on the network, with a name and
          password. Not the radio's users: those are on <a routerLink="/users">Users</a>.
        </p>
      </div>
      @if (problem()) {
        <p class="problem" role="alert"><mc-icon name="alert" /> {{ problem() }}</p>
      }
    </header>

    @if (done()) {
      <p class="done" role="status">{{ done() }}</p>
    }

    @if (users(); as list) {
      @if (!list.length) {
        <p class="panel muted">
          No console users yet. Add one below, or on the node's computer with
          <code>mesh-contingency-console user add NAME</code>.
        </p>
      }
      <ul class="people" aria-label="Console users">
        @for (user of list; track user.name) {
          <li class="panel">
            <div>
              <div class="who">
                <strong>{{ user.name }}</strong>
                @if (user.name === me()) {
                  <span class="badge">you</span>
                }
              </div>
              <p class="details muted">
                Made {{ ago(user.created, now()) }} {{ madeBy(user) }}; password set
                {{ ago(user.changed, now()) }};
                {{
                  user.last_login ? 'last login ' + ago(user.last_login, now()) : 'never logged in'
                }}
              </p>
            </div>
            <div class="actions">
              @if (user.name === me()) {
                <a class="btn btn-ghost btn-sm" routerLink="/account">Change password</a>
              } @else if (removing() === user.name) {
                <span>Remove {{ user.name }}? They won't be able to log in.</span>
                <button
                  class="btn btn-sm danger"
                  type="button"
                  [disabled]="busy()"
                  (click)="remove(user.name)"
                >
                  Remove
                </button>
                <button class="btn btn-ghost btn-sm" type="button" (click)="removing.set(null)">
                  Keep
                </button>
              } @else {
                <button
                  class="btn btn-ghost btn-sm"
                  type="button"
                  [disabled]="busy()"
                  (click)="startPassword(user.name)"
                >
                  New password
                </button>
                <button
                  class="btn btn-ghost btn-sm danger"
                  type="button"
                  [disabled]="busy()"
                  (click)="removing.set(user.name)"
                >
                  Remove
                </button>
              }
            </div>
            @if (resetting() === user.name) {
              <form (submit)="$event.preventDefault(); savePassword(user.name)">
                <label class="field">
                  <span class="label"
                    >A new password for {{ user.name }}, {{ min }} or more characters</span
                  >
                  <input
                    type="password"
                    autocomplete="new-password"
                    [value]="password()"
                    (input)="password.set(value($event))"
                  />
                </label>
                <p class="muted">They're logged out, and log in again with this one.</p>
                <div class="actions">
                  <button class="btn btn-sm" type="submit" [disabled]="busy() || !password()">
                    Set password
                  </button>
                  <button class="btn btn-ghost btn-sm" type="button" (click)="resetting.set(null)">
                    Cancel
                  </button>
                </div>
              </form>
            }
          </li>
        }
      </ul>
    } @else if (!problem()) {
      <p class="loading" role="status"><span class="spinner"></span> Reading the console users…</p>
    }

    <section class="panel narrow" aria-labelledby="add-title">
      <h2 id="add-title"><mc-icon name="users" /> Add a console user</h2>
      <form (submit)="$event.preventDefault(); add()">
        <label class="field">
          <span class="label">Name: letters, digits, dots, dashes or underscores</span>
          <input
            autocomplete="off"
            autocapitalize="none"
            spellcheck="false"
            [value]="newName()"
            (input)="newName.set(value($event))"
          />
        </label>
        <label class="field">
          <span class="label">Password, {{ min }} or more characters</span>
          <input
            type="password"
            autocomplete="new-password"
            [value]="newPassword()"
            (input)="newPassword.set(value($event))"
          />
        </label>
        <p class="muted">Tell them their password in person; they can change it on Account.</p>
        <div class="actions">
          <button class="btn" type="submit" [disabled]="busy() || !newName() || !newPassword()">
            Add
          </button>
        </div>
      </form>
    </section>
  `,
})
export class ConsoleUsers {
  private readonly api = inject(Api);
  protected readonly users = signal<ConsoleUser[] | null>(null);
  protected readonly problem = signal<string | null>(null);
  protected readonly done = signal<string | null>(null);
  protected readonly busy = signal(false);
  /** Whose removal is being asked about, or whose new password is being typed. */
  protected readonly removing = signal<string | null>(null);
  protected readonly resetting = signal<string | null>(null);
  protected readonly password = signal('');
  protected readonly newName = signal('');
  protected readonly newPassword = signal('');
  protected readonly now = signal(Date.now() / 1000);
  protected readonly min = PASSWORD_MIN;
  protected readonly ago = ago;
  /** The console user this is, or null for the console on the node's computer. */
  protected readonly me = computed(() => this.api.me()?.user ?? null);

  constructor() {
    this.load();
  }

  load(): void {
    this.api.consoleUsers().subscribe({
      next: (users) => {
        this.now.set(Date.now() / 1000);
        this.users.set(users);
        this.problem.set(null);
      },
      error: (error) =>
        this.problem.set(apiError(error, "can't read the console users: is the bot running?")),
    });
  }

  protected value(event: Event): string {
    return (event.target as HTMLInputElement).value;
  }

  protected madeBy(user: ConsoleUser): string {
    if (user.created_by === 'node') {
      return "on the node's computer";
    }
    return user.created_by === 'console' ? "from the node's console" : `by ${user.created_by}`;
  }

  protected startPassword(name: string): void {
    this.removing.set(null);
    this.password.set('');
    this.resetting.set(name);
  }

  /** Runs a change, then says so and reads the list again; or says why not. */
  private change(
    request: ReturnType<Api['addConsoleUser']> | ReturnType<Api['removeConsoleUser']>,
    said: string,
    after: () => void = () => undefined,
  ): void {
    this.busy.set(true);
    this.done.set(null);
    this.problem.set(null);
    request.subscribe({
      next: () => {
        this.busy.set(false);
        this.done.set(said);
        after();
        this.load();
      },
      error: (error) => {
        this.busy.set(false);
        this.problem.set(apiError(error, "can't change it: is the bot running?"));
      },
    });
  }

  protected add(): void {
    if (this.newPassword().length < PASSWORD_MIN) {
      this.problem.set(`a password is ${PASSWORD_MIN} or more characters`);
      return;
    }
    const name = this.newName().trim().toLowerCase();
    this.change(this.api.addConsoleUser(name, this.newPassword()), `Added ${name}.`, () => {
      this.newName.set('');
      this.newPassword.set('');
    });
  }

  protected savePassword(name: string): void {
    if (this.password().length < PASSWORD_MIN) {
      this.problem.set(`a password is ${PASSWORD_MIN} or more characters`);
      return;
    }
    this.change(
      this.api.setConsoleUserPassword(name, this.password()),
      `New password for ${name}; they've been logged out.`,
      () => {
        this.resetting.set(null);
        this.password.set('');
      },
    );
  }

  protected remove(name: string): void {
    this.change(this.api.removeConsoleUser(name), `Removed ${name}.`, () =>
      this.removing.set(null),
    );
  }
}
