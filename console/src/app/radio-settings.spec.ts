import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { Api } from './api';
import { RadioSettings } from './radio-settings';
import { FakeApi, RADIO } from '../testing/fakes';

/** Text with its runs of spaces made one. */
function text(element: Element | null | undefined): string {
  return element?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}

/** An element's text as read: its parts (text and elements), a space between. */
function words(element: Element | null): string {
  return [...(element?.childNodes ?? [])]
    .filter((node) => node.nodeType !== Node.COMMENT_NODE) // Angular's markers
    .map((node) => node.textContent?.replace(/\s+/g, ' ').trim() ?? '')
    .filter(Boolean)
    .join(' ');
}

describe('RadioSettings', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({ providers: [{ provide: Api, useValue: api }] });
  });

  async function render(canChange = true) {
    const fixture = TestBed.createComponent(RadioSettings);
    fixture.componentRef.setInput('canChange', canChange);
    await fixture.whenStable();
    return fixture;
  }

  type Fixture = Awaited<ReturnType<typeof render>>;

  function button(fixture: Fixture, label: string): HTMLButtonElement {
    const found = [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')].find(
      (b) => text(b) === label,
    );
    if (!found) {
      throw new Error(`no ${label} button`);
    }
    return found;
  }

  async function type(fixture: Fixture, selector: string, value: string) {
    const field = (fixture.nativeElement as HTMLElement).querySelector<
      HTMLInputElement | HTMLSelectElement
    >(selector)!;
    field.value = value;
    field.dispatchEvent(new Event(field instanceof HTMLSelectElement ? 'change' : 'input'));
    await fixture.whenStable();
  }

  async function click(fixture: Fixture, label: string) {
    button(fixture, label).click();
    await fixture.whenStable();
  }

  it('shows the settings', async () => {
    const fixture = await render(false);
    const element: HTMLElement = fixture.nativeElement;
    const rows = [...element.querySelectorAll('.settings > div')].map((row) => [
      text(row.querySelector('dt')),
      words(row.querySelector('dd')),
    ]);
    expect(rows).toEqual([
      ['Name', 'test-node'],
      ['Frequency', '910.525 MHz · BW 62.5 kHz · SF7 · CR5 Canada USA'],
      ['TX power', '22 dBm of 22'],
      ['Position', '32.5, -99.75 (not in adverts)'],
      ['Clock', '2m behind'],
      ['Firmware', 'Test Board v1.9 (12 Oct 2026)'],
      ['New contacts', 'only what [contacts] auto_add takes (config.toml)'],
    ]);
    expect(element.querySelector('.settings .attention')).not.toBeNull(); // the clock is off
    // Without radio for the console: nothing to change, and why.
    expect(element.querySelector('form')).toBeNull();
    expect(text(element)).toContain('turn on radio under [commands]');
  });

  it('runs each change as the radio command, and reads the settings again', async () => {
    let reads = 0;
    api.radio = () => {
      reads++;
      return of(RADIO);
    };
    const fixture = await render();
    expect(button(fixture, 'Rename').disabled).toBe(true); // the same name
    await type(fixture, '#radio-name', '  Hilltop Relay ');
    await click(fixture, 'Rename');
    await type(fixture, '#radio-power', '10');
    await click(fixture, 'Set power');
    await type(fixture, '[aria-label=Latitude]', '32.4487');
    await type(fixture, '[aria-label=Longitude]', '-99.7331');
    await click(fixture, 'Set position');
    await click(fixture, 'Set clock');
    await click(fixture, 'Reboot radio');
    expect(api.ran).toEqual([
      ['radio', 'name Hilltop Relay'],
      ['radio', 'power 10'],
      ['radio', 'position 32.4487 -99.7331'],
      ['radio', 'clock'],
      ['radio', 'reboot'],
    ]);
    expect(reads).toBe(6);
  });

  it('starts the frequency on the radio’s preset, and says when nothing would change', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    // Canada and USA both match; USA suggests no path hash size.
    expect(element.querySelector<HTMLSelectElement>('.frequency select')!.value).toBe('USA');
    expect(text(element.querySelector('.frequency'))).toContain("That's what the radio is on now.");
    expect(element.querySelector('#radio-confirm-name')).toBeNull();
    await type(fixture, '.frequency select', 'Canada');
    expect(text(element.querySelector('.frequency'))).toContain('path hash size of 3 bytes');
  });

  it('changes the frequency only once the node’s name is typed', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    await type(fixture, '.frequency select', 'Australia (Narrow)');
    expect(text(element.querySelector('.frequency'))).toContain(
      'Now 910.525 MHz · BW 62.5 kHz · SF7 · CR5; after, 916.575 MHz · BW 62.5 kHz · SF7 · CR7.',
    );
    expect(button(fixture, 'Change frequency').disabled).toBe(true);
    await type(fixture, '#radio-confirm-name', 'test-nod');
    expect(button(fixture, 'Change frequency').disabled).toBe(true);
    await type(fixture, '#radio-confirm-name', 'test-node');
    await click(fixture, 'Change frequency');
    expect(api.ran).toEqual([['radio', 'freq Australia (Narrow)']]);
  });

  it('takes other values, once all four are given', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    await type(fixture, '.frequency select', 'custom');
    await type(fixture, '.custom label:nth-child(1) input', '915.8');
    await type(fixture, '.custom select', '250');
    await type(fixture, '.custom label:nth-child(3) input', '10');
    await type(fixture, '.custom label:nth-child(4) input', '');
    expect(element.querySelector('#radio-confirm-name')).toBeNull(); // CR missing
    await type(fixture, '.custom label:nth-child(4) input', '5');
    await type(fixture, '#radio-confirm-name', 'test-node');
    await click(fixture, 'Change frequency');
    expect(api.ran).toEqual([['radio', 'freq 915.8 250 10 5']]);
  });

  it("says when it can't read the settings", async () => {
    api.radio = () => throwError(() => new Error('down'));
    const fixture = await render();
    expect(text(fixture.nativeElement.querySelector('.problem'))).toContain(
      "can't read the radio's settings",
    );
  });
});
