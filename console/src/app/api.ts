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

  /** The live log: the lines kept so far, then each new one. */
  log(): EventSource {
    return new EventSource('/api/log');
  }

  private get<T>(url: string): Observable<T> {
    return this.http.get<T>(url).pipe(
      catchError((error: HttpErrorResponse) => {
        if (error.status === 401) {
          this.signedOut.set(true);
        }
        return throwError(() => error);
      }),
    );
  }
}
