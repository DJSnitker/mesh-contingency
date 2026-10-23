import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { Api } from './api';
import { AreaWeather } from './area-weather';
import { FakeApi, WEATHER } from '../testing/fakes';

/** Text with its runs of spaces made one. */
function text(element: Element | null | undefined): string {
  return element?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}

/** An element's text as read: its children's, a space between. */
function read(element: Element): string {
  return [...element.children].map(text).filter(Boolean).join(' ');
}

describe('AreaWeather', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({ providers: [{ provide: Api, useValue: api }] });
  });

  async function render(): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(AreaWeather);
    await fixture.whenStable();
    return fixture.nativeElement;
  }

  function cards(element: HTMLElement): HTMLElement[] {
    return [...element.querySelectorAll<HTMLElement>('.area')];
  }

  it('shows a card for each county, in order', async () => {
    const element = await render();
    expect(text(element.querySelector('h1'))).toBe('Area Weather');
    expect(text(element.querySelector('.title p'))).toContain('every 15 min');
    expect(cards(element).map((card) => text(card.querySelector('h2')))).toEqual([
      'Taylor, TX',
      'Jones, TX',
      'Callahan, TX',
    ]);
  });

  it('shows the weather now and the forecast', async () => {
    const taylor = cards(await render())[0];
    expect(text(taylor.querySelector('header span'))).toBe('near Buffalo Gap, TX');
    expect(text(taylor.querySelector('.now strong'))).toBe('63°');
    expect(text(taylor.querySelector('.now span'))).toBe('Clear');
    const details = [...taylor.querySelectorAll('.details span')].map((span) => text(span));
    expect(details).toEqual(['Wind SE 7 mph, gusts 15', 'Humidity 63%']);
    const periods = [...taylor.querySelectorAll('.periods li')].map(read);
    expect(periods).toEqual(['Today 85°F Mostly Sunny', 'Tonight 60°F Chance Showers 30%']);
    expect(text(taylor.querySelector('.foot'))).toBe('Abilene Regional Airport · 25m ago');
    expect(taylor.classList).not.toContain('attention');
    expect(taylor.querySelector('.stale')).toBeNull();
  });

  it('makes a county with an alert stand out', async () => {
    const jones = cards(await render())[1];
    expect(jones.classList).toContain('attention');
    expect(text(jones.querySelector('.alert'))).toBe('Wind Advisory');
  });

  it('keeps an old report, and says why it is old', async () => {
    const [, jones, callahan] = cards(await render());
    expect(text(jones)).toContain('No station near it is reporting.');
    expect(text(jones.querySelector('.stale'))).toBe('Not updated since 40m ago: no network');
    expect(text(callahan.querySelector('.stale'))).toBe('No report yet: TimeoutError');
    expect(callahan.querySelector('.now')).toBeNull();
  });

  it('says when an alert ends', async () => {
    const ends = new Date(2026, 9, 23, 18, 0).getTime() / 1000;
    const alert = { event: 'Flood Warning', severity: 'Severe', headline: null, ends };
    const taylor = { ...WEATHER.areas![0], alerts: [alert] };
    api.weather = () => of({ ...WEATHER, areas: [taylor] });
    const card = cards(await render())[0];
    expect(text(card.querySelector('.alert'))).toBe('Flood Warning until Oct 23, 18:00');
  });

  it('calls no wind calm, and waits for a first report', async () => {
    const calm = { ...WEATHER.areas![0], wind_mph: 0.2, gust_mph: null };
    const asking = { county: 'Nolan, TX', alerts: [], problem: null };
    api.weather = () => of({ ...WEATHER, areas: [calm, asking] });
    const [first, second] = cards(await render());
    expect(text(first.querySelector('.details'))).toContain('Wind calm');
    expect(text(second.querySelector('p'))).toBe('Asking the NWS…');
    expect(second.querySelector('.now, .stale')).toBeNull();
  });

  it('says how to add counties when there are none', async () => {
    api.weather = () => of({ ...WEATHER, areas: null });
    const element = await render();
    expect(cards(element)).toEqual([]);
    expect(text(element.querySelector('.panel'))).toContain('add them to counties under [alerts]');
  });

  it("says when the bot can't be reached", async () => {
    api.weather = () => throwError(() => new HttpErrorResponse({ status: 0 }));
    const element = await render();
    expect(text(element.querySelector('[role=alert]'))).toBe("can't reach the bot");
  });
});
