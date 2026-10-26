import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Api, CommandInfo, Contact, Contacts as RadioContacts } from './api';
import { ChatTabs } from './chat-tabs';
import { Icon } from './icon';
import { Reply, Runner } from './runner';
import { ago } from './time';

/**
 * Chat's Contacts tab: the radio's contacts, each one's type, whether it's a
 * user or admin, its path and when it was heard, with a filter. Message a
 * companion to chat with it as the node (dm.ts); reset the path to one, or
 * remove it (it asks first, as over the radio), if /api/commands has contact.
 */
@Component({
  selector: 'mc-contacts',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ChatTabs, Icon, Reply, RouterLink],
  providers: [Runner],
  styleUrl: './contacts.scss',
  templateUrl: './contacts.html',
})
export class Contacts {
  private readonly api = inject(Api);
  protected readonly runner = inject(Runner);
  protected readonly offered = signal<CommandInfo[] | null>(null);
  protected readonly problem = signal<string | null>(null);
  protected readonly contacts = signal<RadioContacts | null>(null);
  protected readonly contactsProblem = signal<string | null>(null);
  protected readonly filter = signal('');
  /** When the contacts were read, for "heard 5m ago". */
  protected readonly now = signal(Date.now() / 1000);
  protected readonly ago = ago;
  /** The contacts whose name, key or type has the filter's words in it. */
  protected readonly shown = computed(() => {
    const words = this.filter().toLowerCase().split(/\s+/).filter(Boolean);
    return (this.contacts()?.contacts ?? []).filter((c) => {
      const text = `${c.name ?? ''} ${c.key} ${c.type} ${this.flags(c).join(' ')}`.toLowerCase();
      return words.every((word) => text.includes(word));
    });
  });

  constructor() {
    this.runner.onDone = (answer) => {
      if (answer.command === 'contact') {
        this.loadContacts();
      }
    };
    this.api.commands().subscribe({
      next: (commands) => {
        this.offered.set(commands);
        this.problem.set(null);
      },
      error: () => this.problem.set("can't reach the bot: is it running?"),
    });
    this.loadContacts();
  }

  loadContacts(): void {
    this.api.contacts().subscribe({
      next: (contacts) => {
        this.now.set(Date.now() / 1000);
        this.contacts.set(contacts);
        this.contactsProblem.set(null);
      },
      error: () => this.contactsProblem.set("can't read the radio's contacts"),
    });
  }

  protected has(name: string): boolean {
    return (this.offered() ?? []).some((c) => c.name === name);
  }

  /** What's worth saying about a contact besides its name: its type, and if it's one of the node's people. */
  protected flags(contact: Contact): string[] {
    const flags = contact.type === 'chat' ? [] : [contact.type];
    if (contact.admin) {
      flags.push('admin');
    } else if (contact.user) {
      flags.push('user');
    }
    return flags;
  }

  protected path(contact: Contact): string {
    if (contact.hops === null) {
      return 'no path (floods)';
    }
    return contact.hops === 0 ? 'direct' : `${contact.hops} hop${contact.hops === 1 ? '' : 's'}`;
  }
}
