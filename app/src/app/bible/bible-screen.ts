import { ChangeDetectionStrategy, Component, effect, inject, signal } from '@angular/core';

import { Icon } from '../icon';
import { NeedsNode } from '../node/needs-node';
import { NodeLink } from '../node/node-link';
import { parseVerse } from '../node/replies';
import { StepLine } from '../node/step-line';

/** Where the verse of the day is kept on the phone, with its date. */
export const TODAY = 'mc.bible.today';

/** A passage, as the screen shows it. */
interface Passage {
  reference: string;
  text: string;
}

/** Today's date on the phone, as YYYY-MM-DD. */
function today(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

/**
 * The Bible tab: the verse of the day (verse alone), asked for once a day
 * and kept on the phone until the next; and any verse or passage looked up
 * (verse <reference>). The node has the Bible (BSB) with it, so neither
 * needs the internet.
 */
@Component({
  selector: 'mc-bible',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, NeedsNode, StepLine],
  styles: `
    .panel {
      display: grid;
      gap: 12px;
    }
    h2,
    p {
      margin: 0;
    }
    .passage {
      margin: 0;
      padding: 10px 12px;
      border-left: 3px solid var(--sky);
      background: var(--ink-3);
      line-height: 1.5;
    }
    .passage strong {
      display: block;
      margin-bottom: 4px;
    }
  `,
  template: `
    <h1><mc-icon name="book" /> Bible</h1>

    <mc-needs-node />

    @if (link.exchange(); as ex) {
      @if (ex.step !== 'answered') {
        <mc-step-line [exchange]="ex" />
      }
    }

    <section class="panel today">
      <h2>Verse of the day</h2>
      @if (verseOfDay(); as v) {
        <blockquote class="passage">
          <strong>{{ v.reference }}</strong
          >{{ v.text }}
        </blockquote>
      } @else {
        <div class="actions">
          <button class="btn btn-sm" type="button" [disabled]="!link.ready()" (click)="getToday()">
            Get the verse of the day
          </button>
        </div>
      }
      @if (todaySaid(); as said) {
        <p class="said">{{ said }}</p>
      }
    </section>

    <section class="panel lookup">
      <h2>Look up a verse</h2>
      <label class="field">
        A reference (John 3:16, Psalm 23:1-4)
        <input
          type="text"
          name="reference"
          autocomplete="off"
          [value]="reference()"
          (input)="reference.set(value($event))"
        />
      </label>
      <div class="actions">
        <button
          class="btn btn-sm"
          type="button"
          [disabled]="!link.ready() || !reference().trim()"
          (click)="lookUp()"
        >
          Look it up
        </button>
      </div>
      @if (found(); as v) {
        <blockquote class="passage found">
          <strong>{{ v.reference }}</strong
          >{{ v.text }}
        </blockquote>
      }
      @if (lookupSaid(); as said) {
        <p class="said">{{ said }}</p>
      }
    </section>
  `,
})
export class BibleScreen {
  protected readonly link = inject(NodeLink);

  protected readonly verseOfDay = signal<Passage | null>(this.stored());
  protected readonly todaySaid = signal<string | null>(null);
  protected readonly reference = signal('');
  protected readonly found = signal<Passage | null>(null);
  protected readonly lookupSaid = signal<string | null>(null);
  private asked = false;

  constructor() {
    // Today's verse, once the node can be asked, unless it's kept from earlier today.
    effect(() => {
      if (this.link.ready() && !this.verseOfDay() && !this.asked) {
        this.asked = true;
        void this.getToday();
      }
    });
  }

  protected value(event: Event): string {
    return (event.target as HTMLInputElement).value;
  }

  protected async getToday(): Promise<void> {
    this.todaySaid.set(null);
    const passage = await this.ask('verse', this.todaySaid);
    if (passage) {
      this.verseOfDay.set(passage);
      try {
        localStorage.setItem(TODAY, JSON.stringify({ date: today(), ...passage }));
      } catch {
        // Asked for again next time, then.
      }
    }
  }

  protected async lookUp(): Promise<void> {
    this.found.set(null);
    this.lookupSaid.set(null);
    this.found.set(await this.ask(`verse ${this.reference().trim()}`, this.lookupSaid));
  }

  /** Ask the node for a passage; what it says instead goes to `said`. */
  private async ask(
    command: string,
    said: ReturnType<typeof signal<string | null>>,
  ): Promise<Passage | null> {
    const exchange = await this.link.ask(command, { one: true });
    if (!exchange.text) {
      return null;
    }
    const result = parseVerse(exchange.text);
    if (result?.outcome === 'found') {
      return { reference: result.reference, text: result.text };
    }
    said.set(exchange.text);
    return null;
  }

  /** The verse of the day kept from earlier today, if any. */
  private stored(): Passage | null {
    try {
      const kept = JSON.parse(localStorage.getItem(TODAY) ?? 'null');
      return kept?.date === today() && kept.reference && kept.text
        ? { reference: kept.reference, text: kept.text }
        : null;
    } catch {
      return null;
    }
  }
}
