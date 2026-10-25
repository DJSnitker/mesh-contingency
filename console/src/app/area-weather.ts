import { HttpErrorResponse } from '@angular/common/http';
import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError, EMPTY, switchMap, tap, timer } from 'rxjs';

import { Api, Area, CommandInfo, Weather } from './api';
import { Icon } from './icon';
import { Reply, Runner } from './runner';
import { ago, when } from './time';

/** How often the weather is read again (ms): the bot has new reports every 15 min. */
export const WEATHER_REFRESH_MS = 60_000;

/** Where the favorite counties are kept, in this browser. */
export const FAVORITES = 'mc.console.weather.favorites';

/** wx's answer as lines: its parts ("ALERT: ...", the rain, the temperature and wind). */
export function wxLines(messages: string[]): string[] {
  return messages
    .map((m) => m.replace(/^\(\d+\/\d+\) /, ''))
    .join(' ')
    .split(' | ')
    .map((line) => line.trim())
    .filter(Boolean);
}

/**
 * The Weather page, as the phone app's tab: the weather now in each county
 * [alerts] watches, a card each, whether or not there's an alert: the bot
 * asks the NWS every 15 min and keeps the last report, so a card says how old
 * it is and, if the last try failed, why. Favorites (starred, kept in this
 * browser) come first; with any, the other counties wait under Show more.
 * Below, the weather for any other zipcode or county (wx).
 */
@Component({
  selector: 'mc-area-weather',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, NgTemplateOutlet, Reply],
  providers: [Runner],
  styleUrl: './area-weather.scss',
  templateUrl: './area-weather.html',
})
export class AreaWeather {
  private readonly api = inject(Api);
  protected readonly runner = inject(Runner);
  protected readonly weather = signal<Weather | null>(null);
  protected readonly offered = signal<CommandInfo[]>([]);
  /** Asking before testalert, which posts on the air for everyone on the channel. */
  protected readonly confirmingTest = signal(false);
  /** The alert channel, as the alert command says it, e.g. #contingency-wx. */
  protected readonly channel = computed(
    () => this.offered().find((c) => c.name === 'alert')?.channel ?? 'the alert channel',
  );
  protected readonly problem = signal<string | null>(null);
  protected readonly favorites = signal<string[]>(this.stored());
  /** The favorites still watched, in the order they were starred. */
  protected readonly starred = computed(() => {
    const areas = this.weather()?.areas ?? [];
    return this.favorites()
      .map((county) => areas.find((a) => a.county === county))
      .filter((a): a is Area => !!a);
  });
  protected readonly others = computed(() =>
    (this.weather()?.areas ?? []).filter((a) => !this.favorites().includes(a.county)),
  );

  protected readonly where = signal('');
  protected readonly looking = signal(false);
  /** The last wx answer: its lines, or what went wrong. */
  protected readonly wx = signal<{ lines: string[]; alert: boolean } | null>(null);
  protected readonly wxSaid = signal<string | null>(null);
  protected readonly ago = ago;
  protected readonly when = when;

  constructor() {
    this.api.commands().subscribe({
      next: (commands) => this.offered.set(commands),
      error: () => undefined, // the weather's own problem says the bot can't be reached
    });
    timer(0, WEATHER_REFRESH_MS)
      .pipe(
        switchMap(() =>
          this.api.weather().pipe(
            tap(() => this.problem.set(null)),
            catchError((error: HttpErrorResponse) => {
              this.problem.set(
                error.status === 0 ? "can't reach the bot" : `the bot said ${error.status}`,
              );
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(),
      )
      .subscribe((weather) => this.weather.set(weather));
  }

  protected isFavorite(county: string): boolean {
    return this.favorites().includes(county);
  }

  /** Star a county, or not; favorites keep the order they're starred in. */
  protected toggleFavorite(county: string): void {
    this.favorites.update((favorites) =>
      favorites.includes(county) ? favorites.filter((f) => f !== county) : [...favorites, county],
    );
    try {
      localStorage.setItem(FAVORITES, JSON.stringify(this.favorites()));
    } catch {
      // Not kept (a private window): starred until the page closes.
    }
  }

  private stored(): string[] {
    try {
      const stored = JSON.parse(localStorage.getItem(FAVORITES) ?? '[]');
      return Array.isArray(stored) ? stored.filter((s) => typeof s === 'string') : [];
    } catch {
      return [];
    }
  }

  /** The weather for any zipcode or county, as wx answers it. */
  protected lookUp(): void {
    const where = this.where().trim();
    if (!where || this.looking()) {
      return;
    }
    this.looking.set(true);
    this.wx.set(null);
    this.wxSaid.set(null);
    this.api.run('wx', where).subscribe({
      next: (answer) => {
        this.looking.set(false);
        const lines = answer.ok ? wxLines(answer.messages) : [];
        if (lines.length) {
          this.wx.set({ lines, alert: lines[0].includes('ALERT:') });
        } else {
          this.wxSaid.set(answer.messages.join(' ') || 'wx: no answer');
        }
      },
      error: (error: HttpErrorResponse) => {
        this.looking.set(false);
        const said = typeof error.error === 'object' && error.error?.error;
        this.wxSaid.set(said || "can't reach the bot: is it running?");
      },
    });
  }

  protected value(event: Event): string {
    return (event.target as HTMLInputElement).value;
  }

  protected has(name: string): boolean {
    return this.offered().some((c) => c.name === name);
  }

  protected postTest(): void {
    this.confirmingTest.set(false);
    this.runner.run('testalert');
  }

  protected round(value: number | null | undefined): string {
    return value == null ? '–' : `${Math.round(value)}`;
  }

  /** "SE 7 mph, gusts 15", "calm", or null if the station gave no wind. */
  protected wind(area: Area): string | null {
    if (area.wind_mph == null) {
      return null;
    }
    if (Math.round(area.wind_mph) === 0) {
      return 'calm';
    }
    const gusts = area.gust_mph ? `, gusts ${Math.round(area.gust_mph)}` : '';
    return `${area.wind_dir ? area.wind_dir + ' ' : ''}${Math.round(area.wind_mph)} mph${gusts}`;
  }
}
