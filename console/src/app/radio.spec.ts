import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { afterEach, onTestFinished, vi } from 'vitest';

import { Api } from './api';
import { Radio } from './radio';
import { COMMANDS, CONTACTS, FakeApi } from '../testing/fakes';

describe('Radio', () => {
  let api: FakeApi;

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: Api, useValue: api }],
    });
  });

  /** The page, on a tab (Settings, the first, opens by itself). */
  async function render(tab = 'contacts') {
    const fixture = TestBed.createComponent(Radio);
    await fixture.whenStable();
    if (tab !== 'settings') {
      await open(fixture, tab);
    }
    return fixture;
  }

  async function open(
    fixture: { nativeElement: HTMLElement; whenStable(): Promise<unknown> },
    tab: string,
  ) {
    fixture.nativeElement.querySelector<HTMLButtonElement>(`#${tab}-tab`)!.click();
    await fixture.whenStable();
  }

  function tabs(element: HTMLElement): string[] {
    return [...element.querySelectorAll('[role=tab]')].map(
      (t) =>
        `${t.textContent!.replace(/\s+/g, ' ').trim()}${t.getAttribute('aria-selected') === 'true' ? ' *' : ''}`,
    );
  }

  function button(element: HTMLElement, label: string): HTMLButtonElement {
    return [...element.querySelectorAll('button')].find((b) => b.textContent?.trim() === label)!;
  }

  it('adverts and backs up', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    button(element, 'Flood advert').click();
    await fixture.whenStable();
    button(element, 'Back up now').click();
    await fixture.whenStable();
    expect(api.ran).toEqual([
      ['advert', 'flood'],
      ['backup', ''],
    ]);
    expect(element.querySelector('.reply')?.textContent).toContain('backup: done');
  });

  it('offers only what the console may run', async () => {
    api.commands = () => of(COMMANDS.filter((c) => c.name === 'backup'));
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    expect([...element.querySelectorAll('h2')].map((h) => h.textContent?.trim())).toEqual([
      'Backup',
    ]);
    // The contacts are still listed, with nothing to do to them.
    expect(element.querySelectorAll('.contacts li').length).toBe(2);
    expect(element.querySelector('.contacts button')).toBeNull();
  });

  function rows(element: HTMLElement): string[][] {
    return [...element.querySelectorAll('.contacts .contact-list li:not(.muted)')].map((li) =>
      [...li.querySelectorAll('strong, .badge, code, .about span')].map((e) =>
        e.textContent!.trim(),
      ),
    );
  }

  it('lists the contacts and how many the radio holds', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(1_000_000 + 3_600_000);
    api.contacts = () =>
      of({
        ...CONTACTS,
        contacts: [
          { ...CONTACTS.contacts[0], last_advert: 1_000 },
          { ...CONTACTS.contacts[0], key: 'ad'.repeat(32), name: null, admin: true, hops: 0 },
          CONTACTS.contacts[1],
        ],
      });
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector('.contacts-head .muted')?.textContent?.trim()).toBe(
      '3 of 350 on the radio',
    );
    expect(rows(element)).toEqual([
      ['Alice', 'user', 'a1a1a1a1a1a1', '1 hop', 'heard 1h ago'],
      ['?', 'admin', 'adadadadadad', 'direct', 'heard 1h ago'],
      ['Hilltop', 'repeater', '37ca00000000', 'no path (floods)', 'no advert heard'],
    ]);
  });

  it('filters the contacts', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    const filter = element.querySelector<HTMLInputElement>('.filter')!;
    for (const [text, names] of [
      ['repeater', ['Hilltop']],
      ['A1A1', ['Alice']],
      ['user', ['Alice']],
      ['zed', []],
    ] as const) {
      filter.value = text;
      filter.dispatchEvent(new Event('input'));
      await fixture.whenStable();
      expect(rows(element).map((row) => row[0])).toEqual(names);
    }
    expect(element.querySelector('.contacts li')?.textContent).toContain('Nothing matches');
  });

  it('removes a contact once confirmed, and reads them again', async () => {
    let reads = 0;
    api.contacts = () => {
      reads++;
      return of(CONTACTS);
    };
    api.answer = (command, text) =>
      of({
        command,
        messages: [`contact: this removes ${text}…`],
        asks: api.ran.length === 1,
        ok: true,
      });
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    const hilltop = element.querySelectorAll('.contacts li')[1] as HTMLElement;
    button(hilltop, 'Remove').click();
    await fixture.whenStable();
    expect(element.querySelector('.reply.asks')).not.toBeNull();
    expect(reads).toBe(1);
    button(element.querySelector('.reply')!, 'Confirm').click();
    await fixture.whenStable();
    const key = CONTACTS.contacts[1].key;
    expect(api.ran).toEqual([
      ['contact', `remove ${key}`],
      ['contact', `remove ${key}`],
    ]);
    expect(reads).toBe(2);
  });

  it('resets the path to a contact', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    button(element.querySelector('.contacts li')!, 'Reset path').click();
    await fixture.whenStable();
    expect(api.ran).toEqual([['contact', `path ${'a1'.repeat(32)}`]]);
  });

  it("says when it can't read the contacts", async () => {
    api.contacts = () => throwError(() => new Error('down'));
    const fixture = await render();
    expect(fixture.nativeElement.querySelector('.contacts .problem')?.textContent).toContain(
      "can't read the radio's contacts",
    );
  });

  it('reads the contacts again only after a contact command', async () => {
    let reads = 0;
    api.contacts = () => {
      reads++;
      return of(CONTACTS);
    };
    const fixture = await render();
    button(fixture.nativeElement, 'Back up now').click();
    await fixture.whenStable();
    expect(reads).toBe(1);
  });

  it('shows settings or contacts, a tab each, with the count; the channels are in Chat', async () => {
    const fixture = await render('settings');
    const element: HTMLElement = fixture.nativeElement;
    expect(tabs(element)).toEqual(['Settings *', 'Contacts 2']);
    expect(element.querySelector('[role=tabpanel] mc-radio-settings')).not.toBeNull();
    await open(fixture, 'contacts');
    expect(tabs(element)).toEqual(['Settings', 'Contacts 2 *']);
    expect(element.querySelector('[role=tabpanel]')?.id).toBe('contacts-panel');
    expect(element.querySelector('#channels-tab')).toBeNull();
  });

  it('moves between the tabs with the arrow keys', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    document.body.append(element); // so focus can move
    onTestFinished(() => element.remove());
    const contacts = element.querySelector<HTMLElement>('#contacts-tab')!;
    contacts.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
    await fixture.whenStable();
    expect(tabs(element)[0]).toBe('Settings *'); // round to the first
    expect(document.activeElement?.id).toBe('settings-tab');
    element
      .querySelector<HTMLElement>('#settings-tab')!
      .dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }));
    await fixture.whenStable();
    expect(tabs(element)[1]).toBe('Contacts 2 *'); // and back round to the last
  });
});
