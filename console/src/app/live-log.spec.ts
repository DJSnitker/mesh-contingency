import { TestBed } from '@angular/core/testing';

import { Api } from './api';
import { LiveLog, MAX_LINES } from './live-log';
import { FakeApi } from '../testing/fakes';

describe('LiveLog', () => {
  let api: FakeApi;

  beforeEach(() => {
    api = new FakeApi();
    TestBed.configureTestingModule({ providers: [{ provide: Api, useValue: api }] });
  });

  async function render() {
    const fixture = TestBed.createComponent(LiveLog);
    await fixture.whenStable();
    return fixture;
  }

  function lines(element: HTMLElement): string[] {
    return [...element.querySelectorAll('.line span')].map((line) => line.textContent ?? '');
  }

  it('shows each line as it comes', async () => {
    const fixture = await render();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('reconnecting');
    api.source.open();
    api.source.send(1, '[console] health');
    api.source.send(2, '  -> running health');
    await fixture.whenStable();
    expect(lines(element)).toEqual(['[console] health', '  -> running health']);
    expect(element.querySelector('.state')?.textContent).toContain('live');
  });

  it('starts over when it reconnects, since the kept lines come again', async () => {
    const fixture = await render();
    api.source.open();
    api.source.send(1, 'one');
    api.source.fail();
    api.source.open();
    api.source.send(1, 'one');
    await fixture.whenStable();
    expect(lines(fixture.nativeElement)).toEqual(['one']);
  });

  it(`keeps the last ${MAX_LINES} lines`, async () => {
    const fixture = await render();
    api.source.open();
    for (let i = 0; i < MAX_LINES + 5; i++) {
      api.source.send(i, `line ${i}`);
    }
    await fixture.whenStable();
    const shown = lines(fixture.nativeElement);
    expect(shown.length).toBe(MAX_LINES);
    expect(shown[0]).toBe('line 5');
  });

  it('closes the log when it goes', async () => {
    const fixture = await render();
    fixture.destroy();
    expect(api.source.closed).toBe(true);
  });
});
