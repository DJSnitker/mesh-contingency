import type { BleDevice } from '@capacitor-community/bluetooth-le';

import { Ble } from './ble';
import { fromHex, toHex } from './hex';

/** The node in the fake radio's contacts. */
export const NODE_KEY = 'c0'.repeat(32);

/** A contact the fake radio has. */
export interface FakeContact {
  name: string;
  publicKey: string;
  type: number;
  /** Hops on its known path; -1 for none (flood). */
  hops?: number;
}

/** The radio a FakeBle plays, and how it behaves. */
export interface FakeRadio {
  name: string;
  batteryMilliVolts: number;
  /** Answers the device query (older firmware may not). */
  answersQuery: boolean;
  /** Answers anything at all once connected. */
  answers: boolean;
  txPower: number;
  maxTxPower: number;
  /** Millionths of a degree. */
  lat: number;
  lon: number;
  sharesPosition: boolean;
  /** kHz and Hz, as the radio holds them. */
  freq: number;
  bw: number;
  sf: number;
  cr: number;
  /** How far its clock is ahead of the phone's (seconds). */
  clockAhead: number;
}

/**
 * The Bluetooth plugin, for tests, with a MeshCore companion radio on the
 * other end that answers the frames the app writes, as a real one would.
 */
export class FakeBle implements Ble {
  radio: FakeRadio = {
    name: 'Field T1000',
    batteryMilliVolts: 3920,
    answersQuery: true,
    answers: true,
    txPower: 22,
    maxTxPower: 22,
    lat: 0,
    lon: 0,
    sharesPosition: false,
    freq: 910525,
    bw: 62500,
    sf: 7,
    cr: 5,
    clockAhead: 0,
  };
  /** Adverts sent: "flood" or "zero-hop". */
  adverts: string[] = [];
  /** Times it was told to restart. */
  reboots = 0;
  /** Why the next request or connect fails, if it should. */
  failPick: string | null = null;
  failConnect: string | null = null;

  initialized = 0;
  connects: string[] = [];
  disconnects: string[] = [];
  /** Each frame written to the radio, as bytes. */
  written: Uint8Array[] = [];

  contacts: FakeContact[] = [
    { name: 'Ridge Node', publicKey: NODE_KEY, type: 1 },
    { name: 'Hill Repeater', publicKey: 'a1'.repeat(32), type: 2, hops: -1 },
    { name: 'Erin', publicKey: 'e0'.repeat(32), type: 1, hops: 2 },
  ];
  /** The radio's channel slots ("" for an empty one). */
  channels: string[] = ['Public', '#contingency-wx', '', '#contingency-comm'];
  /** Channel messages the radio sent: [slot, text]. */
  channelSent: [number, string][] = [];
  /** Direct messages the radio sent: [recipient key prefix, text, attempt]. */
  sent: [string, string, number][] = [];
  /** The try (from 0) the recipient first acknowledges; null for never. */
  ackFrom: number | null = 0;
  /** What the node answers a direct message, as its messages. */
  node: (text: string) => string[] = (text) =>
    text === 'whoami' ? ['Field T1000 (abababababab); no passphrase; no messages'] : [];
  /** Messages waiting on the radio, as frames. */
  private waiting: Uint8Array[] = [];

  private onDisconnect: ((deviceId: string) => void) | undefined;
  private notify: ((value: DataView) => void) | undefined;

  async initialize(): Promise<void> {
    this.initialized++;
  }

  async requestDevice(): Promise<BleDevice> {
    if (this.failPick) {
      throw new Error(this.failPick);
    }
    return { deviceId: 'AA:BB:CC:DD:EE:FF', name: this.radio.name };
  }

  async connect(deviceId: string, onDisconnect?: (deviceId: string) => void): Promise<void> {
    if (this.failConnect) {
      throw new Error(this.failConnect);
    }
    this.connects.push(deviceId);
    this.onDisconnect = onDisconnect;
  }

  async disconnect(deviceId: string): Promise<void> {
    this.disconnects.push(deviceId);
    this.notify = undefined;
  }

  async startNotifications(
    _deviceId: string,
    _service: string,
    _characteristic: string,
    callback: (value: DataView) => void,
  ): Promise<void> {
    this.notify = callback;
  }

