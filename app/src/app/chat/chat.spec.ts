import { TestBed } from '@angular/core/testing';

import { FakeBle, NODE_KEY } from '../radio/fake-ble';
import { openScreen } from '../screens.testing';
import { ChatHistory, HISTORY } from './chat-history';

const ERIN = 'e0'.repeat(32);

describe('Chat', () => {
  let ble: FakeBle;

  beforeEach(() => {
    ble = new FakeBle();
    localStorage.clear();
  });

  const open = (path = '/chat', ready = true) => openScreen(path, ble, ready);
  const texts = (page: HTMLElement, selector: string) =>
    [...page.querySelectorAll(selector)].map((e) => e.textContent?.trim());

  /** Wait for the screen to show something, then let it settle. */
  async function shows(fixture: { detectChanges(): void }, check: () => void) {
    await vi.waitFor(() => {
      fixture.detectChanges();
      check();
    });
  }

  it("lists the radio's channels and companions, the node apart", async () => {
    const { page, fixture } = await open();
    await shows(fixture, () => expect(texts(page, '.channels .name')).toHaveLength(3));
    expect(texts(page, '.channels .name')).toEqual([
      'Public',
      '#contingency-wx',
      '#contingency-comm',
    ]);
    // Not the repeater, and not the node.
    expect(texts(page, '.direct .name')).toEqual(['Erin']);
    expect(page.querySelector('.direct')?.textContent).toContain('Ridge Node is the node');
  });

  it('sends a direct message, marked delivered or not', async () => {
    const { page, type, button, fixture } = await open(`/chat/dm/${ERIN}`);
    await shows(fixture, () => expect(page.querySelector('h1')?.textContent).toBe('Erin'));
    type('chat-text', 'are you at the shelter?');
    button('Send').click();
    await shows(fixture, () => expect(texts(page, '.lines .meta')[0]).toContain('Delivered'));
    expect(ble.sent.map(([prefix, text]) => [prefix, text])).toEqual([
      [ERIN.slice(0, 12), 'are you at the shelter?'],
    ]);
    expect(page.querySelector<HTMLTextAreaElement>('[name="chat-text"]')?.value).toBe('');

    ble.ackFrom = null;
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      type('chat-text', 'hello?');
      button('Send').click();
      await vi.advanceTimersByTimeAsync(60_000);
    } finally {
      vi.useRealTimers();
    }
    await shows(fixture, () => expect(texts(page, '.lines .meta')[1]).toContain('Not delivered'));
  });

  it('keeps what others send, unread until opened, but never the node', async () => {
    const { page, fixture } = await open();
    await shows(fixture, () => expect(texts(page, '.direct .name')).toEqual(['Erin']));
    ble.deliver(ERIN, 'we are ok');
    ble.deliver(NODE_KEY, 'inbox: new message from Erin; send inbox to read');
    ble.hear(1, 'Ridge Node', 'Flash Flood Warning: Taylor');
    await shows(fixture, () => expect(texts(page, '.unread')).toEqual(['1', '1']));
    expect(texts(page, '.last')).toContain('we are ok');
    expect(texts(page, '.last')).toContain('Ridge Node: Flash Flood Warning: Taylor');
    expect(page.querySelector('.tabs .badge')?.textContent?.trim()).toBe('2');

    const history = TestBed.inject(ChatHistory);
    expect(Object.keys(history.chats()).sort()).toEqual([
      'ch:#contingency-wx',
      `dm:${ERIN.slice(0, 12)}`,
    ]);
    expect(JSON.parse(localStorage.getItem(HISTORY)!)['ch:#contingency-wx'].lines[0]).toMatchObject(
      {
        from: 'Ridge Node',
        text: 'Flash Flood Warning: Taylor',
      },
    );

    (page.querySelector('a.chat[href*="dm"]') as HTMLAnchorElement).click();
    await shows(fixture, () => expect(page.querySelector('h1')?.textContent).toBe('Erin'));
    expect(texts(page, '.lines .text')).toEqual(['we are ok']);
    expect(history.chats()[`dm:${ERIN.slice(0, 12)}`].unread).toBe(0);
  });

  it('posts to a channel, held to what fits after the radio name', async () => {
    const { page, type, button, fixture } = await open('/chat/channel/%23contingency-comm');
    await shows(fixture, () => expect(button('Send')).toBeTruthy());
    expect(page.querySelector('h1')?.textContent).toBe('#contingency-comm');
    // 133, less "Field T1000: ".
    expect(page.querySelector('.count')?.textContent).toContain('120 characters left');
    type('chat-text', 'x'.repeat(121));
    expect(button('Send').disabled).toBe(true);
    type('chat-text', 'net at 7');
    await shows(fixture, () => expect(button('Send').disabled).toBe(false));
    button('Send').click();
    await shows(fixture, () => expect(texts(page, '.lines .meta')[0]).toContain('Sent'));
    expect(ble.channelSent).toEqual([[3, 'net at 7']]);
  });

  it('keeps chats on the phone, and clears them when asked', async () => {
    localStorage.setItem(
      HISTORY,
      JSON.stringify({
        [`dm:${ERIN.slice(0, 12)}`]: {
          lines: [{ id: 1, mine: true, text: 'still sending', at: 1, status: 'sending' }],
          unread: 0,
        },
        'ch:#contingency-wx': {
          lines: [{ id: 2, mine: false, from: 'Ridge Node', text: 'Wind Advisory', at: 2 }],
          unread: 1,
        },
      }),
    );
    const list = await open('/chat', false);
    expect(texts(list.page, '.channels .name')).toEqual(['#contingency-wx']);
    expect(texts(list.page, '.direct .name')).toEqual([ERIN.slice(0, 12)]);
    TestBed.resetTestingModule();

    const { page, fixture } = await open(`/chat/dm/${ERIN}`, false);
    await shows(fixture, () => expect(texts(page, '.lines .text')).toEqual(['still sending']));
    // Unknown whether it went, once the app had closed.
    expect(texts(page, '.lines .meta')[0]).toContain("Couldn't send");
    expect(page.textContent).toContain('Connect your radio');

    const ask = vi.spyOn(window, 'confirm').mockReturnValue(true);
    [...page.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Clear')!.click();
    ask.mockRestore();
    await shows(fixture, () => expect(page.textContent).toContain('No messages yet.'));
    expect(Object.keys(JSON.parse(localStorage.getItem(HISTORY)!))).toEqual(['ch:#contingency-wx']);
  });
});
