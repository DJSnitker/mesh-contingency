import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { afterEach, vi } from 'vitest';

import { Api } from './api';
import { Chat } from './chat';
import { SEEN, Unread } from './unread';
import { ALICE_MESSAGES, CONVERSATIONS, FakeApi, OVERVIEW } from '../testing/fakes';

describe('Chat', () => {
  let api: FakeApi;

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: Api, useValue: api }],
    });
  });

  async function render(): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(Chat);
    await fixture.whenStable();
    return fixture.nativeElement;
  }

  function rows(element: HTMLElement) {
    return [...element.querySelectorAll('.rows a')].map((a) => ({
      name: a.querySelector('.name')?.textContent?.trim(),
      side: a.querySelector('.side')?.textContent?.trim() ?? null,
      sub: a.querySelector('.sub')?.textContent?.replace(/\s+/g, ' ').trim(),
      href: a.getAttribute('href'),
      unread: a.querySelector('.unread')?.textContent ?? null,
    }));
  }

  it("lists the console's chats, each with its newest message and unread replies", async () => {
    vi.spyOn(Date, 'now').mockReturnValue(1_200_000);
    TestBed.inject(Unread).refresh();
    const element = await render();
    expect(rows(element)).toEqual([
      {
        name: 'Alice',
        side: '4m ago',
        sub: 'on my way',
        href: `/chat/dm/${'a1'.repeat(32)}`,
        unread: '1',
      },
    ]);
    expect(element.textContent).toContain('never kept');
    const tabs = [...element.querySelectorAll('mc-chat-tabs nav a')].map((a) =>
      a.textContent?.replace(/\s+/g, ' ').trim(),
    );
    expect(tabs).toEqual(['Chats 1', 'Channels 1', 'Contacts']);
  });

  it("says when the console's message wasn't delivered", async () => {
    const last = { ...ALICE_MESSAGES.messages![1], status: 'not delivered' as const };
    api.conversations = () => of([{ ...CONVERSATIONS[0], last, heard: 0 }]);
    const element = await render();
    expect(rows(element)[0].sub).toBe('You: can you check the gauge? · not delivered');
    expect(rows(element)[0].unread).toBeNull();
  });

  it('counts only replies since the chat was last seen', async () => {
    localStorage.setItem(
      SEEN,
      JSON.stringify({ started: OVERVIEW.started, slots: {}, dms: { ['a1'.repeat(32)]: 1 } }),
    );
    TestBed.inject(Unread).refresh();
    const element = await render();
    expect(rows(element)[0].unread).toBeNull();
  });

  it('points to Contacts when there are no chats yet', async () => {
    api.conversations = () => of([]);
    const element = await render();
    expect(element.querySelector('.panel a[href="/chat/contacts"]')).not.toBeNull();
  });

  it("says when the bot keeps none, or can't be read", async () => {
    api.conversations = () => of(null);
    expect((await render()).textContent).toContain("isn't keeping the console's chats");
    api.conversations = () => throwError(() => new Error('down'));
    expect((await render()).querySelector('.problem')?.textContent).toContain(
      "can't read the console's conversations",
    );
  });
});