  async write(
    _deviceId: string,
    _service: string,
    _characteristic: string,
    value: DataView,
  ): Promise<void> {
    const frame = new Uint8Array(
      value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength),
    );
    this.written.push(frame);
    if (this.radio.answers) {
      for (const answer of this.answer(frame)) {
        setTimeout(() => this.notify?.(new DataView(answer.buffer)), 0);
      }
    }
  }

  /** A direct message reaches the radio, from the contact with this key. */
  deliver(fromKey: string, text: string): void {
    this.waiting.push(contactMessage(fromKey, text));
    setTimeout(() => this.notify?.(new DataView(new Uint8Array([0x83]).buffer)), 0); // MsgWaiting
  }

  /** A message is heard on a channel slot, from someone named `from`. */
  hear(channel: number, from: string, text: string): void {
    this.waiting.push(channelMessage(channel, `${from}: ${text}`));
    setTimeout(() => this.notify?.(new DataView(new Uint8Array([0x83]).buffer)), 0); // MsgWaiting
  }

  /** The radio goes out of range. */
  drop(): void {
    this.onDisconnect?.('AA:BB:CC:DD:EE:FF');
  }

  /** The command codes the app has written, in order. */
  commands(): number[] {
    return this.written.map((frame) => frame[0]);
  }

  private answer(frame: Uint8Array): Uint8Array[] {
    switch (frame[0]) {
      case 1: // AppStart -> SelfInfo
        return [selfInfo(this.radio)];
      case 2: // SendTxtMsg -> Sent, then maybe the acknowledgement and the node's answer
        return this.sendText(frame);
      case 3: // SendChannelTxtMsg -> Ok
        this.channelSent.push([frame[2], new TextDecoder().decode(frame.slice(7))]);
        return [new Uint8Array([0])];
      case 4: // GetContacts -> ContactsStart, Contact..., EndOfContacts
        return [
          new Uint8Array([2, this.contacts.length, 0, 0, 0]),
          ...this.contacts.map(contact),
          new Uint8Array([4, 0, 0, 0, 0]),
        ];
      case 5: {
        // GetDeviceTime -> CurrTime
        const time = new Uint8Array(5);
        time[0] = 9;
        const now = Math.floor(Date.now() / 1000) + this.radio.clockAhead;
        new DataView(time.buffer).setUint32(1, now, true);
        return [time];
      }
      case 6: // SetDeviceTime -> Ok
        this.radio.clockAhead = 0;
        return [OK];
      case 7: // SendSelfAdvert -> Ok
        this.adverts.push(frame[1] === 1 ? 'flood' : 'zero-hop');
        return [OK];
      case 8: // SetAdvertName -> Ok
        this.radio.name = new TextDecoder().decode(frame.slice(1));
        return [OK];
      case 11: {
        // SetRadioParams -> Ok
        const view = new DataView(frame.buffer, frame.byteOffset);
        Object.assign(this.radio, {
          freq: view.getUint32(1, true),
          bw: view.getUint32(5, true),
          sf: frame[9],
          cr: frame[10],
        });
        return [OK];
      }
      case 12: // SetTxPower -> Ok, or Err above its maximum
        if (frame[1] > this.radio.maxTxPower) {
          return [new Uint8Array([1])];
        }
        this.radio.txPower = frame[1];
        return [OK];
      case 13: // ResetPath -> Ok
      case 15: {
        // RemoveContact -> Ok
        const key = toHex(frame.slice(1, 33));
        const found = this.contacts.find((c) => c.publicKey === key);
        if (!found) {
          return [new Uint8Array([1])];
        }
        if (frame[0] === 13) {
          found.hops = -1;
        } else {
          this.contacts = this.contacts.filter((c) => c !== found);
        }
        return [OK];
      }
      case 14: {
        // SetAdvertLatLon -> Ok
        const view = new DataView(frame.buffer, frame.byteOffset);
        this.radio.lat = view.getInt32(1, true);
        this.radio.lon = view.getInt32(5, true);
        return [OK];
      }
      case 19: // Reboot: answers nothing, and goes away
        this.reboots++;
        setTimeout(() => this.drop(), 0);
        return [];
      case 38: // SetOtherParams -> Ok
        if (frame.length >= 4) {
          this.radio.sharesPosition = frame[3] === 1;
        }
        return [OK];
      case 10: // SyncNextMessage -> a message, or NoMoreMessages
        return [this.waiting.shift() ?? new Uint8Array([10])];
      case 20: // GetBatteryVoltage -> BatteryVoltage
        return [
          new Uint8Array([
            12,
            this.radio.batteryMilliVolts & 0xff,
            this.radio.batteryMilliVolts >> 8,
          ]),
        ];
      case 22: // DeviceQuery -> DeviceInfo
        return this.radio.answersQuery ? [deviceInfo()] : [];
      case 31: // GetChannel -> ChannelInfo, or Err past the last slot
        return frame[1] < this.channels.length
          ? [channelInfo(frame[1], this.channels[frame[1]])]
          : [new Uint8Array([1])];
      default:
        return [];
    }
  }

  private sendText(frame: Uint8Array): Uint8Array[] {
    const attempt = frame[2];
    const prefix = toHex(frame.slice(7, 13));
    const text = new TextDecoder().decode(frame.slice(13));
    this.sent.push([prefix, text, attempt]);
    const ackCode = 0x1000 + attempt;
    const sent = new Uint8Array(10);
    sent[0] = 6; // Sent
    new DataView(sent.buffer).setUint32(2, ackCode, true);
    new DataView(sent.buffer).setUint32(6, 1000, true); // estTimeout, ms
    const answers = [sent];
    if (this.ackFrom === null || attempt < this.ackFrom) {
      return answers;
    }
    const ack = new Uint8Array(9);
    ack[0] = 0x82; // SendConfirmed
    new DataView(ack.buffer).setUint32(1, ackCode, true);
    answers.push(ack);
    const recipient = this.contacts.find((c) => c.publicKey.startsWith(prefix));
    if (recipient?.publicKey === NODE_KEY && attempt === this.ackFrom) {
      for (const reply of this.node(text)) {
        this.waiting.push(contactMessage(NODE_KEY, reply));
      }
      if (this.waiting.length) {
        answers.push(new Uint8Array([0x83])); // MsgWaiting
      }
    }
    return answers;
  }
}

