import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { afterEach, vi } from 'vitest';

import { Api } from './api';
import { Chat } from './chat';
import { SEEN, Unread } from './unread';
import { CHANNELS, FakeApi, OVERVIEW } from '../testing/fakes';

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

  it('lists the channels in use, the last heard on first, each opening its thread', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(1_200_000);
    const element = await render();
    expect(element.querySelector('h2 .muted')?.textContent?.trim()).toBe('3 of 5 slots in use');
    const rows = [...element.querySelectorAll('.rows a')].map((a) => ({
      name: a.querySelector('.name')?.firstChild?.textContent?.trim(),
      uses: [...a.querySelectorAll('.badge')].map((b) => b.textContent),
      side: a.querySelector('.side')?.textContent?.trim() ?? null,
      sub: a.querySelector('.sub')?.textContent?.replace(/\s+/g, ' ').trim(),
      href: a.getAttribute('href'),
      unread: a.querySelector('.unread')?.textContent ?? null,
    }));
    expect(rows).toEqual([
      {
        name: 'Public',
        uses: [],
        side: '5m ago',
        sub: 'the usual Public channel: everyone · 2 messages',
        href: '/chat/channel/0',
        unread: '1',
      },
      {
        name: '#contingency-wx',
        uses: ['alert', 'automatic alerts'],
        side: null,
        sub: 'hashtag: anyone who adds the same name',
        href: '/chat/channel/1',
        unread: null,
      },
      {
        name: 'Family',
        uses: [],
        side: null,
        sub: 'private: only radios given its key',
        href: '/chat/channel/2',
        unread: null,
      },
    ]);
  });

  it("says when it can't read the channels", async () => {
    api.channels = () => throwError(() => new Error('down'));
    const element = await render();
    expect(element.querySelector('.problem')?.textContent).toContain(
      "can't read the radio's channels",
    );
    expect(element.querySelector('.loading')).toBeNull();
  });

  it('counts as unread only what came since the channel was last seen, in this run of the bot', async () => {
    localStorage.setItem(SEEN, JSON.stringify({ started: OVERVIEW.started, slots: { 0: 1 } }));
    let element = await render();
    expect(element.querySelector('.unread')).toBeNull(); // the one heard was seen

    api.channels = () => of(CHANNELS.map((c) => (c.slot === 0 ? { ...c, heard: 4 } : c)));
    TestBed.inject(Unread).refresh();
    element = await render();
    expect(element.querySelector('.unread')?.textContent).toBe('3');

    // A restart of the bot starts the counts again.
    api.overview = () => of({ ...OVERVIEW, started: OVERVIEW.started + 60 });
    api.channels = () => of(CHANNELS);
    TestBed.inject(Unread).refresh();
    element = await render();
    expect(element.querySelector('.unread')?.textContent).toBe('1');
  });
});
