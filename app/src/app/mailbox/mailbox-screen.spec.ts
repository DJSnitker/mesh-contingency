import { CHOSEN } from '../node/node-link';
import { FakeBle } from '../radio/fake-ble';
import { openScreen, reply } from '../screens.testing';
import { passphraseProblem, recipient } from './mailbox-screen';

describe('MailboxScreen', () => {
  let ble: FakeBle;

  beforeEach(() => {
    ble = new FakeBle();
    localStorage.clear();
  });

  const open = (ready = true) => openScreen('/mailbox', ble, ready);

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
    // Folded away until opened.
    const section = page.querySelector<HTMLDetailsElement>('details.passphrase')!;
    expect(section.open).toBe(false);
    section.querySelector('summary')!.click();
    expect(section.open).toBe(true);
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
