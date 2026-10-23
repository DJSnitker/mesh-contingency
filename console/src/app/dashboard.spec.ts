import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
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
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: Api, useValue: api }],
    });
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
    expect(read(element.querySelector('a.row')!)).toBe('Alerts none');
    expect(element.querySelector('a.row')?.getAttribute('href')).toBe('/weather');
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

  it('names the alerts out, with their counties, and links to Area Weather', async () => {
    const alerts = {
      active: [
        { event: 'Wind Advisory', counties: ['Taylor, TX', 'Jones, TX'] },
        { event: 'Flood Warning', counties: ['Brown, TX'] },
      ],
      checked: 1000,
      problem: null,
    };
    api.overview = () => of({ ...OVERVIEW, alerts });
    const row = (await render()).querySelector('a.row.bad')!;
    expect(read(row)).toBe('Alerts Wind Advisory (Taylor, Jones); Flood Warning (Brown)');
    expect(row.getAttribute('href')).toBe('/weather');
  });

  it("says when alerts can't be checked, or are off", async () => {
    const failing = { active: [], checked: 1000, problem: 'no network' };
    api.overview = () => of({ ...OVERVIEW, alerts: failing });
    let element = await render();
    expect(read(element.querySelector('a.row.bad')!)).toBe("Alerts can't check: no network");
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: Api, useValue: api }],
    });
    api.overview = () => of({ ...OVERVIEW, alerts: null });
    element = await render();
    expect(read(element.querySelector('a.row')!)).toBe('Alerts off');
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
    expect(rows.slice(0, 3)).toEqual(['Alerts none', 'Watch off', 'Backup off']);
  });
});
