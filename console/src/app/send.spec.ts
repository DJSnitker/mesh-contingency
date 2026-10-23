import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { Api } from './api';
import { Send } from './send';
import { ALICE, COMMANDS, FakeApi } from '../testing/fakes';

describe('Send', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({ providers: [{ provide: Api, useValue: api }] });
  });

  async function render() {
    const fixture = TestBed.createComponent(Send);
    await fixture.whenStable();
    return fixture;
  }

  type Fixture = Awaited<ReturnType<typeof render>>;

  function section(fixture: Fixture, title: string): HTMLElement {
    return [
      ...(fixture.nativeElement as HTMLElement).querySelectorAll<HTMLElement>('section'),
    ].find((s) => s.querySelector('h2')?.textContent?.includes(title))!;
  }

  async function type(
    fixture: Fixture,
    field: HTMLTextAreaElement | HTMLSelectElement,
    text: string,
  ) {
    field.value = text;
    field.dispatchEvent(new Event(field instanceof HTMLSelectElement ? 'change' : 'input'));
    await fixture.whenStable();
  }

  function button(where: HTMLElement, label: string): HTMLButtonElement {
    return [...where.querySelectorAll('button')].find((b) => b.textContent?.includes(label))!;
  }

  it('posts to the channel picked, then empties the box', async () => {
    const fixture = await render();
    const post = section(fixture, 'Post to a channel');
    const box = post.querySelector('textarea')!;
    expect(button(post, 'Post to').textContent).toContain('#contingency-wx');
    expect(button(post, 'Post to').disabled).toBe(true); // nothing to post yet

    post
      .querySelectorAll<HTMLInputElement>('input[type=radio]')[1]
      .dispatchEvent(new Event('change'));
    await type(fixture, box, '  net at 19:00 on 146.52  ');
    expect(post.querySelector('.count')?.textContent).toContain('22 / 119');
    button(post, 'Post to #contingency-comm').click();
    await fixture.whenStable();
    expect(api.ran).toEqual([['comm', 'net at 19:00 on 146.52']]);
    expect(post.querySelector('.reply')?.textContent).toContain('comm: done');
    expect(box.value).toBe('');
  });

  it("won't post more than one channel message holds", async () => {
    const fixture = await render();
    const post = section(fixture, 'Post to a channel');
    await type(fixture, post.querySelector('textarea')!, 'x'.repeat(120));
    expect(post.querySelector('.count.over')).not.toBeNull();
    expect(post.textContent).toContain('shorten it');
    expect(button(post, 'Post to').disabled).toBe(true);
  });

  it('keeps the text when the bot refuses', async () => {
    api.answer = (command) =>
      of({ command, messages: ['msg: Alice’s inbox is full'], asks: false, ok: false });
    const fixture = await render();
    const msg = section(fixture, 'Leave a message');
    const options = [...msg.querySelectorAll('option')].map((o) => o.textContent?.trim());
    expect(options).toEqual(['Pick a user…', 'Alice (a1a1a1a1)']); // users, not an admin without a section
    await type(fixture, msg.querySelector('select')!, ALICE.key);
    await type(fixture, msg.querySelector('textarea')!, 'water at the church');
    button(msg, 'Leave message').click();
    await fixture.whenStable();
    expect(api.ran).toEqual([['msg', `${ALICE.key} water at the church`]]);
    expect(msg.querySelector('.reply.failed')?.textContent).toContain('inbox is full');
    expect(msg.querySelector('textarea')!.value).toBe('water at the church');
  });

  it('offers only what the console may run', async () => {
    api.commands = () => of(COMMANDS.filter((c) => c.name === 'comm'));
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    expect([...element.querySelectorAll('h2')].map((h) => h.textContent?.trim())).toEqual([
      'Post to a channel',
    ]);
    expect(element.querySelectorAll('input[type=radio]').length).toBe(1);
  });
});
