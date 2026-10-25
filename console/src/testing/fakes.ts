import { signal } from '@angular/core';
import { Observable, of } from 'rxjs';

import {
  Answer,
  Channel,
  ChannelMessages,
  Checkins,
  CommandInfo,
  Contacts,
  RadioSettings,
  HistoryEntry,
  JoinRequest,
  Mailbox,
  Overview,
  User,
  Weather,
} from '../app/api';

export const OVERVIEW: Overview = {
  node: 'Hilltop Node',
  channel_limit: 119,
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
  alerts: { active: [], checked: 1000 + 3 * 3600, problem: null },
};

export const WEATHER: Weather = {
  now: 10_000,
  every_minutes: 15,
  alerts_checked: 9_900,
  alerts_problem: null,
  areas: [
    {
      county: 'Taylor, TX',
      alerts: [],
      problem: null,
      place: 'Buffalo Gap, TX',
      station: 'Abilene Regional Airport',
      observed: 10_000 - 25 * 60,
      text: 'Clear',
      temp_f: 62.96,
      feels_f: null,
      humidity: 62.6,
      wind_mph: 6.9,
      gust_mph: 15.2,
      wind_dir: 'SE',
      periods: [
        {
          name: 'Today',
          temp: 85,
          unit: 'F',
          text: 'Mostly Sunny',
          pop: 0,
          wind: 'SSE 10 to 15 mph',
        },
        { name: 'Tonight', temp: 60, unit: 'F', text: 'Chance Showers', pop: 30, wind: 'S 10 mph' },
      ],
      updated: 10_000 - 5 * 60,
    },
    {
      county: 'Jones, TX',
      alerts: [{ event: 'Wind Advisory', severity: 'Minor', headline: null, ends: null }],
      problem: 'no network',
      place: 'Anson, TX',
      station: null,
      observed: null,
      text: null,
      temp_f: null,
      feels_f: null,
      humidity: null,
      wind_mph: null,
      gust_mph: null,
      wind_dir: null,
      periods: [],
      updated: 10_000 - 40 * 60,
    },
    { county: 'Callahan, TX', alerts: [], problem: 'TimeoutError' },
  ],
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

export const CHECKINS: Checkins = {
  checkins: [
    { key: 'a1'.repeat(32), name: 'Alice', status: 'ok, at the shelter', time: 900 },
    { key: 'ad'.repeat(32), name: 'Admin Radio', status: 'ok', time: 800 },
  ],
  missing: [{ key: 'b0'.repeat(32), name: 'Bob' }],
};

export const MAILBOXES: Mailbox[] = [
  {
    key: 'a1'.repeat(32),
    name: 'Alice',
    messages: [
      { from: 'Bob', time: 700, read: true, sealed: false },
      { from: 'Dana', time: 950, read: false, sealed: true },
    ],
  },
];

export const HISTORY: HistoryEntry[] = [
  { time: 990, by: 'console', what: 'approved Carol T-Deck (c0c0c0c0c0c0)' },
  { time: 900, by: 'Alice', what: 'left' },
  { time: 800, by: 'KE5ABC', what: 'posted an alert to #contingency-wx' },
];

export const CONTACTS: Contacts = {
  max: 350,
  contacts: [
    {
      key: 'a1'.repeat(32),
      name: 'Alice',
      type: 'chat',
      user: true,
      admin: false,
      hops: 1,
      last_advert: 1_000,
    },
    {
      key: '37ca'.padEnd(64, '0'),
      name: 'Hilltop',
      type: 'repeater',
      user: false,
      admin: false,
      hops: null,
      last_advert: null,
    },
  ],
};

export const CHANNELS: Channel[] = [
  { slot: 0, name: 'Public', kind: 'public', uses: [], messages: 2, last: 900 },
  {
    slot: 1,
    name: '#contingency-wx',
    kind: 'hashtag',
    uses: ['alert', 'automatic alerts'],
    messages: 0,
    last: null,
  },
  { slot: 2, name: 'Family', kind: 'private', uses: [], messages: 0, last: null },
  { slot: 3, name: '', kind: 'empty', uses: [], messages: 0, last: null },
  { slot: 4, name: '', kind: 'empty', uses: [], messages: 0, last: null },
];

export const RADIO: RadioSettings = {
  name: 'test-node',
  freq: 910.525,
  bw: 62.5,
  sf: 7,
  cr: 5,
  presets_matching: ['Canada', 'USA'],
  tx_power: 22,
  max_tx_power: 22,
  lat: 32.5,
  lon: -99.75,
  shares_position: false,
  clock_offset: -125,
  model: 'Test Board',
  version: 'v1.9',
  build: '12 Oct 2026',
  path_hash_mode: 0,
  manual_add_contacts: true,
  bandwidths: [7.8, 10.4, 15.6, 20.8, 31.25, 41.7, 62.5, 125, 250, 500],
  presets: [
    { title: 'Australia (Narrow)', freq: 916.575, bw: 62.5, sf: 7, cr: 7, path_hash_size: null },
    { title: 'Canada', freq: 910.525, bw: 62.5, sf: 7, cr: 5, path_hash_size: 3 },
    { title: 'USA', freq: 910.525, bw: 62.5, sf: 7, cr: 5, path_hash_size: null },
  ],
  presets_taken: '2026-10-23',
};

export const PUBLIC_MESSAGES: ChannelMessages = {
  slot: 0,
  keep: 200,
  messages: [
    { time: 900, sender: 'test-node', text: 'net at 7', hops: null, snr: null, own: true },
    { time: 600, sender: 'Alice', text: 'anyone on?', hops: 2, snr: 6.5, own: false },
  ],
};

function offer(name: string, usage: string, channel: string | null = null): CommandInfo {
  return { name, permission: 'admin', usage, summary: `${name} summary`, channel };
}

export const COMMANDS: CommandInfo[] = [
  offer('advert', 'advert [flood]'),
  offer('alertmap', 'alertmap [county, ST]'),
  offer('alert', 'alert <message>', '#contingency-wx'),
  offer('backup', 'backup'),
  offer('comm', 'comm <message>', '#contingency-comm'),
  offer('contact', 'contact remove|path <name or key>'),
  offer('radio', 'radio [name|power|position|clock|reboot|freq ...]'),
  offer('reload', 'reload'),
  offer('setemail', 'setemail <name or key> qm [address] group [address ...]'),
  { ...offer('status', 'status <name or key>'), permission: 'public' },
  offer('testalert', 'testalert'),
  { ...offer('verse', 'verse [book chapter:verse[-verse]]'), permission: 'public' },
  { ...offer('msg', 'msg <name> <message>'), permission: 'user' },
  offer('whois', 'whois <name or key>'),
];

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
  checkins: () => Observable<Checkins> = () => of(CHECKINS);
  commands: () => Observable<CommandInfo[]> = () => of(COMMANDS);
  inbox: () => Observable<Mailbox[]> = () => of(MAILBOXES);
  history: () => Observable<HistoryEntry[]> = () => of(HISTORY);
  weather: () => Observable<Weather> = () => of(WEATHER);
  contacts: () => Observable<Contacts> = () => of(CONTACTS);
  channels: () => Observable<Channel[]> = () => of(CHANNELS);
  radio: () => Observable<RadioSettings | null> = () => of(RADIO);
  channelMessages: (slot: number) => Observable<ChannelMessages> = (slot) =>
    of({ ...PUBLIC_MESSAGES, slot });
  answer: (command: string, text: string) => Observable<Answer> = (command) =>
    of({ command, messages: [`${command}: done`], asks: false, ok: true });
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
