import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Api, Channel, CommandInfo, Contact, Contacts } from './api';
import { kindText } from './chat';
import { Icon } from './icon';
import { RadioSettings } from './radio-settings';
import { Reply, Runner } from './runner';
import { ago } from './time';

type Tab = 'settings' | 'contacts' | 'channels';

/**
 * Controlling the node rather than sending messages: the radio's advert
 * (nearby, or flooded across the mesh), a backup of the bot's data now, and
 * the radio's contacts: remove one (it asks first, as over the radio) or
 * reset the path to it. Each offered only if /api/commands has it. And the
 * radio's channel slots, to look at: what each is and what the bot posts there;
 * each opens its messages in Chat. The radio's settings (radio-settings.ts),
 * contacts and channels share a panel, one tab each.
 */
@Component({
  selector: 'mc-radio',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, RadioSettings, Reply, RouterLink],
  providers: [Runner],
  styleUrl: './radio.scss',
  templateUrl: './radio.html',
})
export class Radio {
  private readonly api = inject(Api);
  protected readonly runner = inject(Runner);
  protected readonly offered = signal<CommandInfo[] | null>(null);
  protected readonly problem = signal<string | null>(null);
  protected readonly contacts = signal<Contacts | null>(null);
  protected readonly contactsProblem = signal<string | null>(null);
  protected readonly channels = signal<Channel[] | null>(null);
  protected readonly channelsProblem = signal<string | null>(null);
  /** The slots in use; the empty ones are only counted. */
  protected readonly usedChannels = computed(() =>
    (this.channels() ?? []).filter((c) => c.kind !== 'empty'),
  );
  /** The panel's tabs; the counts come from count(). */
  protected readonly tabs = [
    { id: 'settings', label: 'Settings', icon: 'sliders' },
    { id: 'contacts', label: 'Contacts', icon: 'users' },
    { id: 'channels', label: 'Channels', icon: 'send' },
  ] as const;
  protected readonly tab = signal<Tab>('settings');
  protected readonly kindText = kindText;
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
    this.loadChannels();
  }

  loadChannels(): void {
    this.api.channels().subscribe({
      next: (channels) => {
        this.channels.set(channels);
        this.channelsProblem.set(null);
      },
      error: () => this.channelsProblem.set("can't read the radio's channels"),
    });
  }

  /** How many contacts, or channels in use, for a tab's label; null until read. */
  protected count(tab: Tab): number | null {
    if (tab === 'settings') {
      return null;
    }
    if (tab === 'contacts') {
      return this.contacts()?.contacts.length ?? null;
    }
    return this.channels() ? this.usedChannels().length : null;
  }

  /** The arrow keys move between the tabs, as in any tab list. */
  protected arrow(event: KeyboardEvent): void {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (!step) {
      return;
    }
    const ids = this.tabs.map((t) => t.id);
    const next = ids[(ids.indexOf(this.tab()) + step + ids.length) % ids.length];
    this.tab.set(next);
    const tabs = (event.target as HTMLElement).parentElement;
    tabs?.querySelector<HTMLElement>(`#${next}-tab`)?.focus();
    event.preventDefault();
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
