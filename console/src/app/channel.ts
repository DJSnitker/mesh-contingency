import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { catchError, EMPTY, forkJoin, interval, startWith, switchMap, tap } from 'rxjs';

import { Api, Channel, ChannelMessage } from './api';
import { kindText } from './chat';
import { Icon } from './icon';
import { ago, when } from './time';
import { Unread } from './unread';

/** How often a channel's messages are read again (ms). */
export const CHANNEL_REFRESH_MS = 10_000;

/**
 * One channel's thread, as a chat in the phone app: what the radio heard on
 * it since the bot started and what this node posted, oldest first, the
 * node's own on the right; read again every CHANNEL_REFRESH_MS, and marked
 * read (unread.ts) as it is. A box to post to it as this node.
 */
@Component({
  selector: 'mc-channel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, RouterLink],
  styleUrls: ['./compose.scss', './channel.scss'],
  templateUrl: './channel.html',
})
export class ChannelThread {
  private readonly api = inject(Api);
  private readonly unread = inject(Unread);

  /** The channel's slot, from the route. */
  readonly slot = input<string>();
  private readonly number = computed(() => Number(this.slot()));

  protected readonly channel = signal<Channel | null>(null);
  protected readonly limit = signal<number | null>(null);
  protected readonly problem = signal<string | null>(null);
  /** Newest last; null until read, or if the bot keeps none. */
  protected readonly lines = signal<ChannelMessage[] | null>(null);
  protected readonly keep = signal<number | null>(null);
  protected readonly read = signal(false);
  protected readonly messagesProblem = signal<string | null>(null);
  protected readonly now = signal(Date.now() / 1000);
  protected readonly ago = ago;
  protected readonly when = when;
  protected readonly kindText = kindText;

  protected readonly post = signal('');
  protected readonly posting = signal(false);
  /** What came of the last post: posted, or why not. */
  protected readonly posted = signal<{ ok: boolean; text: string } | null>(null);

  constructor() {
    toObservable(this.number)
      .pipe(
        switchMap((slot) => {
          this.lines.set(null);
          this.read.set(false);
          this.posted.set(null);
          forkJoin({
            channels: this.api.channels(),
            overview: this.api.overview(),
          }).subscribe({
            next: ({ channels, overview }) => {
              this.channel.set(channels.find((c) => c.slot === slot) ?? null);
              this.limit.set(overview.channel_limit);
              this.problem.set(null);
            },
            error: () => this.problem.set("can't reach the bot: is it running?"),
          });
          return interval(CHANNEL_REFRESH_MS).pipe(
            startWith(0),
            switchMap(() => this.messages(slot)),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe();
  }

  private messages(slot: number) {
    return this.api.channelMessages(slot).pipe(
      tap((found) => {
        this.now.set(Date.now() / 1000);
        this.keep.set(found.keep);
        this.lines.set(found.messages ? [...found.messages].reverse() : null);
        this.read.set(true);
        this.messagesProblem.set(null);
        this.unread.read(slot, found.heard ?? null);
      }),
      catchError(() => {
        this.messagesProblem.set("can't read the channel's messages");
        return EMPTY;
      }),
    );
  }

  private load(slot: number): void {
    this.messages(slot).subscribe();
  }

  /** How a message came: "direct", "2 hops", and its signal. */
  protected route(hops: number | null, snr: number | null): string {
    const parts =
      hops === null ? [] : [hops === 0 ? 'direct' : `${hops} hop${hops === 1 ? '' : 's'}`];
    if (snr !== null) {
      parts.push(`SNR ${snr} dB`);
    }
    return parts.join(' · ');
  }

  protected tooLong(text: string): boolean {
    const limit = this.limit();
    return limit !== null && text.length > limit;
  }

  protected canPost(): boolean {
    const text = this.post().trim();
    return !!this.channel() && !!text && !this.tooLong(text) && !this.posting();
  }

  /** Post the box's text; it's emptied only once it went out. */
  protected send(): void {
    if (!this.canPost()) {
      return;
    }
    const slot = this.number();
    this.posting.set(true);
    this.posted.set(null);
    this.api.postToChannel(slot, this.post().trim()).subscribe({
      next: ({ channel }) => {
        this.posting.set(false);
        this.post.set('');
        this.posted.set({ ok: true, text: `Posted to ${channel}.` });
        this.load(slot);
      },
      error: (error: HttpErrorResponse) => {
        this.posting.set(false);
        const said = typeof error.error === 'object' && error.error?.error;
        this.posted.set({
          ok: false,
          text:
            said || (error.status === 0 ? "can't reach the bot" : `the bot said ${error.status}`),
        });
      },
    });
  }

  protected value(event: Event): string {
    return (event.target as HTMLTextAreaElement).value;
  }
}
