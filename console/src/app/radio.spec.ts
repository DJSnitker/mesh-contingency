import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { afterEach, vi } from 'vitest';

import { Api } from './api';
import { Radio } from './radio';
import { COMMANDS, FakeApi } from '../testing/fakes';

describe('Radio', () => {
  let api: FakeApi;

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: Api, useValue: api }],
    });
  });

  async function render() {
    const fixture = TestBed.createComponent(Radio);
    await fixture.whenStable();
    return fixture;
  }

  function button(element: HTMLElement, label: string): HTMLButtonElement {
    return [...element.querySelectorAll('button')].find((b) => b.textContent?.trim() === label)!;
  }

  it('adverts and backs up', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    button(element, 'Flood advert').click();
    await fixture.whenStable();
    button(element, 'Back up now').click();
    await fixture.whenStable();
    expect(api.ran).toEqual([
      ['advert', 'flood'],
      ['backup', ''],
    ]);
    expect(element.querySelector('.reply')?.textContent).toContain('backup: done');
  });

  it('offers only what the console may run', async () => {
    api.commands = () => of(COMMANDS.filter((c) => c.name === 'backup'));
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    expect([...element.querySelectorAll('h2')].map((h) => h.textContent?.trim())).toEqual([
      'Backup',
      'Settings',
    ]);
  });

  it('has the settings, and its contacts and channels are in Contacts', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector('mc-radio-settings')).not.toBeNull();
    expect(element.querySelector('[role=tab]')).toBeNull();
    expect(element.querySelector('.title a')?.getAttribute('href')).toBe('/contacts');
  });
});
