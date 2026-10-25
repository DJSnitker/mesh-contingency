import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { Api } from './api';
import { Mailbox } from './mailbox';
import { ALICE, COMMANDS, FakeApi } from '../testing/fakes';

describe('Mailbox', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({ providers: [{ provide: Api, useValue: api }] });
  });

  async function render() {
    const fixture = TestBed.createComponent(Mailbox);
    await fixture.whenStable();
    return fixture;
  }

  type Fixture = Awaited<ReturnType<typeof render>>;

  async function type(
    fixture: Fixture,
    field: HTMLTextAreaElement | HTMLSelectElement,
    text: string,
  ) {
    field.value = text;
    field.dispatchEvent(new Event(field instanceof HTMLSelectElement ? 'change' : 'input'));
    await fixture.whenStable();
  }

  function leave(fixture: Fixture): HTMLElement {
    return fixture.nativeElement.querySelector('[aria-labelledby=msg-title]');
  }

  function button(where: HTMLElement, label: string): HTMLButtonElement {
    return [...where.querySelectorAll('button')].find((b) => b.textContent?.includes(label))!;
  }

  it('lists who has messages from whom, never what they say', async () => {
    const element: HTMLElement = (await render()).nativeElement;
    expect(element.querySelector('h1')?.textContent).toBe('Mailbox');
    expect(element.textContent).toContain('2 message(s) waiting for 1 user(s)');
    const box = element.querySelector('.mailbox')!;
    expect(box.querySelector('h2')?.textContent).toContain('Alice');
    expect(box.textContent).toContain('2 message(s), 1 unread');
    const rows = [...box.querySelectorAll('li')].map((li) => li.textContent ?? '');
    expect(rows[0]).toContain('from Bob');
    expect(rows[0]).not.toContain('unread');
    expect(rows[1]).toContain('from Dana');
    expect(rows[1]).toContain('unread');
    expect(rows[1]).toContain('sealed');
    expect(element.textContent).toContain('stays private');
  });

  it('says when nothing is waiting', async () => {
    api.inbox = () => of([]);
    const element: HTMLElement = (await render()).nativeElement;
    expect(element.textContent).toContain('No messages waiting.');
  });

  it('leaves a message for a user, then empties the box and reads the inbox again', async () => {
    let reads = 0;
    api.inbox = () => {
      reads++;
      return of([]);
    };
    const fixture = await render();
    const msg = leave(fixture);
    const options = [...msg.querySelectorAll('option')].map((o) => o.textContent?.trim());
    expect(options).toEqual(['Pick a user…', 'Alice (a1a1a1a1)']); // users, not an admin without a section
    expect(button(msg, 'Leave message').disabled).toBe(true);
    await type(fixture, msg.querySelector('select')!, ALICE.key);
    await type(fixture, msg.querySelector('textarea')!, 'water at the church');
    button(msg, 'Leave message').click();
    await fixture.whenStable();
    expect(api.ran).toEqual([['msg', `${ALICE.key} water at the church`]]);
    expect(msg.querySelector('textarea')!.value).toBe('');
    expect(reads).toBe(2);
  });

  it('keeps the text when the bot refuses', async () => {
    api.answer = (command) =>
      of({ command, messages: ['msg: Alice’s inbox is full'], asks: false, ok: false });
    const fixture = await render();
    const msg = leave(fixture);
    await type(fixture, msg.querySelector('select')!, ALICE.key);
    await type(fixture, msg.querySelector('textarea')!, 'water at the church');
    button(msg, 'Leave message').click();
    await fixture.whenStable();
    expect(msg.querySelector('.reply.failed')?.textContent).toContain('inbox is full');
    expect(msg.querySelector('textarea')!.value).toBe('water at the church');
  });

  it('offers Leave a message only if the console may run msg', async () => {
    api.commands = () => of(COMMANDS.filter((c) => c.name !== 'msg'));
    const fixture = await render();
    expect(leave(fixture)).toBeNull();
  });
});
