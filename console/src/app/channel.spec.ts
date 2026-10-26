import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { afterEach, vi } from 'vitest';

import { Api } from './api';
import { CHANNEL_REFRESH_MS, ChannelThread } from './channel';
import { Unread } from './unread';
import { FakeApi, PUBLIC_MESSAGES } from '../testing/fakes';

describe('ChannelThread', () => {
  let api: FakeApi;

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: Api, useValue: api }],
    });
  });

  async function render(slot: number) {
    const fixture = TestBed.createComponent(ChannelThread);
    fixture.componentRef.setInput('slot', String(slot));
    await fixture.whenStable();
    return fixture;
  }

  function button(element: HTMLElement, label: string): HTMLButtonElement {
    return [...element.querySelectorAll('button')].find((b) => b.textContent?.includes(label))!;
  }

  it("shows the channel's messages oldest first, the node's own on the right", async () => {
    vi.spyOn(Date, 'now').mockReturnValue(1_200_000);
    const asked: number[] = [];
    api.channelMessages = (slot) => {
      asked.push(slot);
      return of({ ...PUBLIC_MESSAGES, slot });
    };
    const element: HTMLElement = (await render(0)).nativeElement;
    expect(asked).toEqual([0]);
    expect(element.querySelector('h1')?.textContent).toBe('Public');
    expect(element.querySelector('.title .muted')?.textContent).toContain('slot 0');
    const lines = [...element.querySelectorAll('.lines li')].map((li) => ({
      from: li.querySelector('.from')?.textContent?.trim() ?? null,
      mine: li.classList.contains('mine'),
      text: li.querySelector('.text')?.textContent,
      meta: li.querySelector('.meta')?.textContent?.replace(/\s+/g, ' ').trim(),
    }));
    expect(lines).toEqual([
      { from: 'Alice', mine: false, text: 'anyone on?', meta: '10m ago · 2 hops · SNR 6.5 dB' },
      { from: null, mine: true, text: 'net at 7', meta: '5m ago · this node' },
    ]);
    expect(element.querySelector('a[aria-label="All channels"]')?.getAttribute('href')).toBe(
      '/contacts/channels',
    );
    expect(element.querySelector('#post-title')?.textContent).toContain('Post to Public');
  });

  it('reads the messages again every 10 s', async () => {
    const asked: number[] = [];
    api.channelMessages = (slot) => {
      asked.push(slot);
      return of({ ...PUBLIC_MESSAGES, slot });
    };
    vi.useFakeTimers();
    const fixture = TestBed.createComponent(ChannelThread);
    fixture.componentRef.setInput('slot', '0');
    fixture.detectChanges();
    expect(asked.length).toBe(1);
    await vi.advanceTimersByTimeAsync(CHANNEL_REFRESH_MS);
    expect(asked.length).toBe(2);
    fixture.destroy();
    await vi.advanceTimersByTimeAsync(3 * CHANNEL_REFRESH_MS);
    expect(asked.length).toBe(2);
  });

  it('posts to any channel as this node, then empties the box and reads it again', async () => {
    let reads = 0;
    api.channelMessages = (slot) => {
      reads++;
      return of({ ...PUBLIC_MESSAGES, slot });
    };
    const fixture = await render(2); // Family: no command posts there
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector('#post-title')?.textContent).toContain('Post to Family');
    const box = element.querySelector('textarea')!;
    expect(button(element, 'Post').disabled).toBe(true);
    box.value = '  supper at 6  ';
    box.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    expect(element.querySelector('.count')?.textContent).toContain('11 / 119');
    button(element, 'Post').click();
    await fixture.whenStable();
    expect(api.posted).toEqual([[2, 'supper at 6']]);
    expect(api.ran).toEqual([]); // not a command
    expect(element.querySelector('[role=status]')?.textContent).toContain('Posted to Family.');
    expect(box.value).toBe('');
    expect(reads).toBe(2);
  });

  it('keeps the text and says why when the bot refuses', async () => {
    api.postToChannel = () =>
      throwError(
        () =>
          new HttpErrorResponse({
            status: 502,
            error: { error: 'radio rejected channel message 1 of 1: busy' },
          }),
      );
    const fixture = await render(0);
    const element: HTMLElement = fixture.nativeElement;
    const box = element.querySelector('textarea')!;
    box.value = 'hello';
    box.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    button(element, 'Post').click();
    await fixture.whenStable();
    expect(element.querySelector('.problem')?.textContent).toContain('radio rejected');
    expect(box.value).toBe('hello');
  });

  it("won't post more than one channel message holds", async () => {
    const fixture = await render(1);
    const element: HTMLElement = fixture.nativeElement;
    const box = element.querySelector('textarea')!;
    box.value = 'x'.repeat(120);
    box.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    expect(element.querySelector('.count.over')).not.toBeNull();
    expect(element.textContent).toContain('shorten it');
    expect(button(element, 'Post').disabled).toBe(true);
  });

  it('marks the channel read as its messages are read', async () => {
    TestBed.inject(Unread).refresh(); // Public: 1 heard, none seen
    expect(TestBed.inject(Unread).unread(0)).toBe(1);
    await render(0);
    expect(TestBed.inject(Unread).unread(0)).toBe(0);
  });

  it('says when nothing was heard, when none are kept, and when it fails', async () => {
    api.channelMessages = (slot) => of({ slot, keep: 200, messages: [], heard: 0 });
    let element: HTMLElement = (await render(0)).nativeElement;
    expect(element.querySelector('.thread')?.textContent).toContain(
      'Nothing heard on this channel',
    );

    api.channelMessages = (slot) => of({ slot, keep: null, messages: null, heard: null });
    element = (await render(0)).nativeElement;
    expect(element.querySelector('.thread')?.textContent).toContain(
      "The bot isn't keeping channel messages.",
    );

    api.channelMessages = () => throwError(() => new Error('down'));
    element = (await render(0)).nativeElement;
    expect(element.querySelector('.thread .problem')?.textContent).toContain(
      "can't read the channel's messages",
    );
  });
});
