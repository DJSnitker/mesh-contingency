import { FakeBle } from '../radio/fake-ble';
import { openScreen, reply } from '../screens.testing';
import { QUICK } from './checkins-screen';

describe('CheckinsScreen', () => {
  let ble: FakeBle;

  beforeEach(() => {
    ble = new FakeBle();
    localStorage.clear();
  });

  const open = (ready = true) => openScreen('/checkins', ble, ready);

  it('asks for the radio and the node first', async () => {
    const { page, button } = await open(false);
    expect(page.textContent).toContain('Connect your radio and pick the node first');
    expect(button("I'm ok").disabled).toBe(true);
  });

  it('checks in with one press', async () => {
    ble.node = () => reply('ok');
    const { page, press } = await open();
    expect([...page.querySelectorAll('.quick button')].map((b) => b.textContent?.trim())).toEqual(
      QUICK.map((q) => q.label),
    );
    await press("I'm ok");
    await press('Need help');
    expect(ble.sent.map(([, text]) => text)).toEqual(['ok', 'ok need help']);
    expect(page.querySelector('.checked-in')?.textContent).toBe('Checked in as Dana: need help.');
  });

  it('checks in in your own words, held to what fits', async () => {
    ble.node = () => reply('ok, with how you are');
    const { page, type, press, button } = await open();
    type('status', 'need water');
    await press('Check in');
    expect(ble.sent.map(([, text]) => text)).toEqual(['ok need water']);
    expect(page.querySelector('.checked-in')?.textContent).toBe('Checked in as Dana: need water.');
    expect(page.querySelector<HTMLInputElement>('[name="status"]')?.value).toBe('');

    type('status', 'x'.repeat(131));
    expect(button('Check in').disabled).toBe(true);
  });

  it("looks up someone's check-ins, a status with ; in it kept whole", async () => {
    ble.node = () => reply('status, several, one with ; in it');
    const { page, type, press } = await open();
    type('who', 'n');
    await press('Look up');
    expect(ble.sent.map(([, text]) => text)).toEqual(['status n']);
    const entries = [...page.querySelectorAll('.entries li')].map((li) =>
      li.textContent?.replace(/\s+/g, ' ').trim(),
    );
    expect(entries).toEqual(['Erin, just now fine; at the shelter', 'Dana, just now ok']);
  });

  it('looks up your own, and says when there is none', async () => {
    ble.node = () => reply('status, your own before checking in');
    const { page, press } = await open();
    await press('Look up');
    expect(ble.sent.map(([, text]) => text)).toEqual(['status']);
    expect(page.querySelector('.none')?.textContent?.trim()).toBe("You haven't checked in yet.");
  });

  it('says when nobody by that name has checked in', async () => {
    ble.node = () => reply('status, nobody by that name');
    const { page, type, press } = await open();
    type('who', 'Zed');
    await press('Look up');
    expect(page.querySelector('.none')?.textContent?.trim()).toBe('No check-in from Zed.');
  });
});
