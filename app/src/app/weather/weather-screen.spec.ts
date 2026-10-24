import { FakeBle } from '../radio/fake-ble';
import { openScreen, reply } from '../screens.testing';

describe('WeatherScreen', () => {
  let ble: FakeBle;

  beforeEach(() => {
    ble = new FakeBle();
    localStorage.clear();
  });

  const open = (ready = true) => openScreen('/weather', ble, ready);
  const lines = (page: HTMLElement) =>
    [...page.querySelectorAll('.report li')].map((li) => li.textContent?.trim());

  it('asks for the radio and the node first', async () => {
    const { page, button } = await open(false);
    expect(page.textContent).toContain('Connect your radio and pick the node first');
    expect(button('Get the verse').disabled).toBe(true);
  });

  it('shows the weather a section a line, alerts marked', async () => {
    ble.node = () => reply('wx, with alerts');
    const { page, type, press } = await open();
    type('where', '79601');
    await press('Get the weather');
    expect(ble.sent.map(([, text]) => text)).toEqual(['wx 79601']);
    expect(lines(page)).toEqual([
      '79601 ALERT: Flash Flood Warning; Wind Advisory',
      'Heavy Rain, 0.31in/hr, 90% precip 6h',
      '68F S25mph G43',
    ]);
    expect(page.querySelector('.report li')?.classList).toContain('alert');
  });

  it("says what the node said when it can't find the place", async () => {
    ble.node = () => reply('wx, unknown zipcode');
    const { page, type, press } = await open();
    type('where', '00000');
    await press('Get the weather');
    expect(page.querySelector('.weather .said')?.textContent).toBe('wx: unknown zipcode 00000');
  });

  it('shows a verse, whole though it came in parts, or the verse of the day', async () => {
    ble.node = () => reply('verse, a passage in parts');
    const { page, type, press } = await open();
    type('reference', 'Psalm 23:1-4');
    await press('Get the verse');
    expect(page.querySelector('.passage strong')?.textContent).toBe('Psalm 23:1-4');
    expect(page.querySelector('.passage')?.textContent).toContain(
      'Your rod and Your staff, they comfort me.',
    );

    type('reference', '');
    await press('Get the verse');
    expect(ble.sent.map(([, text]) => text)).toEqual(['verse Psalm 23:1-4', 'verse']);
  });
});
