import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';

/** GET /api/overview (mesh_contingency/web/api.py). Times are seconds since 1970. */
export interface Overview {
  node: string | null;
  /** The longest channel post (alert, comm) from this node, or null with no radio. */
  channel_limit: number | null;
  started: number;
  now: number;
  health: string[];
  users: number;
  admins: number;
  requests: number;
  checkins: number;
  waiting: number;
  counts: { messages: number; sent: number; undelivered: number; errors: number };
  /** The node watch's problems, or null if [watch] is off. */
  watch: string[] | null;
  backup: { last: number | null; failing: string | null } | null;
  /** The alerts out for the counties in [alerts], each event once; null without counties. */
  alerts: {
    active: { event: string; counties: string[] }[];
    checked: number | null;
    problem: string | null;
  } | null;
}

/** An alert the NWS has out for a county, as the alert watcher last found it. */
export interface AreaAlert {
  event: string | null;
  severity: string | null;
  headline: string | null;
  ends: number | null;
}

/** A forecast period, e.g. Tonight: 60 F, Partly Cloudy. */
export interface Period {
  name: string;
  temp: number;
  unit: string;
  text: string;
  /** Chance of rain, in percent, or null if the NWS gave none. */
  pop: number | null;
  wind: string | null;
}

/**
 * The weather now in one county [alerts] watches (mesh_contingency/area_weather.py).
 * Only county, alerts and problem are there before the first report.
 */
export interface Area {
  county: string;
  alerts: AreaAlert[];
  /** Why the last try failed; the rest is the last report that worked. */
  problem?: string | null;
  /** The town the NWS names nearest the county's middle. */
  place?: string;
  station?: string | null;
  observed?: number | null;
  text?: string | null;
  temp_f?: number | null;
  feels_f?: number | null;
  humidity?: number | null;
  wind_mph?: number | null;
  gust_mph?: number | null;
  wind_dir?: string | null;
  periods?: Period[];
  updated?: number;
}

/** GET /api/weather. areas is null with no counties in [alerts]. */
export interface Weather {
  now: number;
  every_minutes: number;
  areas: Area[] | null;
  alerts_checked: number | null;
  alerts_problem: string | null;
}

/** One of the radio's contacts, from GET /api/contacts. */
export interface Contact {
  key: string;
  name: string | null;
  /** chat, repeater, room, sensor or unknown. */
  type: string;
  user: boolean;
  admin: boolean;
  /** The length of the path the radio keeps to it, or null if a message to it floods. */
  hops: number | null;
  /** When the radio last heard its advert (by the radio's clock), or null. */
  last_advert: number | null;
}

/** GET /api/contacts. max is how many the radio can hold, null if it doesn't say. */
export interface Contacts {
  max: number | null;
  contacts: Contact[];
}

/** One of the radio's channel slots, from GET /api/channels; never its key. */
export interface Channel {
  slot: number;
  name: string;
  /** public (the usual Public), hashtag (its key comes from its #name), private, or empty. */
  kind: 'public' | 'hashtag' | 'private' | 'empty';
  /** What the bot posts to it: alert, comm, testalert, weekly test, automatic alerts. */
  uses: string[];
  /** Its messages kept since the bot started, or null if none are kept. */
  messages: number | null;
  /** When the newest of them came, or null. */
  last: number | null;
}

/** A message on a channel, as GET /api/channels/{slot}/messages lists them. */
export interface ChannelMessage {
  time: number;
  /** Who sent it, or null if it didn't say. */
  sender: string | null;
  text: string;
  /** The repeaters it came through (0: direct), or null for this node's own posts. */
  hops: number | null;
  /** The signal-to-noise ratio it came in at (dB), or null. */
  snr: number | null;
  /** This node posted it (alert, comm, the automatic alerts, the weekly test). */
  own: boolean;
}

/** GET /api/channels/{slot}/messages: newest first; messages is null if none are kept. */
export interface ChannelMessages {
  slot: number;
  /** How many are kept per channel. */
  keep: number | null;
  messages: ChannelMessage[] | null;
}

