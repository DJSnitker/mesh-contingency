import Connection from '@liamcottle/meshcore.js/src/connection/connection.js';
import Constants from '@liamcottle/meshcore.js/src/constants.js';

import { Ble, RX, SERVICE, TX } from './ble';

/** How long the radio has to answer the first question it's asked (ms). */
export const QUERY_MS = 5000;

/** Resolve with the promise's value, or reject once `ms` have passed. */
export function within<T>(promise: Promise<T>, ms: number, what: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`the radio didn't answer (${what})`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

/**
 * A companion radio over Bluetooth (the Capacitor plugin), the way
 * meshcore.js's WebBleConnection does it in a browser: frames go to RX and
 * come back as TX notifications. Writes wait their turn, since the radio
 * takes one GATT write at a time.
 */
export class CapacitorBleConnection extends Connection {
  private queue: Promise<unknown> = Promise.resolve();
  private closed = false;
  /** The firmware's build date and model, if the radio answered the device query. */
  firmware: string | null = null;

  constructor(
    private readonly ble: Ble,
    readonly deviceId: string,
  ) {
    super();
  }

  /** Connect, listen to the radio, and say which protocol version the app speaks. */
  async open(): Promise<void> {
    await this.ble.connect(this.deviceId, () => {
      if (!this.closed) {
        this.onDisconnected();
      }
    });
    await this.ble.startNotifications(this.deviceId, SERVICE, TX, (value) => {
      this.onFrameReceived(new Uint8Array(value.buffer, value.byteOffset, value.byteLength));
    });
    // What Connection.onConnected does, but not waiting forever on a radio
    // that doesn't answer; older firmware may not, and works anyway.
    const info = await within(
      this.deviceQuery(Constants.SupportedCompanionProtocolVersion),
      QUERY_MS,
      'device query',
    ).catch(() => null);
    if (info) {
      this.firmware =
        [info.manufacturerModel, info.firmware_build_date].filter(Boolean).join(', ') || null;
    }
    this.emit('connected');
  }

  override async close(): Promise<void> {
    this.closed = true;
    await this.ble.disconnect(this.deviceId).catch(() => undefined);
  }

  override sendToRadioFrame(frame: Uint8Array): Promise<void> {
    this.emit('tx', frame);
    const view = new DataView(frame.buffer, frame.byteOffset, frame.byteLength);
    const written = this.queue.then(() => this.ble.write(this.deviceId, SERVICE, RX, view));
    // One failed write doesn't hold up the next.
    this.queue = written.catch(() => undefined);
    return written;
  }
}
