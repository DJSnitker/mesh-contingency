import { TestBed } from '@angular/core/testing';
import { provideRouter, Router, withHashLocation } from '@angular/router';

import { App } from './app';
import { routes, TABS } from './app.routes';
import { BLE } from './radio/ble';
import { FakeBle, NODE_KEY } from './radio/fake-ble';
import { REMEMBERED } from './radio/radio';

describe('App', () => {
  let ble: FakeBle;

  beforeEach(() => {
    ble = new FakeBle();
    localStorage.clear();
  });

  async function open(path: string) {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter(routes, withHashLocation()), { provide: BLE, useValue: ble }],
    });
    const fixture = TestBed.createComponent(App);
    await TestBed.inject(Router).navigateByUrl(path);
    await fixture.whenStable();
    const page = fixture.nativeElement as HTMLElement;
    /** Press a button by its text, and wait for a panel (the radio's) to show `then`. */
    const press = async (text: string, then: string, panel = '.radio') => {
      const button = [...page.querySelectorAll('button')].find((b) =>
        b.textContent?.includes(text),
      );
      expect(button, `a "${text}" button`).toBeTruthy();
      button!.click();
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(page.querySelector(panel)?.textContent).toContain(then);
      });
    };
    return Object.assign(page, { press, fixture });
  }

  it('has a tab for each main screen, in order', async () => {
    const page = await open('/');
    const tabs = [...page.querySelectorAll('.tabs a')].map((a) => a.textContent?.trim());
    expect(tabs).toEqual(TABS.map((tab) => tab.label));
  });

  it('opens on the Node screen, with email reached from it', async () => {
    const page = await open('/');
    expect(page.querySelector('h1')?.textContent).toContain('Node');
    expect(page.querySelector('.tabs a.active')?.textContent).toContain('Node');
    const more = [...page.querySelectorAll('.more a')].map((a) => a.textContent?.trim());
    expect(more).toEqual(['Email']);
  });

  it('every route but the redirects is reachable from a tab or the Node screen', () => {
    // Contacts is the Chat screen's second tab; a chat opens from either.
    const reachable = new Set([...TABS.map((t) => t.path), '/email', '/chat/contacts']);
    const screens = routes
      .filter((r) => r.component && !r.path?.includes(':'))
      .map((r) => `/${r.path}`);
    expect(new Set(screens)).toEqual(reachable);
  });

  it('shows no radio until one is connected', async () => {
    const page = await open('/');
    expect(page.querySelector('.radio-state')?.textContent).toContain('No radio');
    expect(page.querySelector('.radio')?.textContent).toContain('Find my radio');
  });

  it('finds the radio and shows its name and battery, there and in the header', async () => {
    const page = await open('/node');
    await page.press('Find my radio', 'Battery');
    expect(page.querySelector('.radio-name')?.textContent).toBe('Field T1000');
    expect(page.querySelector('.battery')?.textContent).toBe('3.92 V');
    expect(page.querySelector('.radio-state')?.textContent).toContain('Field T1000');
    expect(page.querySelector('.radio-state')?.classList).toContain('connected');
  });

  it('reconnects to the radio from last time when it opens', async () => {
    localStorage.setItem(
      REMEMBERED,
      JSON.stringify({ deviceId: 'AA:BB:CC:DD:EE:FF', name: 'Field T1000' }),
    );
    const page = await open('/mailbox');
    await vi.waitFor(() =>
      expect(page.querySelector('.radio-state')?.textContent).toContain('Field T1000'),
    );
    expect(ble.connects).toEqual(['AA:BB:CC:DD:EE:FF']);
  });

  it('offers to reconnect after a disconnect, and to find another after forgetting', async () => {
    const page = await open('/node');
    await page.press('Find my radio', 'Battery');
    await page.press('Disconnect', "isn't connected");
    expect(page.querySelector('.radio-state')?.textContent).toContain('No radio');
    await page.press('Reconnect', 'Battery');
    await page.press('Forget it', 'Find my radio');
    expect(ble.connects).toHaveLength(2);
  });

  it("says why it couldn't connect", async () => {
    ble.failConnect = 'Connection timeout';
    const page = await open('/node');
    await page.press('Find my radio', 'a radio takes one at a time');
    expect(page.querySelector('.problem')).not.toBeNull();
  });

  it("lists the radio's companions to pick the node from, and checks whether you're a user", async () => {
    const page = await open('/node');
    await page.press('Find my radio', 'Ridge Node', '.node');
    const listed = [...page.querySelectorAll('.contacts button')].map((b) => b.textContent?.trim());
    expect(listed).toEqual(['Erin', 'Ridge Node']);
    await page.press('Ridge Node', "You're a user", '.node');
    expect(page.querySelector('.node h2')?.textContent).toBe('Ridge Node');
    expect(page.querySelector('.membership')?.textContent).toContain('No messages; no passphrase');
    expect(ble.sent.map(([, text]) => text)).toEqual(['whoami']);
  });

  it('asks to join when not a user, and shows the welcome', async () => {
    ble.node = (text) =>
      text === 'whoami'
        ? ['unrecognized user or function']
        : ['join: request sent to the admins as Field T1000'];
    const page = await open('/node');
    await page.press('Find my radio', 'Ridge Node', '.node');
    await page.press('Ridge Node', "You're not a user yet", '.node');
    await page.press('Join', 'Asked, as Field T1000', '.node');

    ble.node = () => ['Field T1000 (abababababab); passphrase set; 2 message(s), 1 unread'];
    ble.deliver(NODE_KEY, "Welcome, Field T1000: you're now a user. Send help for your commands.");
    await vi.waitFor(() => {
      page.fixture.detectChanges();
      expect(page.querySelector('.membership')?.textContent).toContain('2 message(s), 1 unread');
    });
    expect(page.textContent).toContain("Welcome, Field T1000: you're now a user.");
    expect([...page.querySelectorAll('button')].map((b) => b.textContent?.trim())).not.toContain(
      'Join',
    );
  });

  it("shows the node's reply as it came when the app can't read it", async () => {
    ble.node = () => ['whoami: something the app has never seen'];
    const page = await open('/node');
    await page.press('Find my radio', 'Ridge Node', '.node');
    await page.press('Ridge Node', 'something the app has never seen', '.node');
    expect(page.querySelector('.said')?.textContent).toBe(
      'whoami: something the app has never seen',
    );
  });

  it('goes back to the list to change the node', async () => {
    const page = await open('/node');
    await page.press('Find my radio', 'Ridge Node', '.node');
    await page.press('Ridge Node', "You're a user", '.node');
    await page.press('Change node', "Pick the node from your radio's contacts", '.node');
  });
});
