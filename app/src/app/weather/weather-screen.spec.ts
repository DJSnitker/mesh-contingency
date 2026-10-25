import { TestBed } from '@angular/core/testing';

import { FakeBle } from '../radio/fake-ble';
import { openScreen, reply } from '../screens.testing';
import { AreaWeather, COUNTIES, FAVORITES } from './area-weather';

describe('WeatherScreen', () => {
  let ble: FakeBle;
  /** What the node answers: the fixtures' area replies. */
  const node = (text: string) =>
    ({
      area: reply('area, the counties'),
      'area Taylor, TX': reply('area, a county'),
      'area Jones, TX': reply('area, a county with an alert'),
      'area Harris, TX': reply('area, no report yet'),
      'wx 79601': reply('wx, with alerts'),
      'wx 00000': reply('wx, unknown zipcode'),
    })[text] ?? [];

  beforeEach(() => {
    ble = new FakeBle();
    ble.node = node;
    localStorage.clear();
  });

  async function open(ready = true) {
    const screen = await openScreen('/weather', ble, ready);
    const { page, fixture } = screen;
    const shows = (check: () => void) =>
      vi.waitFor(() => {
        fixture.detectChanges();
        check();
      });
    const card = (county: string) =>
      page.querySelector<HTMLElement>(`.card[data-county="${county}"]`)!;
    const lines = (county: string) =>
      [...card(county).querySelectorAll('.report li')].map((li) => li.textContent?.trim());
    /** Press a button in a county's card. */
    const inCard = async (county: string, text: string) => {
      [...card(county).querySelectorAll('button')]
        .find((b) => b.textContent?.includes(text))!
        .click();
      await shows(() => expect(screen.link.ready()).toBe(true));
      await new Promise((resolve) => setTimeout(resolve, 0));
      await shows(() => expect(screen.link.ready()).toBe(true));
    };
    const star = (county: string) => card(county).querySelector<HTMLButtonElement>('.star')!;
    return { ...screen, shows, card, lines, inCard, star };
  }

  it('asks for the radio and the node first', async () => {
    const { page, button } = await open(false);
    expect(page.textContent).toContain('Connect your radio and pick the node first');
    expect(button('Get the counties').disabled).toBe(true);
  });

  it("gets the node's counties by itself, a card each, and a county's report on asking", async () => {
    const { page, shows, card, lines, inCard } = await open();
    await shows(() => expect(page.querySelectorAll('.all .card')).toHaveLength(19));
    expect(ble.sent.map(([, text]) => text)).toEqual(['area']);
    expect(JSON.parse(localStorage.getItem(COUNTIES)!)).toHaveLength(19);

    await inCard('Taylor, TX', 'Get the weather');
    expect(lines('Taylor, TX')).toEqual([
      '63F, Clear',
      'S7mph',
      '12m ago',
      'Tonight: 55F Mostly Clear 20%',
    ]);
    expect(card('Taylor, TX').querySelector('.report li')?.classList).not.toContain('alert');
    expect(card('Taylor, TX').textContent).toContain('Update');

    await inCard('Jones, TX', 'Get the weather');
    expect(lines('Jones, TX')[0]).toBe('ALERT: Wind Advisory');
    expect(card('Jones, TX').querySelector('.report li')?.classList).toContain('alert');

    await inCard('Harris, TX', 'Get the weather');
    expect(card('Harris, TX').querySelector('.said')?.textContent).toContain(
      'no report for Harris, TX yet',
    );
  });

  it('shows favorites first, loaded by themselves, and the rest under Show more', async () => {
    const { page, shows, star } = await open();
    await shows(() => expect(page.querySelectorAll('.all .card')).toHaveLength(19));
    star('Jones, TX').click();
    star('Taylor, TX').click();
    await shows(() => expect(page.querySelectorAll('.favorites .card')).toHaveLength(2));
    expect([...page.querySelectorAll('.favorites .card h2')].map((h) => h.textContent)).toEqual([
      'Jones, TX',
      'Taylor, TX',
    ]);
    expect(JSON.parse(localStorage.getItem(FAVORITES)!)).toEqual(['Jones, TX', 'Taylor, TX']);
    const more = page.querySelector<HTMLDetailsElement>('details.more')!;
    expect(more.open).toBe(false);
    expect(more.querySelector('summary')?.textContent).toContain('Show more (17)');
    expect(star('Jones, TX').getAttribute('aria-pressed')).toBe('true');

    // Opened again later: the counties are kept, and the favorites load by themselves.
    TestBed.resetTestingModule();
    ble = new FakeBle();
    ble.node = node;
    const again = await open();
    await again.shows(() => expect(again.lines('Taylor, TX')).toHaveLength(4));
    expect(again.lines('Jones, TX')[0]).toBe('ALERT: Wind Advisory');
    expect(ble.sent.map(([, text]) => text)).toEqual(['area Jones, TX', 'area Taylor, TX']);

    again.star('Jones, TX').click();
    again.star('Taylor, TX').click();
    await again.shows(() => expect(again.page.querySelector('details.more')).toBeNull());
    expect(again.page.querySelectorAll('.all .card')).toHaveLength(19);
  });

  it('keeps the reports while the app is open', async () => {
    const { page, shows, star } = await open();
    await shows(() => expect(page.querySelectorAll('.all .card')).toHaveLength(19));
    star('Taylor, TX').click();
    const area = TestBed.inject(AreaWeather);
    await area.loadFavorites();
    await area.loadFavorites();
    expect(ble.sent.map(([, text]) => text)).toEqual(['area', 'area Taylor, TX']);
  });

  it('gets the weather for another place', async () => {
    const { page, type, press, shows } = await open();
    await shows(() => expect(page.querySelectorAll('.all .card')).toHaveLength(19));
    type('where', '79601');
    await press('Look it up');
    expect(
      [...page.querySelectorAll('.lookup .report li')].map((li) => li.textContent?.trim()),
    ).toEqual([
      '79601 ALERT: Flash Flood Warning; Wind Advisory',
      'Heavy Rain, 0.31in/hr, 90% precip 6h',
      '68F S25mph G43',
    ]);
    type('where', '00000');
    await press('Look it up');
    expect(page.querySelector('.lookup .said')?.textContent).toBe('wx: unknown zipcode 00000');
  });
});
