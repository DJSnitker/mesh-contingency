import type { BleDevice } from '@capacitor-community/bluetooth-le';

import { Ble } from './ble';

/** The radio a FakeBle plays, and how it behaves. */
export interface FakeRadio {
  name: string;
  batteryMilliVolts: number;
  /** Answers the device query (older firmware may not). */
  answersQuery: boolean;
  /** Answers anything at all once connected. */
  answers: boolean;
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
  };
  /** Why the next request or connect fails, if it should. */
  failPick: string | null = null;
  failConnect: string | null = null;

  initialized = 0;
  connects: string[] = [];
  disconnects: string[] = [];
  /** Each frame written to the radio, as bytes. */
  written: Uint8Array[] = [];

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
    const answer = this.answer(frame[0]);
    if (answer && this.radio.answers) {
      setTimeout(() => this.notify?.(new DataView(answer.buffer)), 0);
    }
  }

  /** The radio goes out of range. */
  drop(): void {
    this.onDisconnect?.('AA:BB:CC:DD:EE:FF');
  }

  /** The command codes the app has written, in order. */
  commands(): number[] {
    return this.written.map((frame) => frame[0]);
  }

  private answer(command: number): Uint8Array | null {
    switch (command) {
      case 1: // AppStart -> SelfInfo
        return selfInfo(this.radio.name);
      case 6: // SetDeviceTime -> Ok
        return new Uint8Array([0]);
      case 20: // GetBatteryVoltage -> BatteryVoltage
        return new Uint8Array([
          12,
          this.radio.batteryMilliVolts & 0xff,
          this.radio.batteryMilliVolts >> 8,
        ]);
      case 22: // DeviceQuery -> DeviceInfo
        return this.radio.answersQuery ? deviceInfo() : null;
      default:
        return null;
    }
  }
}

function selfInfo(name: string): Uint8Array {
  const frame = new Uint8Array(58 + name.length);
  const view = new DataView(frame.buffer);
  frame[0] = 5; // SelfInfo
  frame[1] = 1; // type: companion
  frame[2] = 22; // txPower
  frame[3] = 22; // maxTxPower
  frame.fill(0xab, 4, 36); // publicKey
  view.setUint32(48, 910525, true); // radioFreq, kHz
  view.setUint32(52, 62500, true); // radioBw, Hz
  frame[56] = 7; // radioSf
  frame[57] = 5; // radioCr
  frame.set(new TextEncoder().encode(name), 58);
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
