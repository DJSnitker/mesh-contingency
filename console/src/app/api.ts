import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';

/** GET /api/overview (mesh_contingency/web/api.py). Times are seconds since 1970. */
export interface Overview {
  node: string | null;
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
}

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
