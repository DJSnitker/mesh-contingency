import { FakeBle } from '../radio/fake-ble';
import { openScreen } from '../screens.testing';
import { clockWords, frequencyProblem, matching, PRESETS } from './radio-screen';

describe('RadioScreen', () => {
  let ble: FakeBle;

  beforeEach(() => {
    ble = new FakeBle();
    localStorage.clear();
  });

  async function open(ready = true) {
    const screen = await openScreen('/radio', ble, ready);
    const { page, fixture } = screen;
    /** Wait for the screen to show something. */
    const shows = (check: () => void) =>
      vi.waitFor(() => {
        fixture.detectChanges();
        check();
      });
    /** Press a button by its text, and wait until the radio is done. */
    const act = async (text: string) => {
      // The radio's buttons stay off while it's busy.
      screen.button(text).click();
      await shows(() => expect(screen.button('Refresh').disabled).toBe(false));
    };
    if (ready) {
      await shows(() => expect(page.querySelectorAll('.contacts li')).toHaveLength(3));
    }
    const text = (selector: string) =>
      page.querySelector(selector)?.textContent?.replace(/\s+/g, ' ').trim();
    return { ...screen, shows, act, text };
  }

  it('asks for the radio first', async () => {
    const { page } = await open(false);
    expect(page.textContent).toContain('Connect your radio first');
  });

  it('shows what the radio says about itself', async () => {
    ble.radio.clockAhead = -600;
    const { text } = await open();
    expect(text('.about .name')).toBe('Field T1000');
    expect(text('.frequency')).toBe('910.525 MHz · BW 62.5 kHz · SF7 · CR5 (Canada, USA)');
    expect(text('.power')).toBe('22 dBm of 22');
    expect(text('.position')).toBe('none');
    // Connecting set it.
    expect(text('.clock')).toBe('right');
  });

  it('renames it, and sets its power, position and sharing', async () => {
    const { type, act, text, button } = await open();
    type('radio-name', 'Dana T1000');
    await act('Rename');
    expect(text('.said')).toBe('Renamed Dana T1000. Others see it after the next advert.');
    expect(text('.about .name')).toBe('Dana T1000');
    expect(text('.radio-state')).toBe('Dana T1000');

    type('power', '30');
    expect(button('Set power').disabled).toBe(true);
    type('power', '14');
    await act('Set power');
    expect(text('.power')).toBe('14 dBm of 22');

    type('lat', '32.448736');
    type('lon', '-99.733144');
    await act('Set position');
    expect(text('.position')).toBe('32.448736, -99.733144 (not in adverts)');
    await act('Share it in adverts');
    expect(text('.position')).toBe('32.448736, -99.733144 (in adverts)');
    expect(button('Stop sharing')).toBeTruthy();
  });

  it('sets the clock, and sends adverts', async () => {
    const { act, text } = await open();
    ble.radio.clockAhead = -600;
    await act('Refresh');
    expect(text('.clock')).toBe('10m behind');
    await act('Set the clock from the phone');
    expect(text('.clock')).toBe('right');

    await act('Advert nearby');
    await act('Advert across the mesh');
    expect(ble.adverts).toEqual(['zero-hop', 'flood']);
    expect(text('.said')).toBe('Advert sent across the mesh.');
  });

  it('asks before changing the frequency, says how to go back, and restarts the radio', async () => {
    const { page, fixture, button, type, shows, text } = await open();
    const select = page.querySelector<HTMLSelectElement>('[name="preset"]')!;
    expect(select.value).toBe('Canada');
    expect(button('Set the frequency').disabled).toBe(true);
    expect(page.textContent).toContain('Your radio is on these now.');

    select.value = 'USA - Southern California';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    button('Set the frequency').click();
    fixture.detectChanges();
    expect(text('.confirm p')).toBe(
      "Set your radio to 927.875 MHz · BW 62.5 kHz · SF7 · CR5 and restart it? Radios on other settings won't hear yours, and you won't hear them. To go back, set the Canada preset.",
    );
    button('Cancel').click();
    fixture.detectChanges();
    expect(page.querySelector('.confirm')).toBeNull();
    expect(ble.reboots).toBe(0);

    select.value = 'custom';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    type('bw', '60');
    expect(page.textContent).toContain('The bandwidth is one of');
    expect(button('Set the frequency').disabled).toBe(true);
    type('freq', '927.875');
    type('bw', '62.5');
    button('Set the frequency').click();
    fixture.detectChanges();
    button('Set and restart').click();
    await shows(() => expect(page.textContent).toContain('The radio is restarting'));
    expect([ble.radio.freq, ble.reboots]).toEqual([927875, 1]);

    button('Connect again').click();
    await shows(() =>
      expect(text('.frequency')).toBe(
        '927.875 MHz · BW 62.5 kHz · SF7 · CR5 (USA - Southern California)',
      ),
    );
  });

  it("lists the radio's contacts, to reset a path or remove one", async () => {
    const { page, act, text } = await open();
    const rows = () => [...page.querySelectorAll('.contacts li')];
    expect(rows().map((li) => li.querySelector('.contact-name')?.textContent)).toEqual([
      'Erin',
      'Hill Repeater',
      'Ridge Node',
    ]);
    expect(rows()[0].textContent).toContain('Companion · 2 hops');
    expect(rows()[1].textContent).toContain('Repeater · no path yet (messages flood)');
    expect(rows()[2].textContent).toContain('Companion · direct');
    expect(text('.contacts')).toContain('Removing Ridge Node, the node,');

    const erin = rows()[0];
    erin.querySelector<HTMLButtonElement>('button')!.click();
    await act('Refresh');
    expect(rows()[0].textContent).toContain('no path yet');

    const ask = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    const remove = () =>
      [...rows()[1].querySelectorAll('button')]
        .find((b) => b.textContent?.includes('Remove'))!
        .click();
    remove();
    expect(rows()).toHaveLength(3);
    remove();
    await vi.waitFor(() => expect(text('.said')).toBe('Removed Hill Repeater.'));
    ask.mockRestore();
    expect(ble.contacts.map((c) => c.name)).toEqual(['Ridge Node', 'Erin']);
  });

  it('knows the presets, and the values a radio takes', () => {
    expect(PRESETS.length).toBeGreaterThan(20);
    expect(matching({ freq: 910.525, bw: 62.5, sf: 7, cr: 5 })).toEqual(['Canada', 'USA']);
    expect(frequencyProblem({ freq: 915, bw: 125, sf: 9, cr: 5 })).toBeNull();
    expect(frequencyProblem({ freq: 2400, bw: 125, sf: 9, cr: 5 })).toContain('150 to 960');
    expect(frequencyProblem({ freq: 915, bw: 125, sf: 13, cr: 5 })).toBe('SF is 5 to 12.');
    expect(frequencyProblem({ freq: 915, bw: 125, sf: 9, cr: 9 })).toBe('CR is 5 to 8.');
    expect(clockWords(30)).toBe('right');
    expect(clockWords(-600)).toBe('10m behind');
    expect(clockWords(3900)).toBe('1h 5m ahead');
    expect(clockWords(-200_000)).toBe('2d behind');
  });
});
