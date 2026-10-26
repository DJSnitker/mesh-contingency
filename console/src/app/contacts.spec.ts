import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { afterEach, vi } from 'vitest';

import { Api } from './api';
import { Contacts } from './contacts';
import { COMMANDS, CONTACTS, FakeApi } from '../testing/fakes';

describe('Contacts', () => {
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

  async function render() {
    const fixture = TestBed.createComponent(Contacts);
    await fixture.whenStable();
    return fixture;
  }

  function rows(element: HTMLElement): string[][] {
    return [...element.querySelectorAll('.contact-list li:not(.muted)')].map((li) =>
      [...li.querySelectorAll('strong, .badge, code, .about span')].map((e) =>
        e.textContent!.trim(),
      ),
    );
  }

  function button(element: HTMLElement, label: string): HTMLButtonElement {
    return [...element.querySelectorAll('button')].find((b) => b.textContent?.trim() === label)!;
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
    expect(element.querySelector('.contact-list li')?.textContent).toContain('Nothing matches');
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
    const hilltop = element.querySelectorAll('.contact-list li')[1] as HTMLElement;
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
    button(element.querySelector('.contact-list li')!, 'Reset path').click();
    await fixture.whenStable();
    expect(api.ran).toEqual([['contact', `path ${'a1'.repeat(32)}`]]);
  });

  it("says when it can't read the contacts", async () => {
    api.contacts = () => throwError(() => new Error('down'));
    const fixture = await render();
    expect(fixture.nativeElement.querySelector('.problem')?.textContent).toContain(
      "can't read the radio's contacts",
    );
  });

  it('messages a companion, but not a repeater', async () => {
    const fixture = await render();
    const items = fixture.nativeElement.querySelectorAll('.contact-list li');
    const alice = items[0].querySelector('a.btn') as HTMLAnchorElement;
    expect(alice.textContent?.trim()).toBe('Message');
    expect(alice.getAttribute('href')).toBe(`/chat/dm/${'a1'.repeat(32)}`);
    expect(alice.getAttribute('aria-label')).toBe('Message Alice');
    expect(items[1].querySelector('a.btn')).toBeNull(); // Hilltop, a repeater
  });

  it('lists the contacts with nothing to do to them when contact is not offered', async () => {
    api.commands = () => of(COMMANDS.filter((c) => c.name !== 'contact'));
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelectorAll('.contact-list li').length).toBe(2);
    expect(element.querySelector('.contact-list button')).toBeNull();
    expect(element.querySelector('.contact-list a.btn')).not.toBeNull(); // Message stays
  });

  it('is a tab of Chat', async () => {
    const fixture = await render();
    const tabs = [...fixture.nativeElement.querySelectorAll('mc-chat-tabs nav a')].map((a) =>
      (a as HTMLElement).textContent?.trim(),
    );
    expect(tabs).toEqual(['Chats', 'Channels', 'Contacts']);
  });
});
