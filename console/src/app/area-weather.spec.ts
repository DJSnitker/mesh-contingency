import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { Api } from './api';
import { AreaWeather, FAVORITES, wxLines } from './area-weather';
import { COMMANDS, FakeApi, WEATHER } from '../testing/fakes';

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
    localStorage.clear();
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
    expect(text(element.querySelector('h1'))).toBe('Weather');
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

  it('puts the starred counties first, the rest under Show more, kept in the browser', async () => {
    const fixture = TestBed.createComponent(AreaWeather);
    await fixture.whenStable();
    const element: HTMLElement = fixture.nativeElement;
    const names = (where: string) =>
      [...element.querySelectorAll(`${where} .area h2`)].map((h) => text(h));
    expect(element.textContent).toContain('Star a county to see it first');
    expect(element.querySelector('details.others')).toBeNull();

    element.querySelector<HTMLButtonElement>('[aria-label="Star Callahan, TX"]')!.click();
    await fixture.whenStable();
    element.querySelector<HTMLButtonElement>('[aria-label="Star Taylor, TX"]')!.click();
    await fixture.whenStable();
    expect(names('.favorites')).toEqual(['Callahan, TX', 'Taylor, TX']); // in the order starred
    const more = element.querySelector<HTMLDetailsElement>('details.others')!;
    expect(more.open).toBe(false);
    expect(text(more.querySelector('summary'))).toBe('Show more (1)');
    expect(names('details.others')).toEqual(['Jones, TX']);
    expect(JSON.parse(localStorage.getItem(FAVORITES)!)).toEqual(['Callahan, TX', 'Taylor, TX']);
    expect(
      element.querySelector('[aria-label="Unstar Taylor, TX"]')?.getAttribute('aria-pressed'),
    ).toBe('true');

    // Kept for next time; a county no longer watched is left out.
    localStorage.setItem(FAVORITES, JSON.stringify(['Jones, TX', 'Nolan, TX']));
    const again: HTMLElement = await render();
    expect([...again.querySelectorAll('.favorites .area h2')].map((h) => text(h))).toEqual([
      'Jones, TX',
    ]);
  });

  it('looks up the weather anywhere, and says when it fails', async () => {
    api.answer = (command, where) =>
      of(
        where === '33101'
          ? {
              command,
              messages: [
                '33101 ALERT: Rip Current Statement | Mostly Cloudy, 20% precip 6h | 82F E14mph G18',
              ],
              asks: false,
              ok: true,
            }
          : { command, messages: ['wx: no such zipcode 99999'], asks: false, ok: false },
      );
    const fixture = TestBed.createComponent(AreaWeather);
    await fixture.whenStable();
    const element: HTMLElement = fixture.nativeElement;
    const box = element.querySelector<HTMLInputElement>('input[name=where]')!;
    box.value = ' 33101 ';
    box.dispatchEvent(new Event('input'));
    box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    await fixture.whenStable();
    expect(api.ran.at(-1)).toEqual(['wx', '33101']);
    const lines = [...element.querySelectorAll('.report li')];
    expect(lines.map((li) => text(li))).toEqual([
      '33101 ALERT: Rip Current Statement',
      'Mostly Cloudy, 20% precip 6h',
      '82F E14mph G18',
    ]);
    expect(lines[0].classList.contains('alert')).toBe(true);

    box.value = '99999';
    box.dispatchEvent(new Event('input'));
    box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    await fixture.whenStable();
    expect(element.querySelector('.report')).toBeNull();
    expect(text(element.querySelector('.lookup .problem'))).toBe('wx: no such zipcode 99999');
  });

  it('reads wx parts that came in numbered messages', () => {
    expect(wxLines(['(1/2) Taylor, TX ALERT: Wind', '(2/2) Advisory | 81F S11mph'])).toEqual([
      'Taylor, TX ALERT: Wind Advisory',
      '81F S11mph',
    ]);
  });

  describe('the alert buttons', () => {
    async function fixture() {
      const f = TestBed.createComponent(AreaWeather);
      await f.whenStable();
      return f;
    }

    async function click(f: Awaited<ReturnType<typeof fixture>>, label: string) {
      const found = [...(f.nativeElement as HTMLElement).querySelectorAll('button')].find(
        (b) => text(b) === label,
      );
      if (!found) {
        throw new Error(`no ${label} button`);
      }
      found.click();
      await f.whenStable();
    }

    it('asks before posting the alert test, on the alert channel', async () => {
      const f = await fixture();
      const element: HTMLElement = f.nativeElement;
      expect(text(element.querySelector('.alert-setup p'))).toContain('posted to #contingency-wx');
      await click(f, 'Post alert test');
      expect(api.ran).toEqual([]);
      expect(text(element.querySelector('.confirm'))).toContain(
        'This posts the test message to #contingency-wx now, on the air',
      );
      await click(f, 'Cancel');
      expect(element.querySelector('.confirm')).toBeNull();
      expect(api.ran).toEqual([]);

      await click(f, 'Post alert test');
      await click(f, 'Post it');
      expect(api.ran).toEqual([['testalert', '']]);
      expect(element.querySelector('.confirm')).toBeNull();
      expect(text(element.querySelector('.reply'))).toContain('testalert: done');
    });

    it('looks the counties up again', async () => {
      const f = await fixture();
      await click(f, 'Look up counties again');
      expect(api.ran).toEqual([['alertmap', '']]);
    });

    it('offers only what the console may run', async () => {
      api.commands = () => of(COMMANDS.filter((c) => c.name === 'alertmap'));
      const f = await fixture();
      const element: HTMLElement = f.nativeElement;
      expect([...element.querySelectorAll('.alert-setup button')].map(text)).toEqual([
        'Look up counties again',
      ]);
      expect(text(element.querySelector('.alert-setup p'))).toContain(
        'posted to the alert channel',
      );

      api.commands = () => of(COMMANDS.filter((c) => c.name === 'whois'));
      const none: HTMLElement = (await fixture()).nativeElement;
      expect(none.querySelector('.alert-setup')).toBeNull();
    });
  });
});
