import { computed, inject, Injectable, signal } from '@angular/core';
import type { Sent, SelfInfo } from '@liamcottle/meshcore.js/src/connection/connection.js';
import Constants from '@liamcottle/meshcore.js/src/constants.js';
import { Subject } from 'rxjs';

import { BLE, SERVICE } from './ble';
import { CapacitorBleConnection, within } from './ble-connection';
import { Port, PortInfo, SERIAL } from './serial';
import { UsbConnection } from './usb-connection';
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
  /** Hops on the path the radio knows to it, or null to flood (none known). */
  hops: number | null;
  /** When its last advert was heard (seconds since 1970, by its clock), or 0. */
  lastAdvert: number;
}

/** A radio's frequency (MHz), bandwidth (kHz), spreading factor and coding rate. */
export interface Frequency {
  freq: number;
  bw: number;
  sf: number;
  cr: number;
}

/** A direct message the radio received. */
export interface DirectMessage {
  /** The first 6 bytes of the sender's key, as hex (12 characters). */
  from: string;
  text: string;
  receivedAt: number;
}

/** One of the radio's channels: its slot, and its name ("Public", "#contingency-wx"). */
export interface RadioChannel {
  index: number;
  name: string;
}

/** A message the radio heard on one of its channels. */
export interface ChannelMessage {
  /** The channel's slot. */
  channel: number;
  /** As sent: "<sender's name>: <text>". */
  text: string;
  receivedAt: number;
}

/** Where the last radio is remembered, to reconnect to when the app opens. */
export const REMEMBERED = 'mc.radio';

export type RadioState = 'none' | 'connecting' | 'connected' | 'lost';

/** How the radio is reached: Bluetooth, or a USB cable (on a computer). */
export type Via = 'bluetooth' | 'usb';

/** A connection to the radio, either way. */
export type RadioLink = CapacitorBleConnection | UsbConnection;

/** The radio as the app remembers it: enough to reconnect and to name it. */
interface Remembered {
  /** Missing in what the app remembered before USB: Bluetooth. */
  via?: Via;
  /** Its Bluetooth device, or "" over USB. */
  deviceId: string;
  /** Its USB port's maker and model, to find the port again. */
  usb?: PortInfo;
  name: string;
}

/**
 * The user's own companion radio, over Bluetooth or (on a computer, with
 * Web Serial) a USB cable: connecting to it, what it says about itself, and
 * the connection the other screens send through.
 */
@Injectable({ providedIn: 'root' })
export class Radio {
  private readonly ble = inject(BLE);
  private readonly serial = inject(SERIAL);
  /** Whether a radio on a USB cable can be used here: on a computer, not a phone. */
  readonly canUseUsb = this.serial !== null;
  private initialized = false;

  readonly state = signal<RadioState>('none');
  /** The radio's name, as it reports it (or as remembered, until it does). */
  readonly name = signal<string | null>(this.remembered()?.name ?? null);
  readonly self = signal<SelfInfo | null>(null);
  readonly batteryMilliVolts = signal<number | null>(null);
  readonly firmware = signal<string | null>(null);
  /** How far the radio's clock is ahead of the phone's (seconds), when read. */
  readonly clockOffset = signal<number | null>(null);
  /** Whether its adverts carry its position (newer firmware says). */
  readonly sharesPosition = computed(() => !!this.self()?.reserved?.[1]);
  /** Its frequency, bandwidth, SF and CR. */
  readonly frequency = computed<Frequency | null>(() => {
    const self = this.self();
    return self
      ? { freq: self.radioFreq / 1000, bw: self.radioBw / 1000, sf: self.radioSf, cr: self.radioCr }
      : null;
  });
  /** It was told to restart, so it going away is expected. */
  private restarting = false;
  /** Why the last connect failed, or why the radio went away. */
  readonly problem = signal<string | null>(null);
  readonly hasRemembered = computed(() => this.name() !== null);
  /** How the radio is (or was last) reached. */
  readonly via = signal<Via>(this.remembered()?.via ?? 'bluetooth');

