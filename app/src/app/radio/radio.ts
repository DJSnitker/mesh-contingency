import { computed, inject, Injectable, signal } from '@angular/core';
import type { SelfInfo } from '@liamcottle/meshcore.js/src/connection/connection.js';

import { BLE, SERVICE } from './ble';
import { CapacitorBleConnection, within } from './ble-connection';

/** How long the radio has to answer once connected (ms). */
export const ANSWER_MS = 10000;

/** Where the last radio is remembered, to reconnect to when the app opens. */
export const REMEMBERED = 'mc.radio';

export type RadioState = 'none' | 'connecting' | 'connected' | 'lost';

/** The radio as the app remembers it: enough to reconnect and to name it. */
interface Remembered {
  deviceId: string;
  name: string;
}

/**
 * The user's own companion radio, over Bluetooth: connecting to it, what it
 * says about itself, and the connection the other screens send through.
 */
@Injectable({ providedIn: 'root' })
export class Radio {
  private readonly ble = inject(BLE);
  private initialized = false;

  readonly state = signal<RadioState>('none');
  /** The radio's name, as it reports it (or as remembered, until it does). */
  readonly name = signal<string | null>(this.remembered()?.name ?? null);
  readonly self = signal<SelfInfo | null>(null);
  readonly batteryMilliVolts = signal<number | null>(null);
  readonly firmware = signal<string | null>(null);
  /** Why the last connect failed, or why the radio went away. */
  readonly problem = signal<string | null>(null);
  readonly hasRemembered = computed(() => this.name() !== null);

  /** The open connection, while connected. */
  connection: CapacitorBleConnection | null = null;

  /** Ask the phone to scan for MeshCore radios, and connect to the one picked. */
  async pick(): Promise<void> {
    let deviceId: string;
    this.problem.set(null);
    try {
      await this.initialize();
      const device = await this.ble.requestDevice({ services: [SERVICE] });
      deviceId = device.deviceId;
    } catch (error) {
      // Cancelling the phone's list isn't a problem worth showing.
      if (!/cancel/i.test(String(error))) {
        this.problem.set(describe(error));
      }
      return;
    }
    await this.connect(deviceId);
  }

  /** Connect to the radio remembered from last time, if there is one. */
  async reconnect(): Promise<void> {
    const remembered = this.remembered();
    if (remembered) {
      await this.connect(remembered.deviceId);
    }
  }

  async disconnect(): Promise<void> {
    const connection = this.connection;
    this.connection = null;
    this.state.set('none');
    await connection?.close();
  }

  /** Disconnect, and don't reconnect to this radio when the app opens. */
  async forget(): Promise<void> {
    await this.disconnect();
    try {
      localStorage.removeItem(REMEMBERED);
    } catch {
      // Nothing was stored, then.
    }
    this.name.set(null);
    this.self.set(null);
    this.batteryMilliVolts.set(null);
    this.firmware.set(null);
  }

  private async connect(deviceId: string): Promise<void> {
    if (this.state() === 'connecting') {
      return;
    }
    await this.disconnect();
    this.state.set('connecting');
    this.problem.set(null);
    const connection = new CapacitorBleConnection(this.ble, deviceId);
    try {
      await this.initialize();
      await connection.open();
      const self = await within(connection.getSelfInfo(), ANSWER_MS, 'its name');
      // Messages are dated by the radio's clock, so set it from the phone's.
      await within(connection.syncDeviceTime(), ANSWER_MS, 'setting its clock').catch(
        () => undefined,
      );
      const battery = await within(connection.getBatteryVoltage(), ANSWER_MS, 'its battery').catch(
        () => null,
      );

      this.connection = connection;
      this.self.set(self);
      this.name.set(self.name);
      this.batteryMilliVolts.set(battery?.batteryMilliVolts ?? null);
      this.firmware.set(connection.firmware);
      this.state.set('connected');
      this.remember({ deviceId, name: self.name });
      connection.on('disconnected', () => {
        if (this.connection === connection) {
          this.connection = null;
          this.state.set('lost');
          this.problem.set('The radio went out of range or was turned off.');
        }
      });
    } catch (error) {
      await connection.close();
      this.state.set('none');
      this.problem.set(describe(error));
    }
  }

  private async initialize(): Promise<void> {
    if (!this.initialized) {
      // The app never works out where the phone is from what it scans, so
      // Android 12+ asks only for Nearby devices (AndroidManifest.xml).
      await this.ble.initialize({ androidNeverForLocation: true });
      this.initialized = true;
    }
  }

  private remembered(): Remembered | null {
    try {
      const stored = JSON.parse(localStorage.getItem(REMEMBERED) ?? 'null');
      return typeof stored?.deviceId === 'string' && typeof stored?.name === 'string'
        ? stored
        : null;
    } catch {
      return null;
    }
  }

  private remember(radio: Remembered): void {
    try {
      localStorage.setItem(REMEMBERED, JSON.stringify(radio));
    } catch {
      // Then it's picked again next time.
    }
  }
}

/** What went wrong, for the user. */
export function describe(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error ?? '');
  if (/not enabled|disabled|turned off/i.test(text)) {
    return 'Bluetooth is off. Turn it on, then try again.';
  }
  if (/permission|denied|not allowed/i.test(text)) {
    return 'The app needs the Nearby devices permission to find your radio (Android settings, Apps, Mesh Contingency).';
  }
  if (/didn't answer/.test(text)) {
    return `Connected, but ${text}. Try again, or restart the radio.`;
  }
  return (
    "Couldn't connect to the radio. If the MeshCore app (or another phone) is connected to it, " +
    'disconnect that first: a radio takes one at a time.' +
    (text ? ` (${text})` : '')
  );
}
