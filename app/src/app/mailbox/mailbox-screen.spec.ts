import { TestBed } from '@angular/core/testing';
import { provideRouter, Router, withHashLocation } from '@angular/router';

import fixtures from '../../../../tests/fixtures/app_replies.json';
import { App } from '../app';
import { routes } from '../app.routes';
import { CHOSEN, NodeLink, TIMING } from '../node/node-link';
import { BLE } from '../radio/ble';
import { FakeBle, NODE_KEY } from '../radio/fake-ble';
import { REMEMBERED } from '../radio/radio';
import { passphraseProblem, recipient } from './mailbox-screen';

/** What the bot really replies, from the shared fixtures. */
function reply(name: string): string[] {
  const found = fixtures.cases.find((c) => c.name === name);
  if (!found) {
    throw new Error(`no fixture ${name}`);
  }
  return found.reply;
}

describe('MailboxScreen', () => {
  let ble: FakeBle;

  beforeEach(() => {
    ble = new FakeBle();
    localStorage.clear();
  });

  /** The Mailbox screen, with the radio connected and the node picked (unless `ready` is false). */
  async function open(ready = true) {
    if (ready) {
      localStorage.setItem(
        REMEMBERED,
        JSON.stringify({ deviceId: 'AA:BB:CC:DD:EE:FF', name: 'Field T1000' }),
      );
      localStorage.setItem(CHOSEN, JSON.stringify({ publicKey: NODE_KEY, name: 'Ridge Node' }));
    }
    TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter(routes, withHashLocation()),
        { provide: BLE, useValue: ble },
        { provide: TIMING, useValue: { firstReplyMs: 2000, quietMs: 50, partsMs: 200 } },
      ],
    });
    const fixture = TestBed.createComponent(App);
    await TestBed.inject(Router).navigateByUrl('/mailbox');
    await fixture.whenStable();
    const page = fixture.nativeElement as HTMLElement;
    const link = TestBed.inject(NodeLink);
    if (ready) {
      await vi.waitFor(() => expect(link.ready()).toBe(true));
    }
    const settle = async () => {
      await vi.waitFor(() => expect(link.ready()).toBe(true));
      fixture.detectChanges();
      await fixture.whenStable();
    };
    const type = (name: string, text: string) => {
      const field = page.querySelector<HTMLInputElement>(`[name="${name}"]`)!;
      field.value = text;
      field.dispatchEvent(new Event('input'));
      fixture.detectChanges();
    };
    const button = (text: string) =>
      [...page.querySelectorAll('button')].find((b) => b.textContent?.trim().startsWith(text))!;
    /** Press a button by its text, and wait for the node's answer. */
    const press = async (text: string) => {
      const found = button(text);
      expect(found, `a "${text}" button`).toBeTruthy();
      found.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
      await settle();
    };
    return { page, link, type, press, button, fixture };
  }

  it('asks for the radio and the node first', async () => {
    const { page, button } = await open(false);
    expect(page.textContent).toContain('Connect your radio and pick the node first');
    expect(button('Open inbox').disabled).toBe(true);
  });

  it('opens an empty inbox', async () => {
    ble.node = () => reply('inbox, no messages');
    const { page, press } = await open();
    await press('Open inbox');
    expect(page.querySelector('.result')?.textContent).toContain('No messages.');
    expect(ble.sent.map(([, text]) => text)).toEqual(['inbox']);
  });

  it("shows each message whole, though each came in parts, and doesn't keep them", async () => {
    ble.node = () => reply('inbox, two long messages, each in numbered parts');
    const { page, link, press } = await open();
    await press('Open inbox');
    const messages = [...page.querySelectorAll('.messages li')].map((li) => li.textContent?.trim());
    expect(messages).toHaveLength(2);
    expect(messages[0]).toContain('Erin, just now');
    expect(messages[0]).toContain('meet us at the church on main street by six');
    expect(messages[1]).toContain('so bring any you can spare');
    expect(link.exchange()).toMatchObject({ messages: [], text: null });
  });

  it('opens sealed messages with the passphrase, never showing it', async () => {
    ble.node = (text) =>
      text === 'inbox'
        ? reply('inbox, sealed messages waiting')
        : reply('inbox, sealed messages opened');
    const { page, link, type, press } = await open();
    await press('Open inbox');
    expect(page.querySelector('.result')?.textContent).toContain(
      '1 sealed message(s), from Erin just now',
    );

    type('inbox-passphrase', 'correcthorse12');
    await press('Open inbox');
    expect(ble.sent.map(([, text]) => text)).toEqual(['inbox', 'inbox correcthorse12']);
    expect(page.querySelector('.messages')?.textContent).toContain('meet at noon');
    expect(link.exchange()?.label).toBe('inbox');
    expect(page.textContent).not.toContain('correcthorse12');
    expect(localStorage.getItem(CHOSEN)).not.toContain('correcthorse12');
  });

  it('says a wrong passphrase as the node does', async () => {
    ble.node = () => reply('inbox, wrong passphrase');
    const { page, type, press } = await open();
    type('inbox-passphrase', 'wronghorse123');
    await press('Open inbox');
    expect(page.querySelector('.inbox .said')?.textContent).toBe('inbox: wrong passphrase');
  });

  it('goes to the next page', async () => {
    ble.node = () => reply('inbox, a page of a longer one');
    const { page, press } = await open();
    await press('Open inbox');
    expect(page.querySelectorAll('.messages li')).toHaveLength(7);
    expect(page.textContent).toContain('Page 1 of 2');
    await press('Next page');
    expect(ble.sent.map(([, text]) => text)).toEqual(['inbox', 'inbox 2']);
  });

  it('clears the messages read, and all after asking', async () => {
    ble.node = (text) =>
      text === 'clearinbox'
        ? reply('clearinbox, keeping one that came since')
        : reply('clearinbox all');
    const { page, press } = await open();
    await press('Clear the ones read');
    expect(page.querySelector('.cleared')?.textContent).toBe(
      'Deleted 1 message(s); 1 new one(s) kept, not read yet.',
    );

    const ask = vi.spyOn(window, 'confirm').mockReturnValue(false);
    await press('Clear all');
    expect(ble.sent.map(([, text]) => text)).toEqual(['clearinbox']);
    ask.mockReturnValue(true);
    await press('Clear all');
    expect(ble.sent.map(([, text]) => text)).toEqual(['clearinbox', 'clearinbox all']);
    expect(page.querySelector('.cleared')?.textContent).toBe('Deleted 2 message(s).');
    ask.mockRestore();
  });

  it('leaves a message, putting a name with spaces in ( )', async () => {
    ble.node = () => ['msg: saved for Ridge Base (1 in their inbox)'];
    const { page, type, press } = await open();
    type('msg-to', 'Ridge Base');
    type('msg-text', 'are you ok?');
    await press('Leave it');
    expect(ble.sent.map(([, text]) => text)).toEqual(['msg (Ridge Base) are you ok?']);
    expect(page.querySelector('.sent')?.textContent).toBe(
      'Left for Ridge Base (1 in their inbox).',
    );
    expect(page.querySelector<HTMLTextAreaElement>('[name="msg-text"]')?.value).toBe('');
  });

  it("says why a message wasn't left, and won't send one too long", async () => {
    ble.node = () => reply('msg, no such user');
    const { page, type, press, button } = await open();
    type('msg-to', 'Zed');
    type('msg-text', 'hello');
    await press('Leave it');
    expect(page.querySelector('.sent')?.textContent).toBe(
      'msg: no user Zed; put a name with spaces in ( )',
    );

    type('msg-text', 'x'.repeat(130));
    expect(page.querySelector('.send .count')?.textContent).toContain('-');
    expect(button('Leave it').disabled).toBe(true);
  });

  it('sets a passphrase, asking first when sealed messages would be lost', async () => {
    let confirmed = false;
    ble.node = () => {
      const answer = confirmed
        ? reply('setpass, confirmed')
        : reply('setpass, asking first when sealed messages would be lost');
      confirmed = true;
      return answer;
    };
    const { page, link, type, press, button } = await open();
    type('new-passphrase', 'batterystaple9');
    expect(button('Set it').disabled).toBe(true);
    type('new-passphrase-again', 'batterystaple9');
    await press('Set it');
    expect(page.querySelector('.passphrase')?.textContent).toContain(
      '1 sealed message(s) that only your old passphrase opens',
    );

    await press('Set it, and delete them');
    expect(ble.sent.map(([, text]) => text)).toEqual([
      'setpass batterystaple9',
      'setpass batterystaple9',
    ]);
    expect(page.querySelector('.set')?.textContent).toContain(
      '1 message(s) sealed with the old one were deleted',
    );
    expect(page.querySelector<HTMLInputElement>('[name="new-passphrase"]')?.value).toBe('');
    expect(link.exchange()?.label).toBe('setpass');
  });
});

describe('the mailbox helpers', () => {
  it('puts a name with spaces in ( )', () => {
    expect(recipient(' Erin ')).toBe('Erin');
    expect(recipient('Ridge Base 1')).toBe('(Ridge Base 1)');
  });

  it('checks a new passphrase as the bot does', () => {
    expect(passphraseProblem('short', 'short')).toContain('12 to 16');
    expect(passphraseProblem('has a space in', 'has a space in')).toContain('spaces');
    expect(passphraseProblem('correcthorse12', 'correcthorse13')).toContain("don't match");
    expect(passphraseProblem('correcthorse12', 'correcthorse12')).toBeNull();
  });
});
