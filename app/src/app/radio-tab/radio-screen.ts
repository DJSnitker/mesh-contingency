import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { ChatHistory } from '../chat/chat-history';
import { Icon } from '../icon';
import { NodeLink } from '../node/node-link';
import presetFile from '../radio/presets.json';
import { DEVICE } from '../device';
import { Frequency, Radio, RadioContact } from '../radio/radio';

/** MeshCore's regional presets, as the bot's radio command offers them. */
export interface Preset extends Frequency {
  title: string;
}
export const PRESETS: Preset[] = presetFile.presets;
/** The frequency picker's choice for typing the four values. */
export const CUSTOM = 'custom';
/** The bandwidths a LoRa radio can use (kHz), as the bot checks. */
export const BANDWIDTHS = [7.8, 10.4, 15.6, 20.8, 31.25, 41.7, 62.5, 125, 250, 500];

const TYPES: Record<number, string> = {
  1: 'Companion',
  2: 'Repeater',
  3: 'Room server',
  4: 'Sensor',
};

/** "910.525 MHz · BW 62.5 kHz · SF7 · CR5" */
export function frequencyText(f: Frequency): string {
  return `${f.freq} MHz · BW ${f.bw} kHz · SF${f.sf} · CR${f.cr}`;
}

/** The presets with these four values. */
export function matching(f: Frequency | null): string[] {
  return f
    ? PRESETS.filter(
        (p) => p.freq === f.freq && p.bw === f.bw && p.sf === f.sf && p.cr === f.cr,
      ).map((p) => p.title)
    : [];
}

/** Why the four values aren't ones a radio takes, as the bot says; null when they are. */
export function frequencyProblem(f: Frequency): string | null {
  if (!(f.freq >= 150 && f.freq <= 960)) {
    return 'The frequency is 150 to 960 MHz.';
  }
  if (!BANDWIDTHS.includes(f.bw)) {
    return `The bandwidth is one of ${BANDWIDTHS.join(', ')} kHz.`;
  }
  if (!(Number.isInteger(f.sf) && f.sf >= 5 && f.sf <= 12)) {
    return 'SF is 5 to 12.';
  }
  if (!(Number.isInteger(f.cr) && f.cr >= 5 && f.cr <= 8)) {
    return 'CR is 5 to 8.';
  }
  return null;
}

/** "right", "5m behind", "1h 5m ahead". */
export function clockWords(offset: number): string {
  const seconds = Math.abs(offset);
  if (seconds < 60) {
    return 'right';
  }
  const minutes = Math.round(seconds / 60);
  const span =
    minutes < 60
      ? `${minutes}m`
      : minutes < 1440
        ? `${Math.floor(minutes / 60)}h ${minutes % 60}m`
        : `${Math.floor(minutes / 1440)}d`;
  return `${span} ${offset < 0 ? 'behind' : 'ahead'}`;
}

/**
 * The Radio tab: the user's own radio, over Bluetooth (never the node's).
 * What it says about itself; adverts; its name, TX power, position and
 * whether adverts share it, and clock; its frequency, bandwidth, SF and CR
 * by preset or by value, which asks first and says how to go back; and its
 * contacts, to remove one or reset the path to one.
 */
