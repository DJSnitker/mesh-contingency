import { TestBed } from '@angular/core/testing';

import { FakeBle } from '../radio/fake-ble';
import { openScreen, reply } from '../screens.testing';
import { TODAY } from './bible-screen';

describe('BibleScreen', () => {
  let ble: FakeBle;

  beforeEach(() => {
    ble = new FakeBle();
    ble.node = (text) =>
      ({
        verse: reply('verse'),
        'verse Psalm 23:1-4': reply('verse, a passage in parts'),
        'verse Hezekiah 1:1': reply('verse, no such book'),
      })[text] ?? [];
    localStorage.clear();
  });

  async function open(ready = true) {
    const screen = await openScreen('/bible', ble, ready);
    const shows = (check: () => void) =>
      vi.waitFor(() => {
        screen.fixture.detectChanges();
        check();
      });
    return { ...screen, shows };
  }

  it('asks for the radio and the node first', async () => {
    const { page, button } = await open(false);
    expect(page.textContent).toContain('Connect your radio and pick the node first');
    expect(button('Get the verse of the day').disabled).toBe(true);
  });

  it('shows the verse of the day, asked for once a day', async () => {
    const { page, shows } = await open();
    await shows(() =>
      expect(page.querySelector('.today .passage strong')?.textContent).toBe('John 3:16'),
    );
    expect(page.querySelector('.today .passage')?.textContent).toContain(
      'For God so loved the world',
    );
    expect(page.querySelector('.today .passage')?.textContent).toContain('have eternal life.');
    expect(JSON.parse(localStorage.getItem(TODAY)!).reference).toBe('John 3:16');

    // Opened again today: kept, not asked again.
    TestBed.resetTestingModule();
    const sent = ble.sent.length;
    const again = await open();
    expect(again.page.querySelector('.today .passage strong')?.textContent).toBe('John 3:16');
    expect(ble.sent.length).toBe(sent);
  });

  it('asks again on another day', async () => {
    localStorage.setItem(
      TODAY,
      JSON.stringify({ date: '2000-01-01', reference: 'Genesis 1:1', text: 'In the beginning' }),
    );
    const { page, shows } = await open();
    await shows(() =>
      expect(page.querySelector('.today .passage strong')?.textContent).toBe('John 3:16'),
    );
  });

  it('looks up a verse, and says what the node said when it can’t', async () => {
    const { page, type, press, shows } = await open();
    await shows(() => expect(page.querySelector('.today .passage')).not.toBeNull());
    type('reference', 'Psalm 23:1-4');
    await press('Look it up');
    expect(page.querySelector('.found strong')?.textContent).toBe('Psalm 23:1-4');
    expect(page.querySelector('.found')?.textContent).toContain(
      'Your rod and Your staff, they comfort me.',
    );

    type('reference', 'Hezekiah 1:1');
    await press('Look it up');
    expect(page.querySelector('.found')).toBeNull();
    expect(page.querySelector('.lookup .said')?.textContent).toBe("verse: unknown book 'Hezekiah'");
  });
});
