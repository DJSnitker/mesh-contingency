import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { Api } from './api';
import { Users } from './users';
import { ALICE, CAROL, FakeApi } from '../testing/fakes';

describe('Users', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({ providers: [{ provide: Api, useValue: api }] });
  });

  async function render() {
    const fixture = TestBed.createComponent(Users);
    await fixture.whenStable();
    return fixture;
  }

  function button(element: HTMLElement, within: string, label: string): HTMLButtonElement {
    const found = [...element.querySelectorAll<HTMLButtonElement>(`${within} button`)].find(
      (b) => b.textContent?.trim() === label,
    );
    if (!found) {
      throw new Error(`no ${label} button in ${within}`);
    }
    return found;
  }

  it('lists the users and admins', async () => {
    const element: HTMLElement = (await render()).nativeElement;
    expect(element.textContent).toContain('1 user, 1 admin');
    const rows = [...element.querySelectorAll('.person')];
    expect(rows.map((r) => r.querySelector('.who strong')?.textContent)).toEqual([
      'Admin Radio',
      'Alice',
    ]);
    const alice = rows[1].textContent ?? '';
    expect(alice).toContain('a1a1a1a1a1a1');
    expect(alice).toContain('qm: alice@example.com');
    expect(alice).toContain('emailall: 2 addresses');
    expect(alice).toContain('passphrase set');
    expect(alice).toContain('ok');
    expect(alice).toContain('(1 unread)');
    // An admin with no user section has nothing to remove.
    expect(rows[0].querySelectorAll('button').length).toBe(0);
    expect(rows[0].textContent).toContain('not a user');
  });

  it('approves and denies join requests by key', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector('.requests')?.textContent).toContain('Carol T-Deck');
    button(element, '.requests', 'Approve').click();
    button(element, '.requests', 'Deny').click();
    expect(api.ran).toEqual([
      ['approve', CAROL.key],
      ['deny', CAROL.key],
    ]);
  });

  it('runs whois and resetpass for a user', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    button(element, '.list', 'Whois').click();
    await fixture.whenStable();
    expect(element.querySelector('.reply')?.textContent).toContain('whois: done');
    button(element, '.list', 'Reset passphrase').click();
    expect(api.ran).toEqual([
      ['whois', ALICE.key],
      ['resetpass', ALICE.key],
    ]);
  });

  it('asks before removing, and reads the users again after', async () => {
    let reads = 0;
    api.users = () => {
      reads++;
      return of(reads === 1 ? [ALICE] : []);
    };
    api.answer = (command) =>
      of({ command, messages: ['remove: this removes Alice. Send it again…'], asks: true });
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    button(element, '.list', 'Remove').click();
    await fixture.whenStable();
    expect(element.querySelector('.reply.asks')?.textContent).toContain('this removes Alice');
    expect(reads).toBe(1); // nothing changed yet

    api.answer = (command) => of({ command, messages: ['remove: Alice removed'], asks: false });
    button(element, '.reply', 'Confirm').click();
    await fixture.whenStable();
    expect(api.ran).toEqual([
      ['remove', ALICE.key],
      ['remove', ALICE.key],
    ]);
    expect(element.querySelector('.reply')?.textContent).toContain('Alice removed');
    expect(reads).toBe(2);
    expect(element.textContent).toContain('No users yet');
  });

  it('cancelling a question sends nothing', async () => {
    api.answer = (command) =>
      of({ command, messages: ['remove: this removes Alice.'], asks: true });
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    button(element, '.list', 'Remove').click();
    await fixture.whenStable();
    button(element, '.reply', 'Cancel').click();
    await fixture.whenStable();
    expect(element.querySelector('.reply')).toBeNull();
    expect(api.ran.length).toBe(1);
  });

  it('shows no requests panel when nobody is waiting', async () => {
    api.requests = () => of([]);
    const element: HTMLElement = (await render()).nativeElement;
    expect(element.querySelector('.requests')).toBeNull();
  });
});
