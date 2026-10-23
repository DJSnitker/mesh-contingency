import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { Api } from './api';
import { App } from './app';
import { routes } from './app.routes';
import { FakeApi } from '../testing/fakes';

describe('App', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({
      providers: [provideRouter(routes), { provide: Api, useValue: api }],
    });
  });

  it('has the pages in its rail', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.brand')?.textContent).toContain('Mesh Contingency');
    expect([...element.querySelectorAll('.rail li')].map((li) => li.textContent?.trim())).toEqual([
      'Dashboard',
      'Users',
    ]);
  });

  it('says how to get back in when signed out', async () => {
    api.signedOut.set(true);
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('[role=alert]')?.textContent).toContain('console.url');
    expect(element.querySelector('router-outlet')).toBeNull();
  });
});
