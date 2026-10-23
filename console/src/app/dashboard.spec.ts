import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { Api } from './api';
import { Dashboard } from './dashboard';
import { FakeApi, OVERVIEW } from '../testing/fakes';

/** An element's text as read: its children's, a space between. */
function read(element: Element): string {
  return [...element.children]
    .map((child) => child.textContent?.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .join(' ');
}

describe('Dashboard', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({ providers: [{ provide: Api, useValue: api }] });
  });

  async function render(): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(Dashboard);
    await fixture.whenStable();
    return fixture.nativeElement;
  }

  it('shows the node at a glance', async () => {
    const element = await render();
    expect(element.querySelector('h1')?.textContent).toBe('Hilltop Node');
    expect(element.textContent).toContain('Bot up 3h 5m');
    const tiles = [...element.querySelectorAll('.tile')].map(read);
    expect(tiles).toEqual([
      '2 users (1 admin)',
      '0 join requests',
      '1 check-ins',
      '3 messages waiting',
    ]);
    expect(element.textContent).toContain('no problems');
    expect(element.textContent).toContain('last 2h ago');
    expect(element.textContent).toContain('5 in, 6 out (1 undelivered), 0 error(s)');
    const health = [...element.querySelectorAll('.health li')].map((li) => li.textContent);
    expect(health).toEqual(OVERVIEW.health);
    expect(element.querySelector('.bad')).toBeNull();
  });

  it('makes problems stand out', async () => {
    const problems = {
      ...OVERVIEW,
      requests: 2,
      watch: ['battery low'],
      backup: { last: null, failing: 'disk full' },
    };
    api.overview = () => of(problems);
    const element = await render();
    expect(element.querySelector('.tile.attention')?.textContent).toContain('2');
    const bad = [...element.querySelectorAll('.row.bad')].map((row) => row.textContent);
    expect(bad.join('|')).toContain('battery low');
    expect(bad.join('|')).toContain('failing: disk full');
  });

  it("says when the bot can't be reached", async () => {
    api.overview = () => throwError(() => new HttpErrorResponse({ status: 0 }));
    const element = await render();
    expect(element.querySelector('[role=alert]')?.textContent).toContain("can't reach the bot");
  });

  it('says when watch and backups are off', async () => {
    api.overview = () => of({ ...OVERVIEW, watch: null, backup: null });
    const element = await render();
    const rows = [...element.querySelectorAll('.row')].map(read);
    expect(rows.slice(0, 2)).toEqual(['Watch off', 'Backup off']);
  });
});
