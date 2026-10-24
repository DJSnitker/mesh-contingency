import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';

import { Icon } from '../icon';
import { NeedsNode } from '../node/needs-node';
import { NodeLink } from '../node/node-link';
import { parseVerse, parseWx, Verse, Wx } from '../node/replies';
import { StepLine } from '../node/step-line';

/**
 * The Weather and verse screen: the weather and alerts for a zipcode or
 * county (wx), fetched by the node when it has the internet; and a Bible
 * verse (verse), which the node has with it.
 */
@Component({
  selector: 'mc-weather',
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
    .report {
      display: grid;
      gap: 6px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .report li {
      padding: 8px 12px;
      border-left: 3px solid var(--sky);
      background: var(--ink-3);
    }
    .report li.alert {
      border-left-color: var(--orange);
      color: var(--orange);
      font-weight: 600;
    }
    .passage {
      margin: 0;
      padding: 10px 12px;
      border-left: 3px solid var(--sky);
      background: var(--ink-3);
    }
    .passage strong {
      display: block;
    }
  `,
  template: `
    <h1><mc-icon name="cloud" /> Weather and verse</h1>

    <mc-needs-node />

    @if (link.exchange(); as ex) {
      @if (ex.step !== 'answered') {
        <mc-step-line [exchange]="ex" />
      }
    }

    <section class="panel weather">
      <h2>Weather</h2>
      <label class="field">
        A zipcode, or a county and state (Taylor, TX)
        <input
          type="text"
          name="where"
          autocomplete="postal-code"
          [value]="where()"
          (input)="where.set(value($event))"
        />
      </label>
      <div class="actions">
        <button
          class="btn btn-sm"
          type="button"
          [disabled]="!link.ready() || !where().trim()"
          (click)="getWeather()"
        >
          Get the weather
        </button>
      </div>
      @if (wx(); as report) {
        @if (report.outcome === 'found') {
          <ul class="report">
            @for (line of report.lines; track $index) {
              <li [class.alert]="$first && report.alert">{{ line }}</li>
            }
          </ul>
        }
      }
      @if (wxSaid(); as said) {
        <p class="said">{{ said }}</p>
      }
    </section>

    <section class="panel verse">
      <h2>A verse</h2>
      <label class="field">
        A reference (John 3:16); empty for the verse of the day
        <input
          type="text"
          name="reference"
          autocomplete="off"
          [value]="reference()"
          (input)="reference.set(value($event))"
        />
      </label>
      <div class="actions">
        <button class="btn btn-sm" type="button" [disabled]="!link.ready()" (click)="getVerse()">
          Get the verse
        </button>
      </div>
      @if (verse(); as found) {
        @if (found.outcome === 'found') {
          <p class="passage">
            <strong>{{ found.reference }}</strong> {{ found.text }}
          </p>
        }
      }
      @if (verseSaid(); as said) {
        <p class="said">{{ said }}</p>
      }
    </section>
  `,
})
export class WeatherScreen {
  protected readonly link = inject(NodeLink);

  protected readonly where = signal('');
  protected readonly wx = signal<Wx | null>(null);
  protected readonly wxSaid = signal<string | null>(null);

  protected readonly reference = signal('');
  protected readonly verse = signal<Verse | null>(null);
  protected readonly verseSaid = signal<string | null>(null);

  protected value(event: Event): string {
    return (event.target as HTMLInputElement).value;
  }

  protected async getWeather(): Promise<void> {
    this.wx.set(null);
    this.wxSaid.set(null);
    const exchange = await this.link.ask(`wx ${this.where().trim()}`, { one: true });
    if (!exchange.text) {
      return;
    }
    const report = parseWx(exchange.text);
    this.wx.set(report?.outcome === 'found' ? report : null);
    this.wxSaid.set(report?.outcome === 'found' ? null : exchange.text);
  }

  protected async getVerse(): Promise<void> {
    this.verse.set(null);
    this.verseSaid.set(null);
    const reference = this.reference().trim();
    const exchange = await this.link.ask(reference ? `verse ${reference}` : 'verse', { one: true });
    if (!exchange.text) {
      return;
    }
    const found = parseVerse(exchange.text);
    this.verse.set(found?.outcome === 'found' ? found : null);
    this.verseSaid.set(found?.outcome === 'found' ? null : exchange.text);
  }
}
