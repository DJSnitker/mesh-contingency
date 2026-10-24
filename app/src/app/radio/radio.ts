import { computed, inject, Injectable, signal } from '@angular/core';
import type { Sent, SelfInfo } from '@liamcottle/meshcore.js/src/connection/connection.js';
import Constants from '@liamcottle/meshcore.js/src/constants.js';
import { Subject } from 'rxjs';

import { BLE, SERVICE } from './ble';
import { CapacitorBleConnection, within } from './ble-connection';
import { fromHex, toHex } from './hex';

/** How long the radio has to answer once connected (ms). */
export const ANSWER_MS = 10000;
/** Tries at a direct message before it's not delivered, as MeshCore's own app makes. */
export const SEND_ATTEMPTS = 3;
/** The least time to wait for a direct message's acknowledgement (ms). */
export const MIN_ACK_MS = 5000;

/** A companion radio's contact type, as the node's radio is. */
export const COMPANION = 1;

/** One of the radio's contacts, with its key as hex. */
export interface RadioContact {
  publicKey: string;
  name: string;
  type: number;
}

/** A direct message the radio received. */
export interface DirectMessage {
  /** The first 6 bytes of the sender's key, as hex (12 characters). */
  from: string;
  text: string;
  receivedAt: number;
}

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

  /** Direct messages as they arrive (channel messages are for the Chat step). */
  readonly messages = new Subject<DirectMessage>();
  private draining = false;
  private drainAgain = false;

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

  /** The radio's contacts, by name. */
  async contacts(): Promise<RadioContact[]> {
    const contacts = await within(this.open().getContacts(), ANSWER_MS, 'its contacts');
    return contacts
      .map((c) => ({ publicKey: toHex(c.publicKey), name: c.advName, type: c.type }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  /** Advertise the radio across the mesh, so others (the node) learn it. */
  async advert(): Promise<void> {
    await within(this.open().sendFloodAdvert(), ANSWER_MS, 'sending an advert');
  }

  /**
   * Send a direct message, trying again while the recipient doesn't
   * acknowledge it, as MeshCore's own app does. True once acknowledged.
   * `onAttempt` hears each try (from 1).
   */
  async sendText(
    publicKey: string,
    text: string,
    onAttempt?: (attempt: number) => void,
  ): Promise<boolean> {
    const connection = this.open();
    const acks = new Set<number>();
    let heard: (() => void) | null = null;
    const onAck = (ack: { ackCode: number }) => {
      acks.add(ack.ackCode);
      heard?.();
    };
    connection.on(Constants.PushCodes['SendConfirmed'], onAck);
    try {
      // The same timestamp each try, so they're the same message.
      const timestamp = Math.floor(Date.now() / 1000);
      for (let attempt = 0; attempt < SEND_ATTEMPTS; attempt++) {
        onAttempt?.(attempt + 1);
        const sent = await within(
          this.whenSent(connection, () =>
            connection.sendCommandSendTxtMsg(0, attempt, timestamp, fromHex(publicKey), text),
          ),
          ANSWER_MS,
          'sending',
        );
        const wait = Math.max(sent.estTimeout * 1.2, MIN_ACK_MS);
        const acked = await new Promise<boolean>((resolve) => {
          const timer = setTimeout(() => resolve(acks.has(sent.expectedAckCrc)), wait);
          heard = () => {
            if (acks.has(sent.expectedAckCrc)) {
              clearTimeout(timer);
              resolve(true);
            }
          };
          heard();
        });
        heard = null;
        if (acked) {
          return true;
        }
      }
      return false;
    } finally {
      connection.off(Constants.PushCodes['SendConfirmed'], onAck);
    }
  }

  /** The open connection; throws when there's none. */
  private open(): CapacitorBleConnection {
    if (!this.connection) {
      throw new Error('no radio connected');
    }
    return this.connection;
  }

  /** Send, and resolve with the radio's Sent answer (or reject on its error). */
  private whenSent(connection: CapacitorBleConnection, send: () => Promise<void>): Promise<Sent> {
    return new Promise<Sent>((resolve, reject) => {
      const onSent = (sent: Sent) => {
        connection.off(Constants.ResponseCodes['Err'], onErr);
        resolve(sent);
      };
      const onErr = () => {
        connection.off(Constants.ResponseCodes['Sent'], onSent);
        reject(new Error('the radio refused the message'));
      };
      connection.once(Constants.ResponseCodes['Sent'], onSent);
      connection.once(Constants.ResponseCodes['Err'], onErr);
      send().catch(reject);
    });
  }

  /** Fetch the messages waiting on the radio, until there are none. */
  private async drain(connection: CapacitorBleConnection): Promise<void> {
    if (this.draining) {
      this.drainAgain = true;
      return;
    }
    this.draining = true;
    try {
      do {
        this.drainAgain = false;
        for (;;) {
          const next = await within(connection.syncNextMessage(), ANSWER_MS, 'its messages').catch(
            () => null,
          );
          if (!next || this.connection !== connection) {
            break;
          }
          if (next.contactMessage) {
            this.messages.next({
              from: toHex(next.contactMessage.pubKeyPrefix),
              text: next.contactMessage.text,
              receivedAt: Date.now(),
            });
          }
        }
      } while (this.drainAgain);
    } finally {
      this.draining = false;
    }
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
      // The radio says when messages are waiting; fetch any from meanwhile too.
      connection.on(Constants.PushCodes['MsgWaiting'], () => void this.drain(connection));
      void this.drain(connection);
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
