import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError, EMPTY, switchMap, tap, timer } from 'rxjs';

import { Api, Area, CommandInfo, Weather } from './api';
import { Icon } from './icon';
import { Reply, Runner } from './runner';
import { ago, when } from './time';

/** How often the weather is read again (ms): the bot has new reports every 15 min. */
export const WEATHER_REFRESH_MS = 60_000;

/**
 * The Area Weather page: the weather now in each county [alerts] watches, a
 * card each, whether or not there's an alert: the bot asks the NWS every 15 min and keeps the
 * last report, so a card says how old it is and, if the last try failed,
 * why.
 */
@Component({
  selector: 'mc-area-weather',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, Reply],
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
