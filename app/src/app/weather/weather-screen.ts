import { DatePipe, NgTemplateOutlet } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';

import { Icon } from '../icon';
import { NeedsNode } from '../node/needs-node';
import { NodeLink } from '../node/node-link';
import { parseWx, Wx } from '../node/replies';
import { StepLine } from '../node/step-line';
import { AreaWeather } from './area-weather';

/**
 * The Weather tab: a card for each county the node watches (area), with its
 * last report from the node. Favorites (kept on the phone) come first and
 * load by themselves; with any, the other counties wait under Show more, to
 * be loaded one at a time, as each is a message over the mesh. Below, the
 * weather for any other zipcode or county (wx).
 */
@Component({
  selector: 'mc-weather',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, Icon, NeedsNode, NgTemplateOutlet, StepLine],
  styles: `
    .panel {
      display: grid;
      gap: 12px;
    }
    h2,
    p {
      margin: 0;
    }
    .cards {
      display: grid;
      /* Two across on a tablet. */
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      align-items: start;
      gap: 12px;
    }
    .card {
      display: grid;
      gap: 8px;
    }
    .card-head {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .card-head h2 {
      flex: 1;
    }
    .star {
      padding: 4px;
      border: 0;
      background: none;
      color: var(--muted);
      font-size: 1.3rem;
      cursor: pointer;
    }
    .star[aria-pressed='true'] {
      color: var(--orange);
    }
    .report {
      display: grid;
      gap: 6px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .report li {
      padding: 6px 10px;
      border-left: 3px solid var(--sky);
      background: var(--ink-3);
    }
    .report li.alert {
      border-left-color: var(--orange);
      color: var(--orange);
      font-weight: 600;
    }
    .got {
      color: var(--muted);
      font-size: 0.8rem;
    }
  `,
  template: `
    <h1><mc-icon name="cloud" /> Weather</h1>

    <mc-needs-node />

    @if (link.exchange(); as ex) {
      @if (ex.step !== 'answered') {
        <mc-step-line [exchange]="ex" />
      }
    }

    @if (!area.counties().length) {
      <section class="panel">
        <p class="muted">
          The weather now in each county the node watches, from its latest reports.
        </p>
        <div class="actions">
          <button
            class="btn btn-sm"
            type="button"
            [disabled]="!link.ready()"
            (click)="area.loadCounties()"
          >
            Get the counties
          </button>
        </div>
      </section>
    }
    @if (area.said(); as said) {
      <p class="said">{{ said }}</p>
    }

    @if (favorites().length) {
      <div class="cards favorites">
        @for (county of favorites(); track county) {
          <ng-container *ngTemplateOutlet="card; context: { $implicit: county }" />
        }
      </div>
      @if (others().length) {
        <details class="panel accordion more">
          <summary>
            <h2>Show more ({{ others().length }})</h2>
          </summary>
          <div class="accordion-body cards">
            @for (county of others(); track county) {
              <ng-container *ngTemplateOutlet="card; context: { $implicit: county }" />
            }
          </div>
        </details>
      }
    } @else if (area.counties().length) {
      <p class="muted">Star a county to see it first, loaded each time you open Weather.</p>
      <div class="cards all">
        @for (county of area.counties(); track county) {
          <ng-container *ngTemplateOutlet="card; context: { $implicit: county }" />
        }
      </div>
    }

    <section class="panel lookup">
      <h2>Another place</h2>
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
          Look it up
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
      @if (area.counties().length) {
        <div class="actions">
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            [disabled]="!link.ready()"
            (click)="area.loadCounties()"
          >
            Get the node's counties again
          </button>
        </div>
      }
    </section>

    <ng-template #card let-county>
      <section class="panel card" [attr.data-county]="county">
        <div class="card-head">
          <h2>{{ county }}</h2>
          <button
            class="star"
            type="button"
            [attr.aria-pressed]="area.isFavorite(county)"
            [attr.aria-label]="(area.isFavorite(county) ? 'Unfavorite ' : 'Favorite ') + county"
            (click)="area.toggleFavorite(county)"
          >
            <mc-icon [name]="area.isFavorite(county) ? 'star-filled' : 'star'" />
          </button>
        </div>
        @if (area.cards()[county]; as c) {
          @if (c.lines) {
            <ul class="report">
              @for (line of c.lines; track $index) {
                <li [class.alert]="$first && c.alert">{{ line }}</li>
              }
            </ul>
            <span class="got">Got it {{ c.at | date: 'h:mm a' }}</span>
          }
          @if (c.said) {
            <p class="said">{{ c.said }}</p>
          }
        }
        <div class="actions">
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            [disabled]="!link.ready() || area.cards()[county]?.loading"
            (click)="area.load(county)"
          >
            {{ area.cards()[county]?.lines ? 'Update' : 'Get the weather' }}
          </button>
        </div>
      </section>
    </ng-template>
  `,
})
export class WeatherScreen {
  protected readonly link = inject(NodeLink);
  protected readonly area = inject(AreaWeather);

  /** The favorites still watched, in the order they were starred. */
  protected readonly favorites = computed(() =>
    this.area.favorites().filter((f) => this.area.counties().includes(f)),
  );
  protected readonly others = computed(() =>
    this.area.counties().filter((c) => !this.area.favorites().includes(c)),
  );

  protected readonly where = signal('');
  protected readonly wx = signal<Wx | null>(null);
  protected readonly wxSaid = signal<string | null>(null);
  private started = false;

  constructor() {
    // Once the node can be asked: the counties if there are none yet, then the favorites.
    effect(() => {
      if (this.link.ready() && !this.started) {
        this.started = true;
        void this.start();
      }
    });
  }

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

  private async start(): Promise<void> {
    if (!this.area.counties().length) {
      await this.area.loadCounties();
    }
    await this.area.loadFavorites();
  }
}
