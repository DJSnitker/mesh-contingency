import { FakeBle } from '../radio/fake-ble';
import { openScreen, reply } from '../screens.testing';
import { ADDRESS } from './email-screen';

describe('EmailScreen', () => {
  let ble: FakeBle;

  beforeEach(() => {
    ble = new FakeBle();
    localStorage.clear();
  });

  const open = (ready = true) => openScreen('/email', ble, ready);
  const sent = () => ble.sent.map(([, text]) => text);

  it('asks for the radio and the node first', async () => {
    const { page, button } = await open(false);
    expect(page.textContent).toContain('Connect your radio and pick the node first');
    expect(button('Show them').disabled).toBe(true);
  });

  it('emails the preset contact after asking, and sends nothing when cancelled', async () => {
    ble.node = () => reply('qm');
    const { page, type, press } = await open();
    type('email-text', 'on my way to the shelter');
    await press('Send');
    expect(sent()).toEqual([]);
    expect(page.querySelector('.confirm')?.textContent).toContain(
      'Email this to your preset contact?',
    );
    await press('Cancel');
    expect(page.querySelector('.confirm')).toBeNull();
    expect(sent()).toEqual([]);

    await press('Send');
    await press('Send it');
    expect(sent()).toEqual(['qm on my way to the shelter']);
    expect(page.querySelector('.sent')?.textContent).toBe('Sent to your preset contact.');
  });

  it('emails the group, or an address it checks first', async () => {
    ble.node = (text) => (text.startsWith('emailall') ? reply('emailall') : reply('email'));
    const { page, type, press, button } = await open();
    await press('My group');
    type('email-text', 'we are safe');
    await press('Send');
    await press('Send it');

    await press('An address');
    type('address', 'bob');
    expect(page.textContent).toContain("That isn't an email address the node can send to.");
    expect(button('Send').disabled).toBe(true);
    type('address', 'bob@example.com');
    type('email-text', 'we are safe');
    await press('Send');
    expect(page.querySelector('.confirm')?.textContent).toContain('Email this to bob@example.com?');
    await press('Send it');
    expect(sent()).toEqual(['emailall we are safe', 'email bob@example.com we are safe']);
  });

  it("says why an email wasn't sent", async () => {
    ble.node = () => reply('qm, no internet at the node');
    const { page, type, press } = await open();
    type('email-text', 'on my way');
    await press('Send');
    await press('Send it');
    expect(page.querySelector('.sent')?.textContent).toBe(
      'Not sent: no internet at the node; try again later.',
    );
    expect(page.querySelector<HTMLTextAreaElement>('[name="email-text"]')?.value).toBe('on my way');
  });

  it('shows your addresses, and changes them', async () => {
    ble.node = (text) =>
      ({
        setqm: reply('setqm, none set'),
        addgroup: reply('addgroup, listing them'),
        'setqm dana@example.com': reply('setqm, setting it'),
        'addgroup c@example.com': ['addgroup: c@example.com added (3 in the group)'],
        cleargroup: ['cleargroup: removed 3 address(es)'],
      })[text] ?? [];
    const { page, type, press } = await open();
    await press('Show them');
    expect(page.querySelector('.qm')?.textContent).toBe('none set');
    expect(page.querySelector('.group')?.textContent).toBe('a@example.com, b@example.com');

    type('qm-address', 'dana@example.com');
    await press('Set it');
    expect(page.querySelector('.qm')?.textContent).toBe('dana@example.com');

    type('group-address', 'c@example.com');
    await press('Add it');
    expect(page.querySelector('.group')?.textContent).toBe(
      'a@example.com, b@example.com, c@example.com',
    );

    const ask = vi.spyOn(window, 'confirm').mockReturnValue(true);
    await press('Clear the group');
    expect(page.querySelector('.group')?.textContent).toBe('no addresses');
    expect(page.querySelector('.changed')?.textContent).toBe(
      'Removed 3 address(es) from your group.',
    );
    ask.mockRestore();
    expect(sent()).toEqual([
      'setqm',
      'addgroup',
      'setqm dana@example.com',
      'addgroup c@example.com',
      'cleargroup',
    ]);
  });

  it('checks addresses as the bot does', () => {
    expect(ADDRESS.test('erin@example.com')).toBe(true);
    for (const bad of ['bob', '-x@example.com', 'a@b', 'a b@example.com']) {
      expect(ADDRESS.test(bad), bad).toBe(false);
    }
  });
});
