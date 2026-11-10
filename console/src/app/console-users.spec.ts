import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { Api } from './api';
import { ConsoleUsers } from './console-users';
import { FakeApi, SAM } from '../testing/fakes';

describe('ConsoleUsers', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    api.me.set(SAM);
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: Api, useValue: api }],
    });
  });

  async function render() {
    const fixture = TestBed.createComponent(ConsoleUsers);
    await fixture.whenStable();
    return fixture;
  }

  function rows(element: HTMLElement): HTMLElement[] {
    return [...element.querySelectorAll<HTMLElement>('.people > li')];
  }

  function button(within: HTMLElement, label: string): HTMLButtonElement {
    const found = [...within.querySelectorAll<HTMLButtonElement>('button')].find(
      (b) => b.textContent?.trim() === label,
    );
    if (!found) {
      throw new Error(`no ${label} button`);
    }
    return found;
  }

  it('lists them, apart from the radio users', async () => {
    const element: HTMLElement = (await render()).nativeElement;
    expect(element.textContent).toContain("Not the radio's users");
    const [alex, sam] = rows(element);
    expect(alex.textContent).toContain('by sam');
    expect(alex.textContent).toContain('never logged in');
    expect(sam.textContent).toContain("on the node's computer");
    expect(sam.textContent).toContain('you');
    // Yourself: your password is on Account, and no Remove.
    expect(sam.querySelector('a')?.textContent?.trim()).toBe('Change password');
    expect(sam.querySelectorAll('button').length).toBe(0);
  });

  it('removes someone after asking', async () => {
    const fixture = await render();
    const alex = () => rows(fixture.nativeElement)[0];
    button(alex(), 'Remove').click();
    await fixture.whenStable();
    expect(alex().textContent).toContain("Remove alex? They won't be able to log in.");
    expect(api.calls).toEqual([]);
    button(alex(), 'Keep').click();
    await fixture.whenStable();
    button(alex(), 'Remove').click();
    await fixture.whenStable();
    button(alex(), 'Remove').click();
    await fixture.whenStable();
    expect(api.calls).toEqual([['removeConsoleUser', 'alex']]);
    expect(fixture.nativeElement.querySelector('[role=status]')?.textContent).toContain(
      'Removed alex',
    );
  });

  it('gives someone a new password', async () => {
    const fixture = await render();
    const alex = rows(fixture.nativeElement)[0];
    button(alex, 'New password').click();
    await fixture.whenStable();
    const input = rows(fixture.nativeElement)[0].querySelector<HTMLInputElement>('form input')!;
    input.value = 'alex new password';
    input.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    button(rows(fixture.nativeElement)[0], 'Set password').click();
    await fixture.whenStable();
    expect(api.calls).toEqual([['setConsoleUserPassword', 'alex', 'alex new password']]);
    expect(fixture.nativeElement.textContent).toContain("they've been logged out");
  });

  it('adds one', async () => {
    const fixture = await render();
    const form = fixture.nativeElement.querySelector('[aria-labelledby=add-title] form');
    const [name, password] = form.querySelectorAll('input');
    name.value = ' Jo ';
    name.dispatchEvent(new Event('input'));
    password.value = 'short';
    password.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    button(form, 'Add').click();
    await fixture.whenStable();
    expect(fixture.nativeElement.querySelector('[role=alert]')?.textContent).toContain(
      '12 or more',
    );
    password.value = 'jo password 123';
    password.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    button(form, 'Add').click();
    await fixture.whenStable();
    expect(api.calls).toEqual([['addConsoleUser', 'jo', 'jo password 123']]);
    expect(fixture.nativeElement.querySelector('[role=status]')?.textContent).toContain('Added jo');
  });

  it('says when there are none yet', async () => {
    api.consoleUsers = () => of([]);
    const element: HTMLElement = (await render()).nativeElement;
    expect(element.textContent).toContain('No console users yet');
  });
});
