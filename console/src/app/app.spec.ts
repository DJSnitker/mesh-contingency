import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';

import { Api } from './api';
import { App } from './app';
import { routes } from './app.routes';
import { CHANNELS, CONVERSATIONS, FakeApi } from '../testing/fakes';

describe('App', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    // Nothing unread, unless a test says.
    api.channels = () => of(CHANNELS.map((c) => ({ ...c, heard: 0 })));
    api.conversations = () => of(CONVERSATIONS.map((c) => ({ ...c, heard: 0 })));
    TestBed.configureTestingModule({
      providers: [provideRouter(routes), { provide: Api, useValue: api }],
    });
  });

  it('has the pages in its rail, grouped as the phone app is', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.brand')?.textContent).toContain('Mesh Contingency');
    expect([...element.querySelectorAll('.rail li')].map((li) => li.textContent?.trim())).toEqual([
      'Dashboard',
      'Mailbox',
      'Check-ins',
      'Chat',
      'Weather',
      'Bible',
      'Radio',
      'Users',
      'History',
    ]);
  });

  it('has the tab bar for phone width, More lit on the pages it lists', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    const tabs = () => [...element.querySelectorAll('nav.tabs a')];
    expect(tabs().map((a) => a.textContent?.trim())).toEqual([
      'Dashboard',
      'Mailbox',
      'Chat',
      'Weather',
      'More',
    ]);
    const lit = () =>
      tabs()
        .find((a) => a.classList.contains('active'))
        ?.textContent?.trim();
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/radio');
    await fixture.whenStable();
    expect(lit()).toBe('More');
    await router.navigateByUrl('/chat/channel/1');
    await fixture.whenStable();
    expect(lit()).toBe('Chat');
    await router.navigateByUrl('/more');
    await fixture.whenStable();
    expect(lit()).toBe('More');
    expect([...element.querySelectorAll('main .more a')].map((a) => a.textContent?.trim())).toEqual(
      ['Check-ins', 'Bible', 'Radio', 'Users', 'History'],
    );
  });

  it('takes the old pages to their new places', async () => {
    const router = TestBed.inject(Router);
    TestBed.createComponent(App);
    await router.navigateByUrl('/inbox');
    expect(router.url).toBe('/mailbox');
    await router.navigateByUrl('/send');
    expect(router.url).toBe('/chat');
  });

  it('says how to get back in when signed out', async () => {
    api.signedOut.set(true);
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('[role=alert]')?.textContent).toContain('console.url');
    expect(element.querySelector('router-outlet')).toBeNull();
  });

  it('counts the unread channel messages and replies beside Chat', async () => {
    localStorage.clear();
    api.channels = () => of(CHANNELS);
    api.conversations = () => of(CONVERSATIONS);
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    const chat = [...element.querySelectorAll('.rail a')].find((a) =>
      a.textContent?.includes('Chat'),
    )!;
    expect(chat.querySelector('.unread')?.textContent).toBe('2'); // Public's one, Alice's reply
    fixture.destroy();
  });
});
