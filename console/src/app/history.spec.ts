import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { Api } from './api';
import { History } from './history';
import { FakeApi } from '../testing/fakes';

describe('History', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({ providers: [{ provide: Api, useValue: api }] });
  });

  async function render() {
    const fixture = TestBed.createComponent(History);
    await fixture.whenStable();
    return fixture;
  }

  function shown(element: HTMLElement): string[] {
    return [...element.querySelectorAll('.entry .what')].map((e) => e.textContent ?? '');
  }

  async function type(fixture: Awaited<ReturnType<typeof render>>, text: string) {
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = text;
    input.dispatchEvent(new Event('input'));
    await fixture.whenStable();
  }

  it('lists what was done, newest first', async () => {
    const fixture = await render();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.textContent).toContain('The last 3 admin action(s)');
    expect(shown(element)).toEqual([
      'approved Carol T-Deck (c0c0c0c0c0c0)',
      'left',
      'posted an alert to #contingency-wx',
    ]);
    expect(element.querySelector('.entry .by')?.textContent).toBe('console');
  });

  it('filters by who and what, every word', async () => {
    const fixture = await render();
    await type(fixture, 'alert');
    expect(shown(fixture.nativeElement)).toEqual(['posted an alert to #contingency-wx']);
    await type(fixture, 'Console  APPROVED');
    expect(shown(fixture.nativeElement)).toEqual(['approved Carol T-Deck (c0c0c0c0c0c0)']);
    await type(fixture, 'nobody did this');
    expect(fixture.nativeElement.textContent).toContain('Nothing matches the filter.');
  });

  it('says when there is nothing yet', async () => {
    api.history = () => of([]);
    const fixture = await render();
    expect(fixture.nativeElement.textContent).toContain('Nothing yet.');
  });
});