@Component({
  selector: 'mc-radio',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, Icon, RouterLink],
  styles: `
    .busy {
      position: sticky;
      bottom: 0;
      padding: 10px 14px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--ink-2);
      box-shadow: 0 -4px 16px rgb(0 0 0 / 40%);
    }
    .panel {
      display: grid;
      gap: 12px;
    }
    h2,
    p {
      margin: 0;
    }
    dl {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 6px 16px;
      margin: 0;
      overflow-wrap: anywhere;
    }
    dt {
      color: var(--muted);
    }
    dd {
      margin: 0;
    }
    .attention {
      color: var(--orange);
    }
    .row {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    select {
      width: 100%;
    }
    .confirm {
      display: grid;
      gap: 10px;
      padding: 12px;
      border: 1px solid var(--orange);
      border-radius: 10px;
      background: rgb(255 95 31 / 8%);
    }
    ul {
      display: grid;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    li {
      display: grid;
      gap: 6px;
      padding: 10px 0;
    }
    li + li {
      border-top: 1px solid var(--line);
    }
    .contact-name {
      font-weight: 600;
    }
  `,
  template: `
    <h1><mc-icon name="sliders" /> Radio</h1>

    @if (radio.state() !== 'connected') {
      <section class="panel">
        @if (radio.problem(); as problem) {
          <p class="said">{{ problem }}</p>
        }
        @if (radio.state() === 'connecting') {
          <p class="loading" role="status">
            <span class="spinner"></span> Connecting to your radio…
          </p>
        } @else if (radio.hasRemembered()) {
          <div class="actions">
            <button
              class="btn btn-sm"
              type="button"
              [disabled]="radio.state() === 'connecting'"
              (click)="radio.reconnect()"
            >
              Connect again
            </button>
          </div>
        } @else {
          <p class="muted">
            Connect your radio first, on the <a routerLink="/node">Node</a> screen.
          </p>
        }
      </section>
    } @else {
      @if (said(); as message) {
        <p class="said" role="status">{{ message }}</p>
      }

      <section class="panel about">
        <h2>Your radio</h2>
        <dl>
          <dt>Name</dt>
          <dd class="name">{{ radio.name() }}</dd>
          @if (radio.frequency(); as f) {
            <dt>Frequency</dt>
            <dd class="frequency">
              {{ text(f) }}
              @if (presetsNow().length) {
                <span class="muted">({{ presetsNow().join(', ') }})</span>
              }
            </dd>
          }
          @if (radio.self(); as self) {
            <dt>TX power</dt>
            <dd class="power">
              {{ self.txPower }} dBm <span class="muted">of {{ self.maxTxPower }}</span>
            </dd>
            <dt>Position</dt>
            <dd class="position">
              @if (self.advLat || self.advLon) {
                {{ self.advLat / 1e6 }}, {{ self.advLon / 1e6 }}
                <span class="muted"
                  >({{ radio.sharesPosition() ? 'in adverts' : 'not in adverts' }})</span
                >
              } @else {
                <span class="muted">none</span>
              }
            </dd>
          }
          <dt>Clock</dt>
          <dd class="clock" [class.attention]="clock() !== 'right'">
            {{ clock() ?? "the radio didn't say" }}
          </dd>
          @if (radio.batteryMilliVolts(); as mv) {
            <dt>Battery</dt>
            <dd>{{ (mv / 1000).toFixed(2) }} V</dd>
          }
          @if (radio.firmware(); as firmware) {
            <dt>Firmware</dt>
            <dd>{{ firmware }}</dd>
          }
        </dl>
        <div class="actions">
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            [disabled]="busy() || history.loadingContacts()"
            (click)="refresh()"
          >
            Refresh
          </button>
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            [disabled]="busy()"
            (click)="setClock()"
          >
            Set the clock from the {{ device }}
          </button>
        </div>
      </section>

      <section class="panel adverts">
        <h2>Adverts</h2>
        <p class="muted">An advert tells other radios yours is there, so they can message it.</p>
        <div class="actions">
          <button class="btn btn-sm" type="button" [disabled]="busy()" (click)="advert('zero-hop')">
            Advert nearby
          </button>
          <button class="btn btn-sm" type="button" [disabled]="busy()" (click)="advert('flood')">
            Advert across the mesh
          </button>
        </div>
      </section>

      <section class="panel settings">
        <h2>Settings</h2>
        <label class="field">
          Name
          <input
            name="radio-name"
            maxlength="31"
            [value]="newName()"
            (input)="newName.set(value($event))"
          />
        </label>
        <div class="actions">
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            [disabled]="busy() || !newName().trim() || newName().trim() === radio.name()"
            (click)="rename()"
          >
            Rename
          </button>
          <span class="muted">Others see it after the next advert.</span>
        </div>

        <label class="field">
          TX power (dBm)
          <input
            name="power"
            type="number"
            min="1"
            [max]="radio.self()?.maxTxPower ?? 30"
            [value]="power()"
            (input)="power.set(value($event))"
          />
        </label>
        <div class="actions">
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            [disabled]="busy() || !powerOk()"
            (click)="setPower()"
          >
            Set power
          </button>
        </div>

        <div class="row">
          <label class="field">
            Latitude
            <input
              name="lat"
              inputmode="decimal"
              [value]="lat()"
              (input)="lat.set(value($event))"
            />
          </label>
          <label class="field">
            Longitude
            <input
              name="lon"
              inputmode="decimal"
              [value]="lon()"
              (input)="lon.set(value($event))"
            />
          </label>
        </div>
        <div class="actions">
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            [disabled]="busy() || !positionOk()"
            (click)="setPosition()"
          >
            Set position
          </button>
          <button class="btn btn-ghost btn-sm" type="button" [disabled]="busy()" (click)="share()">
            {{ radio.sharesPosition() ? 'Stop sharing it in adverts' : 'Share it in adverts' }}
          </button>
        </div>
      </section>

      <section class="panel frequency-change">
        <h2>Frequency</h2>
        <p class="muted">
          Every radio on the mesh uses the same settings: a radio on others hears no one. Change
          them only when the mesh does.
        </p>
        <label class="field">
          Preset
          <select name="preset" [value]="preset()" (change)="choose(value($event))">
            @for (p of presets; track p.title) {
              <option [value]="p.title">{{ p.title }}</option>
            }
            <option [value]="CUSTOM">My own values</option>
          </select>
        </label>
        @if (preset() === CUSTOM) {
          <div class="row">
            <label class="field">
              MHz
              <input
                name="freq"
                inputmode="decimal"
                [value]="freq()"
                (input)="freq.set(value($event))"
              />
            </label>
            <label class="field">
              Bandwidth (kHz)
              <input name="bw" inputmode="decimal" [value]="bw()" (input)="bw.set(value($event))" />
            </label>
            <label class="field">
              SF
              <input name="sf" inputmode="numeric" [value]="sf()" (input)="sf.set(value($event))" />
            </label>
            <label class="field">
              CR
              <input name="cr" inputmode="numeric" [value]="cr()" (input)="cr.set(value($event))" />
            </label>
          </div>
          @if (chosenProblem(); as problem) {
            <p class="muted">{{ problem }}</p>
          }
        }
        <div class="actions">
          <button
            class="btn btn-sm"
            type="button"
            [disabled]="busy() || !chosen() || unchanged()"
            (click)="asking.set(true)"
          >
            Set the frequency
          </button>
          @if (unchanged()) {
            <span class="muted">Your radio is on these now.</span>
          }
        </div>
        @if (asking() && chosen(); as c) {
          <div class="confirm" role="alertdialog" aria-labelledby="freq-confirm">
            <p id="freq-confirm">
              Set your radio to {{ text(c) }} and restart it? Radios on other settings won't hear
              yours, and you won't hear them.
              @if (radio.frequency(); as was) {
                To go back, set {{ backTo(was) }}.
              }
            </p>
            <div class="actions">
              <button
                class="btn btn-sm"
                type="button"
                [disabled]="busy()"
                (click)="setFrequency(c)"
              >
                Set and restart
              </button>
              <button class="btn btn-ghost btn-sm" type="button" (click)="asking.set(false)">
                Cancel
              </button>
            </div>
          </div>
        }
      </section>

      <section class="panel contacts">
        <h2>Contacts</h2>
        @if (history.loadingContacts()) {
          <p class="loading" role="status">
            <span class="spinner"></span> Reading the contacts from your radio…
          </p>
        } @else if (contacts().length) {
          <ul>
            @for (c of contacts(); track c.publicKey) {
              <li>
                <span class="contact-name">{{ c.name }}</span>
                <span class="muted">
                  {{ type(c) }} · {{ path(c) }}
                  @if (c.lastAdvert) {
                    · heard {{ c.lastAdvert * 1000 | date: 'MMM d, h:mm a' }}
                  }
                </span>
                <div class="actions">
                  <button
                    class="btn btn-ghost btn-sm"
                    type="button"
                    [disabled]="busy() || c.hops === null"
                    (click)="resetPath(c)"
                  >
                    Reset path
                  </button>
                  <button
                    class="btn btn-ghost btn-sm danger"
                    type="button"
                    [disabled]="busy()"
                    (click)="remove(c)"
                  >
                    Remove
                  </button>
                </div>
              </li>
            }
          </ul>
        } @else {
          <p class="muted">No contacts yet: they're added as the radio hears their adverts.</p>
        }
        @if (isNode(); as name) {
          <p class="muted">
            Removing {{ name }}, the node, means the app can't reach it until its next advert is
            heard.
          </p>
        }
      </section>

      @if (busy()) {
        <p class="busy loading" role="status"><span class="spinner small"></span> {{ doing() }}</p>
      }
    }

    <ul class="more">
      <li>
        <a routerLink="/radio/licenses"><mc-icon name="list" /> Open-source licenses</a>
      </li>
    </ul>
  `,
})
export class RadioScreen {
  protected readonly radio = inject(Radio);
  protected readonly device = inject(DEVICE);
  private readonly link = inject(NodeLink);
  protected readonly presets = PRESETS;
  protected readonly CUSTOM = CUSTOM;

