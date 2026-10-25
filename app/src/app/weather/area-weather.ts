import { inject, Injectable, signal } from '@angular/core';

import { NodeLink } from '../node/node-link';
import { parseArea } from '../node/replies';

/** Where the watched counties and the favorites are kept on the phone. */
export const COUNTIES = 'mc.weather.counties';
export const FAVORITES = 'mc.weather.favorites';
/** A report this new isn't asked for again when the tab opens (ms): the bot has new ones every 15 min. */
export const FRESH_MS = 15 * 60_000;

/** A county's card: its last report, or why there isn't one. */
export interface Card {
  lines: string[] | null;
  alert: boolean;
  /** When the app got it. */
  at: number | null;
  /** What the node said instead, when it had no report. */
  said: string | null;
  loading: boolean;
}

/**
 * The area's weather for the Weather tab: the counties the node watches
 * (area), each county's report (area <county>), and the user's favorites.
 * The counties and favorites are kept on the phone; the reports while the
 * app is open, so switching tabs doesn't ask the mesh again.
 */
@Injectable({ providedIn: 'root' })
export class AreaWeather {
  private readonly link = inject(NodeLink);

  readonly counties = signal<string[]>(this.stored(COUNTIES));
  readonly favorites = signal<string[]>(this.stored(FAVORITES));
  readonly cards = signal<Record<string, Card>>({});
  /** What the node said when the counties were asked for and it didn't list them. */
  readonly said = signal<string | null>(null);

  /** Ask the node for the counties it watches. */
  async loadCounties(): Promise<void> {
    this.said.set(null);
    const exchange = await this.link.ask('area', { one: true });
    if (!exchange.text) {
      return;
    }
    const result = parseArea(exchange.text);
    if (result?.outcome === 'counties') {
      this.counties.set(result.counties);
      this.save(COUNTIES, result.counties);
      // A favorite no longer watched goes.
      this.favorites.update((favorites) => favorites.filter((f) => result.counties.includes(f)));
      this.save(FAVORITES, this.favorites());
    } else {
      this.said.set(exchange.text);
    }
  }

  /** Ask the node for a county's report. */
  async load(county: string): Promise<void> {
    this.update(county, { loading: true });
    const exchange = await this.link.ask(`area ${county}`, { one: true });
    if (!exchange.text) {
      this.update(county, {
        loading: false,
        said: exchange.step === 'no answer' ? 'The node didn’t answer.' : null,
      });
      return;
    }
    const result = parseArea(exchange.text, county);
    if (result?.outcome === 'report') {
      this.update(county, {
        lines: result.lines,
        alert: result.alert,
        at: Date.now(),
        said: null,
        loading: false,
      });
    } else {
      this.update(county, { said: exchange.text, loading: false });
    }
  }

  /** Load the favorites whose reports are missing or old. */
  async loadFavorites(): Promise<void> {
    for (const county of this.favorites()) {
      const card = this.cards()[county];
      if (!card?.at || Date.now() - card.at > FRESH_MS) {
        await this.load(county);
      }
    }
  }

  isFavorite(county: string): boolean {
    return this.favorites().includes(county);
  }

  /** Make a county a favorite, or not; favorites keep the order they're added in. */
  toggleFavorite(county: string): void {
    this.favorites.update((favorites) =>
      favorites.includes(county) ? favorites.filter((f) => f !== county) : [...favorites, county],
    );
    this.save(FAVORITES, this.favorites());
  }

  private update(county: string, change: Partial<Card>): void {
    this.cards.update((cards) => ({
      ...cards,
      [county]: {
        ...(cards[county] ?? { lines: null, alert: false, at: null, said: null, loading: false }),
        ...change,
      },
    }));
  }

  private stored(key: string): string[] {
    try {
      const stored = JSON.parse(localStorage.getItem(key) ?? '[]');
      return Array.isArray(stored) ? stored.filter((s) => typeof s === 'string') : [];
    } catch {
      return [];
    }
  }

  private save(key: string, value: string[]): void {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Kept until the app closes, then.
    }
  }
}
