import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { Api } from './api';
import { Checkins } from './checkins';
import { COMMANDS, FakeApi } from '../testing/fakes';

describe('Checkins', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({ providers: [{ provide: Api, useValue: api }] });
  });

  async function render() {
    const fixture = TestBed.createComponent(Checkins);
    await fixture.whenStable();
    return fixture;
  }

  function buttons(element: HTMLElement): string[] {
    return [...element.querySelectorAll('.clear button')].map((b) => b.textContent?.trim() ?? '');
  }

  function press(element: HTMLElement, label: string): void {
    [...element.querySelectorAll<HTMLButtonElement>('.clear button')]
      .find((b) => b.textContent?.trim() === label)!
      .click();
  }

  it('shows who has checked in, newest first, and who has not', async () => {
    const element: HTMLElement = (await render()).nativeElement;
    expect(element.textContent).toContain('2 checked in, 1 not yet');
    const entries = [...element.querySelectorAll('.entry')].map(
      (e) => e.querySelector('strong')?.textContent,
    );
    expect(entries).toEqual(['Alice', 'Admin Radio']);
    expect(element.querySelector('.entry .status')?.textContent).toBe('ok, at the shelter');
    expect(element.querySelector('.missing')?.textContent).toContain('Bob');
  });

  it('asks before clearing, since clearstatus acts at once', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    expect(buttons(element)).toEqual(['Clear check-ins']);
    press(element, 'Clear check-ins');
    await fixture.whenStable();
    expect(element.querySelector('.clear')?.textContent).toContain('Clear all 2 check-ins?');
    expect(api.ran).toEqual([]);
    press(element, 'Cancel');
    await fixture.whenStable();
    expect(api.ran).toEqual([]);

    api.checkins = () => of({ checkins: [], missing: [] });
    press(element, 'Clear check-ins');
    await fixture.whenStable();
    press(element, 'Yes, clear');
    await fixture.whenStable();
    expect(api.ran).toEqual([['clearstatus', '']]);
    expect(element.querySelector('.reply')?.textContent).toContain('clearstatus: done');
    expect(element.textContent).toContain('Nobody has checked in');
    expect(buttons(element)).toEqual([]); // nothing left to clear
  });

  it("looks up someone's check-in", async () => {
    api.answer = (command, text) =>
      of({ command, messages: [`${text}: ok, at the shelter (15m ago)`], asks: false, ok: true });
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    const look = element.querySelector<HTMLElement>('[aria-labelledby=look-title]')!;
    const box = look.querySelector<HTMLInputElement>('input[name=who]')!;
    box.value = ' alice ';
    box.dispatchEvent(new Event('input'));
    box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    await fixture.whenStable();
    expect(api.ran).toEqual([['status', 'alice']]);
    expect(look.querySelector('.reply')?.textContent).toContain('alice: ok, at the shelter');
  });

  it('offers the lookup only if the console may run status', async () => {
    api.commands = () => of(COMMANDS.filter((c) => c.name !== 'status'));
    const element: HTMLElement = (await render()).nativeElement;
    expect(element.querySelector('[aria-labelledby=look-title]')).toBeNull();
  });
});
