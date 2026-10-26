import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { afterEach, vi } from 'vitest';

import { Api } from './api';
import { DirectThread } from './dm';
import { Unread } from './unread';
import { FakeApi } from '../testing/fakes';

const ALICE = 'a1'.repeat(32);

describe('DirectThread', () => {
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

  async function render(key = ALICE) {
    const fixture = TestBed.createComponent(DirectThread);
    fixture.componentRef.setInput('key', key);
    await fixture.whenStable();
    return fixture;
  }

  function button(element: HTMLElement): HTMLButtonElement {
    return [...element.querySelectorAll('button')].find((b) => b.textContent?.includes('Send'))!;
  }

  async function type(fixture: Awaited<ReturnType<typeof render>>, text: string) {
    const box = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
    box.value = text;
    box.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    return box;
  }

  it("shows the chat oldest first, the console's on the right with its status", async () => {
    vi.spyOn(Date, 'now').mockReturnValue(1_020_000);
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector('h1')?.textContent).toBe('Alice');
    const lines = [...element.querySelectorAll('.lines li')].map((li) => ({
      mine: li.classList.contains('mine'),
      text: li.querySelector('.text')?.textContent,
      meta: li.querySelector('.meta')?.textContent?.replace(/\s+/g, ' ').trim(),
    }));
    expect(lines).toEqual([
      { mine: true, text: 'can you check the gauge?', meta: '2m ago · Delivered' },
      { mine: false, text: 'on my way', meta: '1m ago · 1 hop · SNR 5.5 dB' },
    ]);
  });

  it('sends as the node, then shows it sending and empties the box', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    expect(button(element).disabled).toBe(true);
    const box = await type(fixture, '  thanks  ');
    expect(element.querySelector('.count')?.textContent).toContain('6 / 133');
    button(element).click();
    await fixture.whenStable();
    expect(api.messaged).toEqual([[ALICE, 'thanks']]);
    expect(api.ran).toEqual([]); // not a command
    expect(box.value).toBe('');
    const last = [...element.querySelectorAll('.lines li')].at(-1)!;
    expect(last.textContent).toContain('thanks');
    expect(last.textContent).toContain('Sending…');
  });

  it('keeps the text and says why when the bot refuses', async () => {
    api.messageContact = () =>
      throwError(
        () =>
          new HttpErrorResponse({
            status: 404,
            error: { error: 'the radio has no such contact' },
          }),
      );
    const fixture = await render();
    const box = await type(fixture, 'hello');
    button(fixture.nativeElement).click();
    await fixture.whenStable();
    expect(fixture.nativeElement.querySelector('.problem')?.textContent).toContain(
      'no such contact',
    );
    expect(box.value).toBe('hello');
  });

  it("won't send more than one message holds", async () => {
    const fixture = await render();
    await type(fixture, 'x'.repeat(134));
    expect(fixture.nativeElement.querySelector('.count.over')).not.toBeNull();
    expect(button(fixture.nativeElement).disabled).toBe(true);
  });

  it('marks the replies read as it reads them', async () => {
    const unread = TestBed.inject(Unread);
    unread.refresh();
    expect(unread.dmTotal()).toBe(1);
    await render();
    expect(unread.dmTotal()).toBe(0);
  });

  it('shows a contact with no chat yet', async () => {
    api.contactMessages = (key) => of({ key, name: 'Bob', keep: 200, messages: [], heard: 0 });
    const fixture = await render('b0'.repeat(32));
    expect(fixture.nativeElement.textContent).toContain('No messages yet');
    expect(fixture.nativeElement.querySelector('#send-title')?.textContent).toContain(
      'Message Bob',
    );
  });

  it("says when the chat can't be read", async () => {
    api.contactMessages = () => throwError(() => new Error('down'));
    const fixture = await render();
    expect(fixture.nativeElement.querySelector('.problem')?.textContent).toContain(
      "can't read the chat",
    );
  });
});