  protected readonly history = inject(ChatHistory);

  protected readonly busy = signal(false);
  /** What it's doing with the radio while busy. */
  protected readonly doing = signal('');
  protected readonly said = signal<string | null>(null);
  /** The radio's contacts, every type (as read for Chat too). */
  protected readonly contacts = computed(() => this.history.contacts() ?? []);

  protected readonly newName = signal('');
  protected readonly power = signal('');
  protected readonly lat = signal('');
  protected readonly lon = signal('');

  protected readonly preset = signal<string>(CUSTOM);
  protected readonly freq = signal('');
  protected readonly bw = signal('');
  protected readonly sf = signal('');
  protected readonly cr = signal('');
  protected readonly asking = signal(false);

  protected readonly presetsNow = computed(() => matching(this.radio.frequency()));
  protected readonly clock = computed(() => {
    const offset = this.radio.clockOffset();
    return offset === null ? null : clockWords(offset);
  });
  protected readonly powerOk = computed(() => {
    const dBm = Number(this.power());
    const max = this.radio.self()?.maxTxPower ?? 30;
    return Number.isInteger(dBm) && dBm >= 1 && dBm <= max && dBm !== this.radio.self()?.txPower;
  });
  protected readonly positionOk = computed(() => {
    const [lat, lon] = [this.lat(), this.lon()].map((v) => (v.trim() ? Number(v) : NaN));
    return Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
  });
  /** The four values typed, whether or not a radio takes them. */
  private readonly typed = computed<Frequency | null>(() => {
    const values = [this.freq(), this.bw(), this.sf(), this.cr()];
    if (values.some((v) => !v.trim())) {
      return null;
    }
    const [freq, bw, sf, cr] = values.map(Number);
    return { freq, bw, sf, cr };
  });
  protected readonly chosenProblem = computed(() => {
    const typed = this.typed();
    return typed ? frequencyProblem(typed) : null;
  });
  /** The four values chosen, when a radio takes them. */
  protected readonly chosen = computed<Frequency | null>(() => {
    const preset = PRESETS.find((p) => p.title === this.preset());
    if (preset) {
      return { freq: preset.freq, bw: preset.bw, sf: preset.sf, cr: preset.cr };
    }
    const typed = this.typed();
    return typed && !frequencyProblem(typed) ? typed : null;
  });
  protected readonly unchanged = computed(() => {
    const [now, chosen] = [this.radio.frequency(), this.chosen()];
    return !!now && !!chosen && frequencyText(now) === frequencyText(chosen);
  });
  /** The node's name, when it's one of the contacts. */
  protected readonly isNode = computed(
    () => this.contacts().find((c) => c.publicKey === this.link.node()?.publicKey)?.name ?? null,
  );