function contact(c: FakeContact): Uint8Array {
  const frame = new Uint8Array(148);
  frame[0] = 3; // Contact
  frame.set(fromHex(c.publicKey), 1);
  frame[33] = c.type;
  frame[35] = (c.hops ?? 0) & 0xff; // outPathLen
  new DataView(frame.buffer).setUint32(132, 1_790_000_000, true); // lastAdvert
  frame.set(new TextEncoder().encode(c.name), 100); // advName, 32 bytes
  return frame;
}

function contactMessage(fromKey: string, text: string): Uint8Array {
  const body = new TextEncoder().encode(text);
  const frame = new Uint8Array(13 + body.length);
  frame[0] = 7; // ContactMsgRecv
  frame.set(fromHex(fromKey).slice(0, 6), 1);
  frame.set(body, 13);
  return frame;
}

function channelMessage(channel: number, text: string): Uint8Array {
  const body = new TextEncoder().encode(text);
  const frame = new Uint8Array(8 + body.length);
  frame[0] = 8; // ChannelMsgRecv
  frame[1] = channel;
  frame[2] = 1; // pathLen
  frame.set(body, 8);
  return frame;
}

function channelInfo(index: number, name: string): Uint8Array {
  const frame = new Uint8Array(2 + 32 + 16);
  frame[0] = 18; // ChannelInfo
  frame[1] = index;
  frame.set(new TextEncoder().encode(name), 2); // name, 32 bytes
  return frame;
}

/** The radio's answer to a setting it took. */
const OK = new Uint8Array([0]);

function selfInfo(radio: FakeRadio): Uint8Array {
  const name = new TextEncoder().encode(radio.name);
  const frame = new Uint8Array(58 + name.length);
  const view = new DataView(frame.buffer);
  frame[0] = 5; // SelfInfo
  frame[1] = 1; // type: companion
  frame[2] = radio.txPower;
  frame[3] = radio.maxTxPower;
  frame.fill(0xab, 4, 36); // publicKey
  view.setInt32(36, radio.lat, true);
  view.setInt32(40, radio.lon, true);
  frame[45] = radio.sharesPosition ? 1 : 0; // advert location policy
  view.setUint32(48, radio.freq, true); // kHz
  view.setUint32(52, radio.bw, true); // Hz
  frame[56] = radio.sf;
  frame[57] = radio.cr;
  frame.set(name, 58);
  return frame;
}

function deviceInfo(): Uint8Array {
  const model = new TextEncoder().encode('Seeed Tracker T1000-E');
  const frame = new Uint8Array(20 + model.length);
  frame[0] = 13; // DeviceInfo
  frame[1] = 8; // firmwareVer
  frame.set(new TextEncoder().encode('19 Feb 2025'), 8);
  frame.set(model, 20);
  return frame;
}
