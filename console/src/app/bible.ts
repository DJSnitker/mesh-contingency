import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal, WritableSignal } from '@angular/core';

import { Answer, Api } from './api';
import { Icon } from './icon';

/** A passage, as verse answers: its reference, then its text. */
export interface Passage {
  reference: string;
  text: string;
}

/**
 * verse's answer as one passage: its messages joined (a long one comes in
 * numbered parts, "(1/2) ..."), the reference split from the text; null for
 * an answer that isn't one (an error, "verse: not found").
 */
export function passage(answer: Answer): Passage | null {
  if (!answer.ok) {
    return null;
  }
  const text = answer.messages.map((m) => m.replace(/^\(\d+\/\d+\) /, '')).join(' ');
  const found = /^(.+? \d+:\d+(?:-\d+)?) ([\s\S]+)$/.exec(text);
  return found ? { reference: found[1], text: found[2] } : null;
}

/**
 * The Bible, as the phone app's tab: the verse of the day (verse alone) and
 * any verse or passage looked up (verse <reference>). The node has the
 * Bible (BSB) with it, so neither needs the internet.
 */
@Component({
  selector: 'mc-bible',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon],
  styleUrl: './compose.scss',
  styles: `
    .passage {
      margin: 0;
      padding: 10px 14px;
      border-left: 3px solid var(--sky);
      background: var(--ink-3);
      line-height: 1.6;
    }
    .passage strong {
      display: block;
      margin-bottom: 4px;
    }
  `,
  template: `
    <header class="title">
      <div>
        <h1>Bible</h1>
        <p class="muted">The Berean Standard Bible, kept on the node.</p>
      </div>
    </header>

    <section class="panel today" aria-labelledby="today-title">
      <h2 id="today-title"><mc-icon name="book" /> Verse of the day</h2>
      @if (today(); as v) {
        <blockquote class="passage">
          <strong>{{ v.reference }}</strong
          >{{ v.text }}
        </blockquote>
      } @else if (todaySaid(); as said) {
        <p class="problem" role="alert"><mc-icon name="alert" /> {{ said }}</p>
      } @else {
        <p class="loading" role="status"><span class="spinner"></span> Reading today's verse…</p>
      }
    </section>

    <section class="panel lookup" aria-labelledby="lookup-title">
      <h2 id="lookup-title"><mc-icon name="list" /> Look up a verse</h2>
      <div class="row look">
        <label class="field">
          <span class="sr-only">A reference</span>
          <input
            name="reference"
            placeholder="John 3:16, Psalm 23:1-4"
            autocomplete="off"
            [value]="reference()"
            (input)="reference.set(value($event))"
            (keydown.enter)="lookUp()"
          />
        </label>
        <button
          class="btn btn-ghost"
          type="button"
          [disabled]="!reference().trim() || looking()"
          (click)="lookUp()"
        >
          @if (looking()) {
            <span class="spinner small"></span>
          }
          Look it up
        </button>
      </div>
      @if (found(); as v) {
        <blockquote class="passage found">
          <strong>{{ v.reference }}</strong
          >{{ v.text }}
        </blockquote>
      }
      @if (foundSaid(); as said) {
        <p class="problem" role="alert"><mc-icon name="alert" /> {{ said }}</p>
      }
    </section>
  `,
})
export class Bible {
  private readonly api = inject(Api);
  protected readonly today = signal<Passage | null>(null);
  protected readonly todaySaid = signal<string | null>(null);
  protected readonly reference = signal('');
  protected readonly looking = signal(false);
  protected readonly found = signal<Passage | null>(null);
  protected readonly foundSaid = signal<string | null>(null);

  constructor() {
    this.ask('', this.today, this.todaySaid);
  }

  protected lookUp(): void {
    const reference = this.reference().trim();
    if (!reference || this.looking()) {
      return;
    }
    this.looking.set(true);
    this.found.set(null);
    this.foundSaid.set(null);
    this.ask(reference, this.found, this.foundSaid, () => this.looking.set(false));
  }

  private ask(
    text: string,
    into: WritableSignal<Passage | null>,
    said: WritableSignal<string | null>,
    done: () => void = () => undefined,
  ): void {
    this.api.run('verse', text).subscribe({
      next: (answer) => {
        const found = passage(answer);
        into.set(found);
        said.set(found ? null : answer.messages.join(' ') || 'verse: no answer');
        done();
      },
      error: (error: HttpErrorResponse) => {
        const message = typeof error.error === 'object' && error.error?.error;
        said.set(message || "can't reach the bot: is it running?");
        done();
      },
    });
  }

  protected value(event: Event): string {
    return (event.target as HTMLInputElement).value;
  }
}