  constructor() {
    // On connecting: read everything, and start the fields from it.
    effect(() => {
      if (this.radio.state() === 'connected') {
        void this.refresh(false);
      }
    });
  }

  protected value(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement).value;
  }

  protected text(f: Frequency): string {
    return frequencyText(f);
  }

  /** How to go back to the settings now: their preset, or the values. */
  protected backTo(was: Frequency): string {
    const titles = matching(was);
    return titles.length ? `the ${titles[0]} preset` : `my own values ${frequencyText(was)}`;
  }

  protected type(c: RadioContact): string {
    return TYPES[c.type] ?? `Type ${c.type}`;
  }

  protected path(c: RadioContact): string {
    if (c.hops === null) {
      return 'no path yet (messages flood)';
    }
    return c.hops === 0 ? 'direct' : `${c.hops} hop${c.hops === 1 ? '' : 's'}`;
  }

  protected choose(title: string): void {
    this.preset.set(title);
    this.asking.set(false);
  }

  /** Read its settings, then its contacts (again, or only if not read since it connected). */
  protected async refresh(again = true): Promise<void> {
    await this.run(null, 'Reading your radio…', async () => {
      await this.radio.refresh();
      this.fill();
    });
    this.history.refresh(again).catch(() => undefined);
  }

  protected async setClock(): Promise<void> {
    await this.run(`The clock is set from the ${this.device}.`, 'Setting the clock…', () =>
      this.radio.setClock(),
    );
  }

  protected async advert(kind: 'flood' | 'zero-hop'): Promise<void> {
    await this.run(
      kind === 'flood' ? 'Advert sent across the mesh.' : 'Advert sent to radios nearby.',
      'Sending the advert…',
      () => this.radio.advert(kind),
    );
  }

  protected async rename(): Promise<void> {
    const name = this.newName().trim();
    await this.run(`Renamed ${name}. Others see it after the next advert.`, 'Renaming…', () =>
      this.radio.rename(name),
    );
  }

  protected async setPower(): Promise<void> {
    const dBm = Number(this.power());
    await this.run(`TX power set to ${dBm} dBm.`, 'Setting the power…', () =>
      this.radio.setPower(dBm),
    );
  }

  protected async setPosition(): Promise<void> {
    const [lat, lon] = [Number(this.lat()), Number(this.lon())];
    await this.run(`Position set to ${lat}, ${lon}.`, 'Setting the position…', () =>
      this.radio.setPosition(lat, lon),
    );
  }

  protected async share(): Promise<void> {
    const share = !this.radio.sharesPosition();
    await this.run(
      share ? 'Adverts now share its position.' : 'Adverts no longer share its position.',
      'Changing its adverts…',
      () => this.radio.sharePosition(share),
    );
  }

  protected async setFrequency(f: Frequency): Promise<void> {
    this.asking.set(false);
    // The radio restarts: the screen then says so, and offers to connect again.
    await this.run(null, 'Setting the frequency and restarting…', () => this.radio.setFrequency(f));
  }

  protected async resetPath(c: RadioContact): Promise<void> {
    await this.run(
      `The path to ${c.name} is reset: the next message finds a new one.`,
      'Resetting the path…',
      async () => {
        await this.radio.resetPath(c.publicKey);
        await this.history.refresh(true);
      },
    );
  }

  protected async remove(c: RadioContact): Promise<void> {
    if (
      !confirm(
        `Remove ${c.name} from your radio's contacts? It's added again when its next advert is heard.`,
      )
    ) {
      return;
    }
    await this.run(`Removed ${c.name}.`, `Removing ${c.name}…`, async () => {
      await this.radio.removeContact(c.publicKey);
      await this.history.refresh(true);
    });
  }

  /** Do something with the radio, saying what while it does, and how it went. */
  private async run(
    done: string | null,
    doing: string,
    action: () => Promise<void>,
  ): Promise<void> {
    this.doing.set(doing);
    this.busy.set(true);
    this.said.set(null);
    try {
      await action();
      this.said.set(done);
    } catch (error) {
      this.said.set(`Didn't work: ${error instanceof Error ? error.message : String(error)}.`);
    } finally {
      this.busy.set(false);
    }
  }

  /** Start the fields from what the radio says now. */
  private fill(): void {
    const self = this.radio.self();
    this.newName.set(this.radio.name() ?? '');
    this.power.set(self ? String(self.txPower) : '');
    this.lat.set(self?.advLat ? String(self.advLat / 1e6) : '');
    this.lon.set(self?.advLon ? String(self.advLon / 1e6) : '');
    const now = this.radio.frequency();
    this.preset.set(matching(now)[0] ?? CUSTOM);
    this.freq.set(now ? String(now.freq) : '');
    this.bw.set(now ? String(now.bw) : '');
    this.sf.set(now ? String(now.sf) : '');
    this.cr.set(now ? String(now.cr) : '');
  }
}
