import { TestBed } from '@angular/core/testing';
import { provideRouter, Router, withHashLocation } from '@angular/router';

import { App } from './app';
import { routes, TABS } from './app.routes';
import { BLE } from './radio/ble';
import { FakeBle } from './radio/fake-ble';
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
    /** Press a button by its text, and wait for the radio panel to show `then`. */
    const press = async (text: string, then: string) => {
      const button = [...page.querySelectorAll('button')].find((b) =>
        b.textContent?.includes(text),
      );
      expect(button, `a "${text}" button`).toBeTruthy();
      button!.click();
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(page.querySelector('.radio')?.textContent).toContain(then);
      });
    };
    return Object.assign(page, { press });
  }

  it('has a tab for each main screen, in order', async () => {
    const page = await open('/');
    const tabs = [...page.querySelectorAll('.tabs a')].map((a) => a.textContent?.trim());
    expect(tabs).toEqual(TABS.map((tab) => tab.label));
  });

  it('opens on the Node screen, with email and weather reached from it', async () => {
    const page = await open('/');
    expect(page.querySelector('h1')?.textContent).toContain('Node');
    expect(page.querySelector('.tabs a.active')?.textContent).toContain('Node');
    const more = [...page.querySelectorAll('.more a')].map((a) => a.textContent?.trim());
    expect(more).toEqual(['Email', 'Weather and verse']);
  });

  it('says what a screen not built yet will do', async () => {
    const page = await open('/chat');
    expect(page.querySelector('h1')?.textContent).toContain('Chat');
    expect(page.textContent).toContain("Direct messages with your radio's contacts");
    expect(page.textContent).toContain('"Chat" step');
  });

  it('every route but the redirects is reachable from a tab or the Node screen', () => {
    const reachable = new Set([...TABS.map((t) => t.path), '/email', '/weather']);
    const screens = routes.filter((r) => r.component).map((r) => `/${r.path}`);
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
});
