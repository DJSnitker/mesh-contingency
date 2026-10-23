import { signal } from '@angular/core';
import { Observable, of } from 'rxjs';

import { Overview } from '../app/api';

export const OVERVIEW: Overview = {
  node: 'Hilltop Node',
  started: 1000,
  now: 1000 + 3 * 3600 + 5 * 60,
  health: ['radio Hilltop Node', 'battery 4.10V', 'users 2 (1 admin)'],
  users: 2,
  admins: 1,
  requests: 0,
  checkins: 1,
  waiting: 3,
  counts: { messages: 5, sent: 6, undelivered: 1, errors: 0 },
  watch: [],
  backup: { last: 1000 + 3600, failing: null },
};

/** Stands in for EventSource, which jsdom doesn't have. */
export class FakeEventSource {
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  closed = false;

  open(): void {
    this.onopen?.();
  }

  send(time: number, line: string): void {
    this.onmessage?.({ data: JSON.stringify({ time, line }) } as MessageEvent<string>);
  }

  fail(): void {
    this.onerror?.();
  }

  close(): void {
    this.closed = true;
  }
}

/** Stands in for Api: overview() gives what `overview` returns, log() a FakeEventSource. */
export class FakeApi {
  readonly signedOut = signal(false);
  overview: () => Observable<Overview> = () => of(OVERVIEW);
  readonly source = new FakeEventSource();
  log(): FakeEventSource {
    return this.source;
  }
}
