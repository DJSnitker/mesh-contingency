import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { Api } from './api';
import { Inbox } from './inbox';
import { FakeApi } from '../testing/fakes';

describe('Inbox', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({ providers: [{ provide: Api, useValue: api }] });
  });

  async function render(): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(Inbox);
    await fixture.whenStable();
    return fixture.nativeElement;
  }

  it('lists who has messages from whom, never what they say', async () => {
    const element = await render();
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
    const element = await render();
    expect(element.textContent).toContain('No messages waiting.');
  });
});
