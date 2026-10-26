import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  ElementRef,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';

import { Api, Preset, RadioSettings as Settings } from './api';
import { Icon } from './icon';
import { Reply, Runner } from './runner';
import { duration } from './time';

/** The frequency picker's choice for typing the four values. */
export const CUSTOM = 'custom';

/**
 * The radio's own settings (on the Radio page): what radio
 * shows, and, if the console may run radio, a form for each change: name,
 * TX power, position, clock, reboot, and last the frequency, bandwidth, SF
 * and CR, from MeshCore's presets or typed in. Those cut the node off from
 * radios on other settings, so the button waits for the node's name to be
 * typed, and the bot asks again (Confirm) and says how to go back. Changes
 * never go over the mesh: the console reaches the radio over USB.
 */
@Component({
  selector: 'mc-radio-settings',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Icon, Reply],
  providers: [Runner],
  styleUrl: './radio-settings.scss',
  templateUrl: './radio-settings.html',
})
export class RadioSettings {
  private readonly api = inject(Api);
  protected readonly runner = inject(Runner);
  /** Whether the console may run radio, so the changes are offered. */
  readonly canChange = input(false);
  protected readonly settings = signal<Settings | null>(null);
  protected readonly problem = signal<string | null>(null);
  protected readonly name = signal('');
  protected readonly power = signal('');
  protected readonly lat = signal('');
  protected readonly lon = signal('');
  /** A preset's title, or CUSTOM. */
  protected readonly preset = signal('');
  protected readonly freq = signal('');
  protected readonly bw = signal('');
  protected readonly sf = signal('');
  protected readonly cr = signal('');
  /** The node's name, typed to unlock the frequency change. */
  protected readonly typedName = signal('');
  protected readonly CUSTOM = CUSTOM;
  /** The bot's reply, at the top: brought into view, as the buttons are far below it. */
  private readonly reply = viewChild('reply', { read: ElementRef });

  /** The four values chosen, or null if they aren't all numbers. */
  protected readonly chosen = computed<Omit<Preset, 'title' | 'path_hash_size'> | null>(() => {
    const preset = this.settings()?.presets.find((p) => p.title === this.preset());
    if (preset) {
      return { freq: preset.freq, bw: preset.bw, sf: preset.sf, cr: preset.cr };
    }
    const typed = [this.freq(), this.bw(), this.sf(), this.cr()];
    const [freq, bw, sf, cr] = typed.map(Number);
    if (typed.some((t) => t.trim() === '') || ![freq, bw, sf, cr].every(Number.isFinite)) {
      return null;
    }
    return { freq, bw, sf, cr };
  });

  /** The chosen preset, if it suggests a path hash size: the radio command leaves that alone. */
  protected readonly pathHashNote = computed(
    () => this.settings()?.presets.find((p) => p.title === this.preset())?.path_hash_size ?? null,
  );

  /** Whether the chosen values are the radio's now. */
  protected readonly unchanged = computed(() => {
    const s = this.settings();
    const c = this.chosen();
    return !!s && !!c && c.freq === s.freq && c.bw === s.bw && c.sf === s.sf && c.cr === s.cr;
  });

  protected readonly freqReady = computed(
    () =>
      !!this.chosen() &&
      !this.unchanged() &&
      this.typedName().trim() !== '' &&
      this.typedName().trim() === this.settings()?.name,
  );

  constructor() {
    this.runner.onDone = () => this.load();
    this.load();
    effect(() => {
      if (this.runner.last()) {
        (this.reply()?.nativeElement as HTMLElement | undefined)?.scrollIntoView?.({
          block: 'nearest',
          behavior: 'smooth',
        });
      }
    });
  }

  load(): void {
    this.api.radio().subscribe({
      next: (settings) => {
        this.settings.set(settings);
        this.problem.set(null);
        if (settings) {
          this.name.set(settings.name ?? '');
          this.power.set(settings.tx_power === null ? '' : String(settings.tx_power));
          this.lat.set(settings.lat ? String(settings.lat) : '');
          this.lon.set(settings.lon ? String(settings.lon) : '');
          this.preset.set(this.startingPreset(settings));
          this.freq.set(settings.freq === null ? '' : String(settings.freq));
          this.bw.set(settings.bw === null ? '' : String(settings.bw));
          this.sf.set(settings.sf === null ? '' : String(settings.sf));
          this.cr.set(settings.cr === null ? '' : String(settings.cr));
          this.typedName.set('');
        }
      },
      error: () => this.problem.set("can't read the radio's settings"),
    });
  }

  /** The preset the radio is on: of several, one that suggests no path hash size. */
  private startingPreset(settings: Settings): string {
    const matching = settings.presets.filter((p) => settings.presets_matching.includes(p.title));
    return (matching.find((p) => p.path_hash_size === null) ?? matching[0])?.title ?? CUSTOM;
  }

  protected value(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement).value;
  }

  protected four(s: {
    freq: number | null;
    bw: number | null;
    sf: number | null;
    cr: number | null;
  }): string {
    return `${s.freq} MHz · BW ${s.bw} kHz · SF${s.sf} · CR${s.cr}`;
  }

  /** "right", "2m behind", "1h 5m ahead", or null if the radio didn't say. */
  protected clock(offset: number | null): string | null {
    if (offset === null) {
      return null;
    }
    if (Math.abs(offset) < 5) {
      return 'right';
    }
    return `${duration(Math.abs(offset))} ${offset > 0 ? 'ahead' : 'behind'}`;
  }

  protected run(text: string): void {
    this.runner.run('radio', text);
  }

  protected setFreq(): void {
    const c = this.chosen();
    if (!c || !this.freqReady()) {
      return;
    }
    const preset = this.settings()?.presets.find((p) => p.title === this.preset());
    this.run(preset ? `freq ${preset.title}` : `freq ${c.freq} ${c.bw} ${c.sf} ${c.cr}`);
  }
}
