import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { Api } from './api';
import { OVERVIEW } from '../testing/fakes';

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
});
