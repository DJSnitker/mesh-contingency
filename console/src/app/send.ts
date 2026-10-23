import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { forkJoin } from 'rxjs';

import { Api, CommandInfo, MAX_TEXT, User } from './api';
import { Icon } from './icon';
import { Reply, Runner } from './runner';

/**
 * Sending from the console: a post to a public channel (alert, comm), or a
 * message left in a user's inbox (msg, from "console"). Each offered only if
 * /api/commands has it, and each with its own reply. A box is emptied only
 * once what it held went out. The radio's controls are on the Radio page.
 */
@Component({
  selector: 'mc-send',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, Reply],
  styleUrl: './send.scss',
  templateUrl: './send.html',
})
export class Send {
  private readonly api = inject(Api);
  protected readonly posting = new Runner();
  protected readonly messaging = new Runner();
  protected readonly offered = signal<CommandInfo[] | null>(null);
  protected readonly users = signal<User[]>([]);
  protected readonly limit = signal<number | null>(null);
  protected readonly problem = signal<string | null>(null);

  /** The channel commands (alert, comm), and the one picked. */
  protected readonly channels = computed(() => (this.offered() ?? []).filter((c) => c.channel));
  protected readonly channel = signal('');
  protected readonly picked = computed(
    () => this.channels().find((c) => c.name === this.channel()) ?? this.channels()[0],
  );
  protected readonly post = signal('');

  /** Who msg can leave a message for: users, not admins without a section. */
  protected readonly recipients = computed(() => this.users().filter((u) => u.user));
  protected readonly to = signal('');
  protected readonly message = signal('');
  /** msg's text is the key, a space, then the message. */
  protected readonly messageLimit = MAX_TEXT - 65;

  constructor() {
    this.posting.onDone = (answer) => answer.ok && this.post.set('');
    this.messaging.onDone = (answer) => answer.ok && this.message.set('');
    forkJoin({
      commands: this.api.commands(),
      overview: this.api.overview(),
      users: this.api.users(),
    }).subscribe({
      next: ({ commands, overview, users }) => {
        this.offered.set(commands);
        this.limit.set(overview.channel_limit);
        this.users.set(users);
        this.problem.set(null);
      },
      error: () => this.problem.set("can't reach the bot: is it running?"),
    });
  }

  protected has(name: string): boolean {
    return (this.offered() ?? []).some((c) => c.name === name);
  }

  protected tooLong(text: string, limit: number | null): boolean {
    return limit !== null && text.length > limit;
  }

  protected canPost(): boolean {
    const text = this.post().trim();
    return !!this.picked() && !!text && !this.tooLong(text, this.limit()) && !this.posting.busy();
  }

  protected canMessage(): boolean {
    const text = this.message().trim();
    return (
      !!this.to() && !!text && !this.tooLong(text, this.messageLimit) && !this.messaging.busy()
    );
  }

  protected sendPost(): void {
    const command = this.picked();
    if (command && this.canPost()) {
      this.posting.run(command.name, this.post().trim());
    }
  }

  protected sendMessage(): void {
    if (this.canMessage()) {
      this.messaging.run('msg', `${this.to()} ${this.message().trim()}`);
    }
  }

  protected value(event: Event): string {
    return (event.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement).value;
  }
}
