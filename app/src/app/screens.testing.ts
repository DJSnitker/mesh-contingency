// Opening a screen in tests, with the fake radio connected and the node
// picked, and pressing its buttons; the node answers with the bot's real
// replies from tests/fixtures/app_replies.json.
import { Provider } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import {
  provideRouter,
  Router,
  withComponentInputBinding,
  withHashLocation,
} from '@angular/router';

import fixtures from '../../../tests/fixtures/app_replies.json';
import { App } from './app';
import { routes } from './app.routes';
import { CHOSEN, NodeLink, TIMING } from './node/node-link';
import { BLE } from './radio/ble';
import { FakeBle, NODE_KEY } from './radio/fake-ble';
import { REMEMBERED } from './radio/radio';

/** What the bot really replies, from the shared fixtures. */
export function reply(name: string): string[] {
  const found = fixtures.cases.find((c) => c.name === name);
  if (!found) {
    throw new Error(`no fixture ${name}`);
  }
  return found.reply;
}

/** The screen at `path`, with the radio connected and the node picked (unless `ready` is false). */
export async function openScreen(
  path: string,
  ble: FakeBle,
  ready = true,
  providers: Provider[] = [],
) {
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
      provideRouter(routes, withHashLocation(), withComponentInputBinding()),
      { provide: BLE, useValue: ble },
      { provide: TIMING, useValue: { firstReplyMs: 2000, quietMs: 50, partsMs: 200 } },
      ...providers,
    ],
  });
  const fixture = TestBed.createComponent(App);
  await TestBed.inject(Router).navigateByUrl(path);
  await fixture.whenStable();
  const page = fixture.nativeElement as HTMLElement;
  const link = TestBed.inject(NodeLink);
  const settle = async () => {
    await vi.waitFor(() => expect(link.ready()).toBe(true));
    fixture.detectChanges();
    await fixture.whenStable();
  };
  if (ready) {
    await settle();
  }
  /** Type into a field, by its name. */
  const type = (name: string, text: string) => {
    const field = page.querySelector<HTMLInputElement>(`[name="${name}"]`)!;
    field.value = text;
    field.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  };
  /** The button whose text starts with `text`. */
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
