import { TestBed } from '@angular/core/testing';

import { FakeBle, NODE_KEY } from '../radio/fake-ble';
import { openScreen } from '../screens.testing';
import { ChatHistory, HISTORY } from './chat-history';
import { when } from './chat-list';
import { heard } from './contact-list';

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

  it("lists the radio's channels under Channels, and its companions under Contacts", async () => {
    const { page, fixture } = await open('/chat/channels');
    await shows(fixture, () => expect(texts(page, '.rows .name')).toHaveLength(3));
    expect(texts(page, '.rows .name')).toEqual(['Public', '#contingency-wx', '#contingency-comm']);
    expect(texts(page, '.rows .sub')).toEqual(['No messages', 'No messages', 'No messages']);

    (page.querySelector('a[href="#/chat/contacts"]') as HTMLAnchorElement).click();
    // Not the repeater, and not the node.
    await shows(fixture, () => expect(texts(page, '.direct .name')).toEqual(['Erin']));
    expect(page.querySelector('.channels')).toBeNull();
    expect(page.querySelector('.direct')?.textContent).toContain('Ridge Node is the node');
  });

  it('shows that the contacts are being read until they are, and reads them once', async () => {
    ble.contactsMs = 300;
    const { page, fixture } = await open('/chat/contacts');
    await shows(fixture, () =>
      expect(page.querySelector('[role="status"]')?.textContent).toContain('Reading the contacts'),
    );
    expect(page.querySelector('.direct')).toBeNull();
    await shows(fixture, () => expect(texts(page, '.direct .name')).toEqual(['Erin']));
    expect(page.querySelector('[role="status"]')).toBeNull();

    // Chat, and back: read once while the radio stays connected.
    (page.querySelector('a[href="#/chat"]') as HTMLAnchorElement).click();
    await shows(fixture, () => expect(page.textContent).toContain('No chats yet'));
    (page.querySelector('a[href="#/chat/contacts"]') as HTMLAnchorElement).click();
    await shows(fixture, () => expect(texts(page, '.direct .name')).toEqual(['Erin']));
    expect(ble.commands().filter((c) => c === 4)).toHaveLength(1); // GetContacts
  });

  it('starts a chat from a contact, which then shows under Chat', async () => {
    const { page, type, button, fixture } = await open('/chat');
    await shows(fixture, () => expect(page.textContent).toContain('No chats yet'));
    (page.querySelector('a[href="#/chat/contacts"]') as HTMLAnchorElement).click();
    await shows(fixture, () => expect(texts(page, '.direct .name')).toEqual(['Erin']));
    (page.querySelector('.direct a') as HTMLAnchorElement).click();
    await shows(fixture, () => expect(page.querySelector('h1')?.textContent).toBe('Erin'));
    type('chat-text', 'checking in');
    button('Send').click();
    await shows(fixture, () => expect(texts(page, '.lines .meta')[0]).toContain('Delivered'));

    (page.querySelector('a[aria-label="All chats"]') as HTMLAnchorElement).click();
    await shows(fixture, () => expect(texts(page, '.rows .name')).toEqual(['Erin']));
    expect(texts(page, '.rows .sub')).toEqual(['You: checking in']);
  });

  it('finds contacts by name, once there are many', async () => {
    ble.contacts.push(
      ...['Ann', 'Bo', 'Cy', 'Di', 'Ed', 'Flo', 'Gus'].map((name, i) => ({
        name,
        publicKey: (i + 0x20).toString(16).repeat(32),
        type: 1,
      })),
    );
    const { page, type, fixture } = await open('/chat/contacts');
    await shows(fixture, () => expect(texts(page, '.direct .name')).toHaveLength(8));
    type('find', 'zz');
    await shows(fixture, () =>
      expect(page.querySelector('.direct')?.textContent).toContain('None by that name.'),
    );
    type('find', 'ER');
    await shows(fixture, () => expect(texts(page, '.direct .name')).toEqual(['Erin']));
  });

  it('says when a contact was heard and how far it is', () => {
    const now = 1_790_000_000_000;
    const contact = { publicKey: '', name: 'Erin', type: 1, lastAdvert: 0 };
    expect(heard({ ...contact, hops: null }, now)).toBe('no path yet');
    expect(heard({ ...contact, hops: 0, lastAdvert: now / 1000 - 300 }, now)).toBe(
      'Heard 5 min ago · direct',
    );
    expect(heard({ ...contact, hops: 1, lastAdvert: now / 1000 - 7200 }, now)).toBe(
      'Heard 2 h ago · 1 hop',
    );
    expect(heard({ ...contact, hops: 3, lastAdvert: now / 1000 - 3 * 86400 }, now)).toBe(
      'Heard 3 days ago · 3 hops',
    );
    expect(when(now, now)).toBe('h:mm a');
    expect(when(now - 86_400_000, now)).toBe('MMM d');
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

  it('sends from a kept chat opened by its key prefix', async () => {
    const { page, type, button, fixture } = await open(`/chat/dm/${ERIN.slice(0, 12)}`);
    await shows(fixture, () => expect(page.querySelector('h1')?.textContent).toBe('Erin'));
    type('chat-text', 'still there?');
    button('Send').click();
    await shows(fixture, () => expect(texts(page, '.lines .meta')[0]).toContain('Delivered'));
    expect(ble.sent.map(([prefix, text]) => [prefix, text])).toEqual([
      [ERIN.slice(0, 12), 'still there?'],
    ]);
  });

  it("can't send to a contact the radio no longer has", async () => {
    const { page, type, button, fixture } = await open(`/chat/dm/${'ab'.repeat(6)}`);
    await shows(fixture, () => expect(page.textContent).toContain('no contact abababababab'));
    type('chat-text', 'hello?');
    expect(button('Send').disabled).toBe(true);
  });

  it('keeps what others send, unread until opened, but never the node', async () => {
    const { page, fixture } = await open();
    await shows(fixture, () => expect(page.textContent).toContain('No chats yet'));
    ble.deliver(ERIN, 'we are ok');
    ble.deliver(NODE_KEY, 'inbox: new message from Erin; send inbox to read');
    ble.hear(1, 'Ridge Node', 'Flash Flood Warning: Taylor');
    await shows(fixture, () => expect(texts(page, '.rows .unread')).toEqual(['1']));
    expect(texts(page, '.rows .name')).toEqual(['Erin']);
    expect(texts(page, '.rows .sub')).toEqual(['we are ok']);
    // The tab bar counts both; the Chat and Channels tabs, theirs.
    expect(page.querySelector('.tabs .badge')?.textContent?.trim()).toBe('2');
    expect(texts(page, 'mc-chat-tabs .badge')).toEqual(['1', '1']);

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

    (page.querySelector('.rows a[href*="dm"]') as HTMLAnchorElement).click();
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
    // Erin by her key, the radio not being there to name her.
    expect(texts(list.page, '.rows .name')).toEqual([ERIN.slice(0, 12)]);
    (list.page.querySelector('a[href="#/chat/channels"]') as HTMLAnchorElement).click();
    await shows(list.fixture, () =>
      expect(texts(list.page, '.rows .name')).toEqual(['#contingency-wx']),
    );
    expect(texts(list.page, '.rows .unread')).toEqual(['1']);
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
