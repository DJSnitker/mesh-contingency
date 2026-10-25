import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Api, Channel } from './api';
import { Icon } from './icon';
import { ago } from './time';

/** What a kind of channel means for who can read it. */
export function kindText(kind: Channel['kind']): string {
  return {
    public: 'the usual Public channel: everyone',
    hashtag: 'hashtag: anyone who adds the same name',
    private: 'private: only radios given its key',
    empty: 'empty',
  }[kind];
}

/**
 * Chat, as the phone app's: the radio's channels, each opening its thread
 * (channel.ts), the ones heard on most recently first. Direct messages come
 * in a later version.
 */
@Component({
  selector: 'mc-chat',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, RouterLink],
  styles: `
    :host {
      display: grid;
      gap: 20px;
    }
    .panel {
      display: grid;
      gap: 12px;
    }
    h2 .muted {
      margin-left: auto;
      font-family: var(--body);
      font-size: 0.85rem;
      font-weight: 400;
      text-transform: none;
    }
    p {
      margin: 0;
    }
    .badge {
      margin-left: 6px;
    }
  `,
  template: `
    <header class="title">
      <div>
        <h1>Chat</h1>
        <p class="muted">The radio's channels: what was said on each since the bot started.</p>
      </div>
      @if (problem()) {
        <p class="problem" role="alert"><mc-icon name="alert" /> {{ problem() }}</p>
      }
    </header>

    <section class="panel" aria-labelledby="channels-title">
      <h2 id="channels-title">
        <mc-icon name="send" /> Channels
        @if (channels(); as all) {
          <span class="muted">{{ used().length }} of {{ all.length }} slots in use</span>
        }
      </h2>
      @if (channels()) {
        <ul class="rows" aria-label="The radio's channels">
          @for (channel of used(); track channel.slot) {
            <li>
              <a [routerLink]="['/chat', 'channel', channel.slot]">
                <span class="name"
                  >{{ channel.name || '(no name)' }}
                  @for (use of channel.uses; track use) {
                    <span class="badge">{{ use }}</span>
                  }
                </span>
                @if (channel.last) {
                  <span class="side">{{ ago(channel.last, now()) }}</span>
                }
                <span class="sub">
                  {{ kindText(channel.kind) }}
                  @if (channel.messages) {
                    · {{ channel.messages }} message{{ channel.messages === 1 ? '' : 's' }}
                  }
                </span>
              </a>
            </li>
          } @empty {
            <li class="muted">No channels on the radio.</li>
          }
        </ul>
        <p class="muted">
          The bot adds the channels it posts to itself; to add or change others, use the MeshCore
          app. Their keys aren't shown here.
        </p>
      } @else if (!problem()) {
        <p class="loading" role="status">
          <span class="spinner"></span> Reading the radio's channels…
        </p>
      }
    </section>
  `,
})
export class Chat {
  private readonly api = inject(Api);
  protected readonly channels = signal<Channel[] | null>(null);
  protected readonly problem = signal<string | null>(null);
  protected readonly now = signal(Date.now() / 1000);
  protected readonly ago = ago;
  protected readonly kindText = kindText;
  /** The slots in use, heard on most recently first; then the rest by slot. */
  protected readonly used = computed(() =>
    (this.channels() ?? [])
      .filter((c) => c.kind !== 'empty')
      .sort((a, b) => (b.last ?? 0) - (a.last ?? 0) || a.slot - b.slot),
  );

  constructor() {
    this.api.channels().subscribe({
      next: (channels) => {
        this.now.set(Date.now() / 1000);
        this.channels.set(channels);
        this.problem.set(null);
      },
      error: () => this.problem.set("can't read the radio's channels"),
    });
  }
}
