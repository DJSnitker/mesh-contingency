import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { forkJoin, timer } from 'rxjs';

import { Api, CommandInfo, Mailbox as Box, MAX_TEXT, User } from './api';
import { REFRESH_MS } from './dashboard';
import { Icon } from './icon';
import { Reply, Runner } from './runner';
import { ago } from './time';

/**
 * The node's mail, as the phone app's Mailbox: the messages waiting on the
 * node (for whom, from whom, when, read or not, sealed or not, never what they
 * say: that's for the recipient, with inbox over the radio and their
 * passphrase, if sealed), and leaving a message for a user (msg, from
 * "console"), offered only if /api/commands has it. The box is emptied only
 * once the message went out.
 */
@Component({
  selector: 'mc-mailbox',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, Reply],
  styleUrls: ['./records.scss', './compose.scss'],
  templateUrl: './mailbox.html',
})
export class Mailbox {
  private readonly api = inject(Api);
  protected readonly messaging = new Runner();
  protected readonly boxes = signal<Box[] | null>(null);
  protected readonly problem = signal<string | null>(null);
  protected readonly now = signal(Date.now() / 1000);
  protected readonly ago = ago;
  protected readonly total = computed(() =>
    (this.boxes() ?? []).reduce((sum, box) => sum + box.messages.length, 0),
  );

  protected readonly offered = signal<CommandInfo[] | null>(null);
  protected readonly users = signal<User[]>([]);
  /** Who msg can leave a message for: users, not admins without a section. */
  protected readonly recipients = computed(() => this.users().filter((u) => u.user));
  protected readonly to = signal('');
  protected readonly message = signal('');
  /** msg's text is the key, a space, then the message. */
  protected readonly messageLimit = MAX_TEXT - 65;

  constructor() {
    this.messaging.onDone = (answer) => {
      if (answer.ok) {
        this.message.set('');
        this.load();
      }
    };
    forkJoin({ commands: this.api.commands(), users: this.api.users() }).subscribe({
      next: ({ commands, users }) => {
        this.offered.set(commands);
        this.users.set(users);
      },
      error: () => this.problem.set("can't reach the bot: is it running?"),
    });
    timer(0, REFRESH_MS)
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.load());
  }

  load(): void {
    this.api.inbox().subscribe({
      next: (boxes) => {
        this.now.set(Date.now() / 1000);
        this.boxes.set(boxes);
        this.problem.set(null);
      },
      error: () => this.problem.set("can't read the inbox: is the bot running?"),
    });
  }

  protected unread(box: Box): number {
    return box.messages.filter((m) => !m.read).length;
  }

  protected has(name: string): boolean {
    return (this.offered() ?? []).some((c) => c.name === name);
  }

  protected tooLong(text: string, limit: number): boolean {
    return text.length > limit;
  }

  protected canMessage(): boolean {
    const text = this.message().trim();
    return (
      !!this.to() && !!text && !this.tooLong(text, this.messageLimit) && !this.messaging.busy()
    );
  }

  protected sendMessage(): void {
    if (this.canMessage()) {
      this.messaging.run('msg', `${this.to()} ${this.message().trim()}`);
    }
  }

  protected value(event: Event): string {
    return (event.target as HTMLTextAreaElement | HTMLSelectElement).value;
  }
}
