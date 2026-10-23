import { signal } from '@angular/core';
import { Observable, of } from 'rxjs';

import { Answer, JoinRequest, Overview, User } from '../app/api';

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

export const ALICE: User = {
  key: 'a1'.repeat(32),
  name: 'Alice',
  user: true,
  admin: false,
  passphrase: true,
  settings: { qm: 'alice@example.com', emailall: ['a@example.com', 'b@example.com'] },
  last_seen: 1000,
  checkin: { status: 'ok', time: 900 },
  messages: 2,
  unread: 1,
};

export const ADMIN: User = {
  key: 'ad'.repeat(32),
  name: 'Admin Radio',
  user: false,
  admin: true,
  passphrase: false,
  settings: {},
  last_seen: null,
  checkin: null,
  messages: 0,
  unread: 0,
};

export const CAROL: JoinRequest = { key: 'c0'.repeat(32), name: 'Carol T-Deck', time: 950 };

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

/**
 * Stands in for Api: each call gives what its property returns; run() also
 * records what was run. log() gives a FakeEventSource.
 */
export class FakeApi {
  readonly signedOut = signal(false);
  overview: () => Observable<Overview> = () => of(OVERVIEW);
  users: () => Observable<User[]> = () => of([ADMIN, ALICE]);
  requests: () => Observable<JoinRequest[]> = () => of([CAROL]);
  answer: (command: string, text: string) => Observable<Answer> = (command) =>
    of({ command, messages: [`${command}: done`], asks: false });
  readonly ran: [string, string][] = [];
  run(command: string, text = ''): Observable<Answer> {
    this.ran.push([command, text]);
    return this.answer(command, text);
  }
  readonly source = new FakeEventSource();
  log(): FakeEventSource {
    return this.source;
  }
}
