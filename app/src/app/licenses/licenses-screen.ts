import { ChangeDetectionStrategy, Component, inject, InjectionToken, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { RouterLink } from '@angular/router';

import { Icon } from '../icon';

/** A package and its license, as the attribution lists it. */
export interface Attribution {
  name: string;
  license: string;
  /** Who holds the copyright, when the text doesn't say. */
  copyright?: string;
  text: string | null;
}

/** Reads one of the app's own files (the web view serves them), or null if it isn't there. */
export const READ_FILE = new InjectionToken<(path: string) => Promise<string | null>>('READ_FILE', {
  factory: () => async (path: string) => {
    try {
      const response = await fetch(path);
      return response.ok ? await response.text() : null;
    } catch {
      return null;
    }
  },
});

/**
 * The web build's notices (angular.json's production build writes them):
 * each package's name, license and text, between lines of dashes.
 */
export const BUILT = '3rdpartylicenses.txt';
/** Copied in by angular.json from node_modules. */
export const CAPACITOR_ANDROID = 'licenses/capacitor-android/LICENSE';
export const APACHE = 'licenses/apache-2.0/LICENSE.txt';

/**
 * The Android libraries in the APK, which the web build doesn't list: the
 * release runtime classpath (./gradlew :app:dependencies --configuration
 * releaseRuntimeClasspath, in android/), Capacitor's own code aside.
 */
export const ANDROID: Omit<Attribution, 'text'>[] = [
  { name: 'AndroidX', license: 'Apache-2.0', copyright: 'The Android Open Source Project' },
  {
    name: 'Apache Cordova (Android framework)',
    license: 'Apache-2.0',
    copyright: 'The Apache Software Foundation',
  },
  { name: 'Guava listenablefuture', license: 'Apache-2.0', copyright: 'The Guava Authors' },
  { name: 'JetBrains Java annotations', license: 'Apache-2.0', copyright: 'JetBrains s.r.o.' },
  { name: 'JSpecify', license: 'Apache-2.0', copyright: 'The JSpecify Authors' },
  {
    name: 'Kotlin standard library and kotlinx.coroutines',
    license: 'Apache-2.0',
    copyright: 'JetBrains s.r.o. and Kotlin Programming Language contributors',
  },
];

/** A license's text without its blank lines around: a centered title keeps its indent. */
function tidy(text: string | null | undefined): string | null {
  return text?.replace(/^\s*\n/, '').trimEnd() || null;
}

/** The packages in the web build's notices file. */
export function parseNotices(text: string): Attribution[] {
  return (
    text
      // Exactly 80 dashes between packages: a license may have shorter lines of them.
      .split(/^-{80}$/m)
      .map((block) => {
        const found = /^\s*Package: (.+)\nLicense: "?([^"\n]*)"?\n\n?([\s\S]*)$/.exec(block);
        return found
          ? { name: found[1].trim(), license: found[2].trim(), text: tidy(found[3]) }
          : null;
      })
      .filter((a): a is Attribution => a !== null)
  );
}

/** The open-source software in the app, and each one's license: opened from Radio. */
@Component({
  selector: 'mc-licenses',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, NgTemplateOutlet, RouterLink],
  styles: `
    :host {
      display: grid;
      gap: 16px;
    }
    .head {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .head h1 {
      margin: 0;
    }
    .panel {
      display: grid;
      gap: 4px;
    }
    h2,
    p {
      margin: 0;
    }
    h2 {
      margin-bottom: 8px;
    }
    details + details {
      border-top: 1px solid var(--line);
    }
    details > summary {
      padding: 10px 0;
    }
    .name {
      flex: 1;
      font-weight: 600;
      overflow-wrap: anywhere;
    }
    .license {
      flex: none;
      color: var(--muted);
      font-size: 0.85rem;
    }
    pre {
      margin: 0 0 12px;
      padding: 10px 12px;
      max-height: 50vh;
      overflow: auto;
      border-radius: 8px;
      background: var(--ink);
      color: var(--muted);
      font-family: var(--mono);
      font-size: 0.75rem;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
  `,
  template: `
    <div class="head">
      <a class="btn btn-ghost btn-sm" routerLink="/radio" aria-label="Back to Radio">‹</a>
      <h1><mc-icon name="list" /> Open-source licenses</h1>
    </div>
    <p class="muted">
      Mesh Contingency is built on open-source software. Thank you to the people who make it. Each
      package is listed with its license and copyright notice.
    </p>

    @if (loading()) {
      <p class="loading" role="status"><span class="spinner"></span> Reading the licenses…</p>
    } @else {
      <section class="panel app">
        <h2>In the app</h2>
        @for (a of app(); track a.name) {
          <ng-container *ngTemplateOutlet="entry; context: { $implicit: a }" />
        } @empty {
          <p class="muted">
            The list is written when the app is built for a phone; this build doesn't have it.
          </p>
        }
      </section>

      <section class="panel android">
        <h2>Android</h2>
        @for (a of android(); track a.name) {
          <ng-container *ngTemplateOutlet="entry; context: { $implicit: a }" />
        }
      </section>
    }

    <ng-template #entry let-a>
      <details class="accordion">
        <summary>
          <span class="name">{{ a.name }}</span>
          <span class="license">{{ a.license }}</span>
        </summary>
        @if (a.copyright) {
          <p class="muted">Copyright {{ a.copyright }}</p>
        }
        @if (a.text) {
          <pre>{{ a.text }}</pre>
        }
      </details>
    </ng-template>
  `,
})
export class LicensesScreen {
  private readonly read = inject(READ_FILE);

  protected readonly loading = signal(true);
  protected readonly app = signal<Attribution[]>([]);
  protected readonly android = signal<Attribution[]>([]);

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    const [built, capacitor, apache] = await Promise.all([
      this.read(BUILT),
      this.read(CAPACITOR_ANDROID),
      this.read(APACHE),
    ]);
    this.app.set(built ? parseNotices(built) : []);
    this.android.set([
      { name: 'Capacitor (Android)', license: 'MIT', text: tidy(capacitor) },
      ...ANDROID.map((a) => ({ ...a, text: tidy(apache) })),
    ]);
    this.loading.set(false);
  }
}