/** One of GET /api/users: a user, an admin, or both. */
export interface User {
  key: string;
  name: string | null;
  /** Has a section in users.toml (an admin needn't). */
  user: boolean;
  admin: boolean;
  passphrase: boolean;
  /** Their settings in users.toml, e.g. qm and emailall addresses. */
  settings: Record<string, string | string[]>;
  last_seen: number | null;
  checkin: { status: string; time: number } | null;
  messages: number;
  unread: number;
}

/** One of GET /api/requests. */
export interface JoinRequest {
  key: string;
  name: string;
  time: number;
}

/** GET /api/checkins: check-ins newest first, and the users with none. */
export interface Checkins {
  checkins: { key: string; name: string; status: string; time: number }[];
  missing: { key: string; name: string | null }[];
}

/** One of GET /api/inbox: a user's mailbox, oldest first. Never the text. */
export interface Mailbox {
  key: string;
  name: string | null;
  messages: { from: string; time: number; read: boolean; sealed: boolean }[];
}

/** One of GET /api/history, newest first. */
export interface HistoryEntry {
  time: number;
  by: string;
  what: string;
}

/** POST /api/run: a command's whole reply. */
export interface Answer {
  command: string;
  messages: string[];
  /** The reply only asks to send the same again to confirm. */
  asks: boolean;
  /** False if it refused, failed or timed out: the messages say why. */
  ok: boolean;
}

/** One of GET /api/commands: what /api/run can run. */
export interface CommandInfo {
  name: string;
  permission: string;
  usage: string;
  summary: string;
  /** Where a channel command (alert, comm) posts. */
  channel: string | null;
}

/** The longest text /api/run takes. */
export const MAX_TEXT = 500;

/** One line of GET /api/log. */
export interface LogLine {
  time: number;
  line: string;
}

/**
 * The bot's API. The page and the API share one origin, so the cookie the
 * console.url link set goes with every request. Without it (a restart of the
 * bot made a new key) every request is refused with 401, and signedOut says
 * so.
 */
@Injectable({ providedIn: 'root' })
export class Api {
  private readonly http = inject(HttpClient);

  /** True once a request was refused for want of the key. */
  readonly signedOut = signal(false);

  overview(): Observable<Overview> {
    return this.get<Overview>('/api/overview');
  }

  users(): Observable<User[]> {
    return this.get<User[]>('/api/users');
  }

  requests(): Observable<JoinRequest[]> {
    return this.get<JoinRequest[]>('/api/requests');
  }

  checkins(): Observable<Checkins> {
    return this.get<Checkins>('/api/checkins');
  }

  inbox(): Observable<Mailbox[]> {
    return this.get<Mailbox[]>('/api/inbox');
  }

  history(): Observable<HistoryEntry[]> {
    return this.get<HistoryEntry[]>('/api/history');
  }

  weather(): Observable<Weather> {
    return this.get<Weather>('/api/weather');
  }

  contacts(): Observable<Contacts> {
    return this.get<Contacts>('/api/contacts');
  }

  channels(): Observable<Channel[]> {
    return this.get<Channel[]>('/api/channels');
  }

  channelMessages(slot: number): Observable<ChannelMessages> {
    return this.get<ChannelMessages>(`/api/channels/${slot}/messages`);
  }

  commands(): Observable<CommandInfo[]> {
    return this.get<CommandInfo[]>('/api/commands');
  }

  /** Run a command as the admin "console", as if sent over the radio. */
  run(command: string, text = ''): Observable<Answer> {
    return this.http.post<Answer>('/api/run', { command, text }).pipe(this.watch());
  }

  /** The live log: the lines kept so far, then each new one. */
  log(): EventSource {
    return new EventSource('/api/log');
  }

  private get<T>(url: string): Observable<T> {
    return this.http.get<T>(url).pipe(this.watch());
  }

  /** Notes a refused key on the way past. */
  private watch<T>() {
    return catchError<T, Observable<T>>((error: HttpErrorResponse) => {
      if (error.status === 401) {
        this.signedOut.set(true);
      }
      return throwError(() => error);
    });
  }
}
