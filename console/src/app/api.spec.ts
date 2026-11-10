import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { Api, apiError } from './api';
import { OVERVIEW, SAM } from '../testing/fakes';

describe('Api', () => {
  let api: Api;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(Api);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('reads the overview', () => {
    let found: unknown;
    api.overview().subscribe((overview) => (found = overview));
    http.expectOne('/api/overview').flush(OVERVIEW);
    expect(found).toEqual(OVERVIEW);
    expect(api.signedOut()).toBe(false);
  });

  it('is signed out when the key is refused', () => {
    let failed = false;
    api.overview().subscribe({ error: () => (failed = true) });
    http.expectOne('/api/overview').flush('Open the console...', { status: 401, statusText: '' });
    expect(failed).toBe(true);
    expect(api.signedOut()).toBe(true);
  });

  it('is not signed out by other failures', () => {
    api.overview().subscribe({ error: () => undefined });
    http.expectOne('/api/overview').flush('', { status: 500, statusText: '' });
    expect(api.signedOut()).toBe(false);
  });

  it('knows the remote console wants a login', () => {
    api.overview().subscribe({ error: () => undefined });
    http
      .expectOne('/api/overview')
      .flush({ error: 'log in first', login: true }, { status: 401, statusText: '' });
    expect(api.signedOut()).toBe(true);
    expect(api.loginNeeded()).toBe(true);
  });

  it('logs in, then reads who this is', () => {
    api.signedOut.set(true);
    api.loginNeeded.set(true);
    api.logIn('sam', 'correct horse battery').subscribe();
    const login = http.expectOne('/api/login');
    expect(login.request.method).toBe('POST');
    expect(login.request.body).toEqual({ name: 'sam', password: 'correct horse battery' });
    login.flush({ name: 'sam' });
    expect(api.signedOut()).toBe(false);
    expect(api.loginNeeded()).toBe(false);
    http.expectOne('/api/me').flush(SAM);
    expect(api.me()).toEqual(SAM);
  });

  it('logs out', () => {
    api.me.set(SAM);
    api.logOut().subscribe();
    http.expectOne('/api/logout').flush({ ok: true });
    expect(api.me()).toBeNull();
    expect(api.signedOut()).toBe(true);
    expect(api.loginNeeded()).toBe(true);
  });

  it('names console users safely in their addresses', () => {
    api.removeConsoleUser('a/b').subscribe();
    const removed = http.expectOne('/api/console-users/a%2Fb');
    expect(removed.request.method).toBe('DELETE');
    removed.flush({ name: 'a/b' });
  });

  it('says what the bot said was wrong', () => {
    expect(apiError({ error: { error: 'no such user' } }, 'fallback')).toBe('no such user');
    expect(apiError({ error: 'Not JSON' }, 'fallback')).toBe('fallback');
    expect(apiError(null, 'fallback')).toBe('fallback');
  });
});
