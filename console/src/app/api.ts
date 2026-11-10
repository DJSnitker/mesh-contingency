import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, tap, throwError } from 'rxjs';

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
  /** Others' messages heard on it since the bot started (for unread), or null if none are kept. */
  heard: number | null;
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
  /** As Channel's heard. */
  heard: number | null;
}

/** One of MeshCore's regional presets: frequency MHz, bandwidth kHz, SF and CR. */
export interface Preset {
  title: string;
  freq: number;
  bw: number;
  sf: number;
  cr: number;
  /** A network setting the preset suggests, which the radio command leaves alone. */
  path_hash_size: number | null;
}

/** GET /api/radio: the radio's own settings (null with no radio). */
export interface RadioSettings {
  name: string | null;
  freq: number | null;
  bw: number | null;
  sf: number | null;
  cr: number | null;
  /** The presets with the radio's four values. */
  presets_matching: string[];
  tx_power: number | null;
  max_tx_power: number | null;
  lat: number | null;
  lon: number | null;
  /** Whether its adverts carry its position. */
  shares_position: boolean;
  /** The radio's clock minus the computer's (s), or null if it didn't say. */
  clock_offset: number | null;
  model: string | null;
  version: string | null;
  build: string | null;
  path_hash_mode: number | null;
  /** On: the radio adds only the contacts [contacts] auto_add takes (set from config.toml). */
  manual_add_contacts: boolean | null;
  bandwidths: number[];
  presets: Preset[];
  /** When the presets were copied from MeshCore's feed. */
  presets_taken: string;
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

/** GET /api/me (mesh_contingency/web/accounts.py): who this browser is. */
export interface Me {
  /** As history shows it: "console", or "sam (console)". */
  name: string;
  /** The console user logged in, or null for the console on the node's computer. */
  user: string | null;
  /** True on the remote console (logged in from the network). */
  remote: boolean;
  /** The remote console's addresses and certificate, once it's up; null when it's off. */
  remote_console: { urls: string[]; fingerprint: string; own_certificate?: boolean } | null;
}

/** One of GET /api/console-users. Never a password. */
export interface ConsoleUser {
  name: string;
  created: number;
  /** "node" (made with the command), "console" (the node's own console) or a console user. */
  created_by: string;
  /** When the password was last set. */
  changed: number;
  last_login: number | null;
}

/** One line of GET /api/log. */
export interface LogLine {
  time: number;
  line: string;
}

/**
 * The bot's API. The page and the API share one origin, so the cookie the
 * console.url link set (or, on the remote console, the login's) goes with
 * every request. Without it (a restart of the bot made a new key, or the
 * login ended) every request is refused with 401, and signedOut says so;
 * loginNeeded says the remote console wants a name and password.
 */
@Injectable({ providedIn: 'root' })
export class Api {
  private readonly http = inject(HttpClient);

  /** True once a request was refused for want of the key or a login. */
  readonly signedOut = signal(false);
  /** True if the refusal was the remote console's: log in to go on. */
  readonly loginNeeded = signal(false);
  /** Who this browser is, once read (whoAmI). */
  readonly me = signal<Me | null>(null);

  /** Read who this is into me. */
  whoAmI(): void {
    this.get<Me>('/api/me').subscribe({
      next: (me) => this.me.set(me),
      error: () => undefined, // signedOut says so if it was a 401
    });
  }

  /** Log in to the remote console; then everything is read again. */
  logIn(name: string, password: string): Observable<{ name: string }> {
    return this.http.post<{ name: string }>('/api/login', { name, password }).pipe(
      tap(() => {
        this.signedOut.set(false);
        this.loginNeeded.set(false);
        this.whoAmI();
      }),
    );
  }

  logOut(): Observable<unknown> {
    return this.http.post('/api/logout', {}).pipe(
      tap(() => {
        this.me.set(null);
        this.loginNeeded.set(true);
        this.signedOut.set(true);
      }),
    );
  }

  /** A console user's own password: the current one, then the new. */
  changePassword(current: string, password: string): Observable<unknown> {
    return this.http.post('/api/me/password', { current, password }).pipe(this.watch());
  }

  consoleUsers(): Observable<ConsoleUser[]> {
    return this.get<ConsoleUser[]>('/api/console-users');
  }

  addConsoleUser(name: string, password: string): Observable<ConsoleUser> {
    return this.http.post<ConsoleUser>('/api/console-users', { name, password }).pipe(this.watch());
  }

  /** Someone else's password: they're logged out. */
  setConsoleUserPassword(name: string, password: string): Observable<unknown> {
    return this.http
      .post(`/api/console-users/${encodeURIComponent(name)}/password`, { password })
      .pipe(this.watch());
  }

  removeConsoleUser(name: string): Observable<unknown> {
    return this.http.delete(`/api/console-users/${encodeURIComponent(name)}`).pipe(this.watch());
  }

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

  /** Post to a channel slot as this node; answers with the channel's name. */
  postToChannel(slot: number, text: string): Observable<{ channel: string }> {
    return this.http
      .post<{ channel: string }>(`/api/channels/${slot}/messages`, { text })
      .pipe(this.watch());
  }

  radio(): Observable<RadioSettings | null> {
    return this.get<RadioSettings | null>('/api/radio');
  }

  commands(): Observable<CommandInfo[]> {
    return this.get<CommandInfo[]>('/api/commands');
  }

  /** Run a command as this browser's sender (me), as if sent over the radio. */
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

  /** Notes a refused key or login on the way past. */
  private watch<T>() {
    return catchError<T, Observable<T>>((error: HttpErrorResponse) => {
      if (error.status === 401) {
        this.loginNeeded.set(Boolean(error.error?.login));
        this.signedOut.set(true);
      }
      return throwError(() => error);
    });
  }
}

/** What the bot said was wrong ({"error": ...}), or fallback if it said nothing. */
export function apiError(error: unknown, fallback: string): string {
  const said = (error as HttpErrorResponse | null)?.error?.error;
  return typeof said === 'string' && said ? said : fallback;
}
