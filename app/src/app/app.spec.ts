import { TestBed } from '@angular/core/testing';
import { provideRouter, Router, withHashLocation } from '@angular/router';

import { App } from './app';
import { routes, TABS } from './app.routes';

describe('App', () => {
  async function open(path: string) {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter(routes, withHashLocation())],
    });
    const fixture = TestBed.createComponent(App);
    await TestBed.inject(Router).navigateByUrl(path);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
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

  it('shows no radio until Bluetooth is built', async () => {
    const page = await open('/');
    expect(page.querySelector('.radio-state')?.textContent).toContain('No radio');
  });
});