  /** The open connection, while connected. */
  connection: RadioLink | null = null;
  /** The USB port picked since the app opened, to reconnect to it and no other. */
  private usbPort: Port | null = null;

  /** Direct messages as they arrive. */
  readonly messages = new Subject<DirectMessage>();
  /** Channel messages as they arrive. */
  readonly channelMessages = new Subject<ChannelMessage>();
  /**
   * The radio answers requests by kind, not by which request: two "Ok"s
   * can't be told apart. So one request at a time waits for its answer.
   */
  private lock: Promise<unknown> = Promise.resolve();
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
    await this.connect(new CapacitorBleConnection(this.ble, deviceId), {
      via: 'bluetooth',
      deviceId,
    });
  }

  /** Show the computer's list of serial ports, and connect to the radio on the one picked. */
  async pickUsb(): Promise<void> {
    this.problem.set(null);
    if (!this.serial) {
      this.problem.set("USB radios can't be used here: connect over Bluetooth.");
      return;
    }
    let port;
    try {
      port = await this.serial.requestPort({ filters: [] });
    } catch (error) {
      // Closing the list without picking isn't a problem worth showing.
      if (!/no port selected|cancel|abort/i.test(String(error))) {
        this.problem.set(describe(error));
      }
      return;
    }
    this.usbPort = port;
    await this.connect(new UsbConnection(port), { via: 'usb', deviceId: '', usb: port.getInfo() });
  }

  /** Connect to the radio remembered from last time, if there is one. */
  async reconnect(): Promise<void> {
    const remembered = this.remembered();
    if (!remembered) {
      return;
    }
    if (remembered.via !== 'usb') {
      await this.connect(new CapacitorBleConnection(this.ble, remembered.deviceId), {
        via: 'bluetooth',
        deviceId: remembered.deviceId,
      });
      return;
    }
    // The port picked since the app opened; or, of the ports allowed before,
    // the one plugged in with the same maker and model. Not when two are:
    // two radios of one model look the same, and one may be someone else's
    // (a node's, on the same computer).
    const ports = (await this.serial?.getPorts().catch(() => [])) ?? [];
    const same = ports.filter(
      (p) =>
        p.getInfo().usbVendorId === remembered.usb?.usbVendorId &&
        p.getInfo().usbProductId === remembered.usb?.usbProductId,
    );
    const port =
      this.usbPort && ports.includes(this.usbPort)
        ? this.usbPort
        : same.length === 1
          ? same[0]
          : null;
    if (!port) {
      this.problem.set(
        same.length > 1
          ? 'More than one radio like yours is plugged in: pick yours with Pick one on USB.'
          : 'Plug your radio in over USB, or pick it again.',
      );
      return;
    }
    await this.connect(new UsbConnection(port), remembered);
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
    const connection = this.open();
    const contacts = await this.exclusive(() =>
      within(connection.getContacts(), ANSWER_MS, 'its contacts'),
    );
    return contacts
      .map((c) => ({
        publicKey: toHex(c.publicKey),
        name: c.advName,
        type: c.type,
        hops: c.outPathLen < 0 ? null : c.outPathLen,
        lastAdvert: c.lastAdvert,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  /**
   * Advertise the radio, so others (the node) learn it: across the mesh
   * (flood), or only to radios in direct range (zero-hop).
   */
  async advert(kind: 'flood' | 'zero-hop' = 'flood'): Promise<void> {
    await this.request('sending an advert', (c) =>
      kind === 'flood' ? c.sendFloodAdvert() : c.sendZeroHopAdvert(),
    );
  }

  /** Read again what the radio says about itself: name, settings, battery, clock. */
  async refresh(): Promise<void> {
    this.self.set(await this.request('its name', (c) => c.getSelfInfo()));
    const battery = await this.request('its battery', (c) => c.getBatteryVoltage()).catch(
      () => null,
    );
    this.batteryMilliVolts.set(battery?.batteryMilliVolts ?? null);
    const time = await this.request('its clock', (c) => c.getDeviceTime()).catch(() => null);
    this.clockOffset.set(time ? time.epochSecs - Math.round(Date.now() / 1000) : null);
  }

  /** The name others see, after its next advert. */
  async rename(name: string): Promise<void> {
    await this.request('taking the name', (c) => c.setAdvertName(name));
    await this.refresh();
    this.name.set(name);
    const remembered = this.remembered();
    if (remembered) {
      this.remember({ ...remembered, name });
    }
  }

  async setPower(dBm: number): Promise<void> {
    await this.request('taking the TX power', (c) => c.setTxPower(dBm));
    await this.refresh();
  }

  /** The position its adverts carry, when it shares one (degrees). */
  async setPosition(lat: number, lon: number): Promise<void> {
    await this.request('taking the position', (c) =>
      c.setAdvertLatLong(Math.round(lat * 1e6), Math.round(lon * 1e6)),
    );
    await this.refresh();
  }

  /**
   * Whether its adverts carry its position. meshcore.js sends only the first
   * of these settings, so the frame is written here, keeping the others.
   */
  async sharePosition(share: boolean): Promise<void> {
    const self = this.self();
    const frame = new Uint8Array([
      38, // SetOtherParams
      self?.manualAddContacts ?? 0,
      self?.reserved?.[2] ?? 0, // telemetry modes
      share ? 1 : 0,
    ]);
    await this.request('taking the setting', (c) => okOrErr(c, () => c.sendToRadioFrame(frame)));
    await this.refresh();
  }

  /** Set the radio's clock from the phone's. */
  async setClock(): Promise<void> {
    await this.request('setting its clock', (c) => c.syncDeviceTime());
    await this.refresh();
  }

  /**
   * Set its frequency, bandwidth, SF and CR, then restart it so they're
   * surely in use, as the bot does with its own radio. It's gone until it's
   * connected again.
   */
  async setFrequency(f: Frequency): Promise<void> {
    await this.request('taking the settings', (c) =>
      c.setRadioParams(Math.round(f.freq * 1000), Math.round(f.bw * 1000), f.sf, f.cr),
    );
    await this.reboot();
  }

  /** Restart the radio. It answers nothing, and is gone until connected again. */
  async reboot(): Promise<void> {
    const connection = this.open();
    this.restarting = true;
    await this.exclusive(() => connection.sendCommandReboot());
  }

  async removeContact(publicKey: string): Promise<void> {
    await this.request('removing the contact', (c) => c.removeContact(fromHex(publicKey)));
  }

  /** Forget the path to a contact: the next message floods, and finds a new one. */
  async resetPath(publicKey: string): Promise<void> {
    await this.request('resetting the path', (c) => c.resetPath(fromHex(publicKey)));
  }

  /** The radio's channels, in slot order, leaving out empty slots. */
  async channels(): Promise<RadioChannel[]> {
    const connection = this.open();
    const channels = await this.exclusive(() =>
      within(connection.getChannels(), ANSWER_MS, 'its channels'),
    );
    return channels.filter((c) => c.name).map((c) => ({ index: c.channelIdx, name: c.name }));
  }

  /**
   * Post to a channel. Nothing acknowledges a channel message: this resolves
   * once the radio has taken it to send.
   */
  async sendToChannel(index: number, text: string): Promise<void> {
    const connection = this.open();
    await this.exclusive(() =>
      within(connection.sendChannelTextMessage(index, text), ANSWER_MS, 'sending').catch(
        (error) => {
          throw error ?? new Error('the radio refused the message');
        },
      ),
    );
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
        const sent = await this.exclusive(() =>
          within(
            this.whenSent(connection, () =>
              connection.sendCommandSendTxtMsg(0, attempt, timestamp, fromHex(publicKey), text),
            ),
            ANSWER_MS,
            'sending',
          ),
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
  private open(): RadioLink {
    if (!this.connection) {
      throw new Error('no radio connected');
    }
    return this.connection;
  }

  /**
   * Ask the radio something, once the request before has its answer, giving
   * up after ANSWER_MS. Its Err (a rejection with nothing) becomes an error.
   */
  private request<T>(what: string, ask: (connection: RadioLink) => Promise<T>): Promise<T> {
    const connection = this.open();
    return this.exclusive(() =>
      within(ask(connection), ANSWER_MS, what).catch((error) => {
        throw error ?? new Error(`the radio refused ${what}`);
      }),
    );
  }

  /** Run a request once the one before has its answer (or gave up). */
  private exclusive<T>(request: () => Promise<T>): Promise<T> {
    const run = this.lock.then(request, request);
    this.lock = run.catch(() => undefined);
    return run;
  }

  /** Send, and resolve with the radio's Sent answer (or reject on its error). */
  private whenSent(connection: RadioLink, send: () => Promise<void>): Promise<Sent> {
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
  private async drain(connection: RadioLink): Promise<void> {
    if (this.draining) {
      this.drainAgain = true;
      return;
    }
    this.draining = true;
    try {
      do {
        this.drainAgain = false;
        for (;;) {
          const next = await this.exclusive(() =>
            within(connection.syncNextMessage(), ANSWER_MS, 'its messages'),
          ).catch(() => null);
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
          if (next.channelMessage) {
            this.channelMessages.next({
              channel: next.channelMessage.channelIdx,
              text: next.channelMessage.text,
              receivedAt: Date.now(),
            });
          }
        }
      } while (this.drainAgain);
    } finally {
      this.draining = false;
    }
  }

  private async connect(connection: RadioLink, how: Omit<Remembered, 'name'>): Promise<void> {
    if (this.state() === 'connecting') {
      return;
    }
    await this.disconnect();
    this.state.set('connecting');
    this.problem.set(null);
    this.via.set(how.via ?? 'bluetooth');
    try {
      if (how.via !== 'usb') {
        await this.initialize();
      }
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
      this.restarting = false;
      this.batteryMilliVolts.set(battery?.batteryMilliVolts ?? null);
      this.firmware.set(connection.firmware);
      this.state.set('connected');
      this.remember({ ...how, name: self.name });
      // The radio says when messages are waiting; fetch any from meanwhile too.
      connection.on(Constants.PushCodes['MsgWaiting'], () => void this.drain(connection));
      void this.drain(connection);
      connection.on('disconnected', () => {
        if (this.connection === connection) {
          this.connection = null;
          this.state.set('lost');
          this.problem.set(
            this.restarting
              ? 'The radio is restarting. Connect again once it’s back, in about half a minute.'
              : this.via() === 'usb'
                ? 'The radio was unplugged or turned off.'
                : 'The radio went out of range or was turned off.',
          );
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
      return typeof stored?.deviceId === 'string' &&
        typeof stored?.name === 'string' &&
        (stored.via === undefined || stored.via === 'bluetooth' || stored.via === 'usb')
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

/** Send, and resolve on the radio's Ok (or reject on its Err). */
function okOrErr(connection: RadioLink, send: () => Promise<void>): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const onOk = () => {
      connection.off(Constants.ResponseCodes['Err'], onErr);
      resolve();
    };
    const onErr = () => {
      connection.off(Constants.ResponseCodes['Ok'], onOk);
      reject(new Error('the radio refused the setting'));
    };
    connection.once(Constants.ResponseCodes['Ok'], onOk);
    connection.once(Constants.ResponseCodes['Err'], onErr);
    send().catch(reject);
  });
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
    "Couldn't connect to the radio. If the MeshCore app (or another phone or computer) is connected to it, " +
    'disconnect that first: a radio takes one at a time.' +
    (text ? ` (${text})` : '')
  );
}
