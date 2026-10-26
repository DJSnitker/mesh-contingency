import { FakeBle } from './fake-ble';
import { Port, PortInfo, Serial } from './serial';

/**
 * A USB serial port with a MeshCore companion radio on it, for tests: the
 * radio is a FakeBle's, so it answers the same frames the same way; this
 * adds and strips the serial framing ("<" or ">", then a 2-byte length).
 */
export class FakePort implements Port {
  readonly readable: ReadableStream<Uint8Array>;
  readonly writable: WritableStream<Uint8Array>;
  opened = 0;
  closed = 0;
  baudRate: number | null = null;
  private push: ((bytes: Uint8Array) => void) | null = null;
  private end: (() => void) | null = null;
  private readonly listeners = new Set<() => void>();
  /** Bytes the radio sends that aren't a frame (its boot messages, say), before the first answer. */
  noise = new Uint8Array();

  constructor(
    readonly ble: FakeBle,
    readonly info: PortInfo = { usbVendorId: 0x239a, usbProductId: 0x8029 },
  ) {
    this.readable = new ReadableStream<Uint8Array>({
      start: (controller) => {
        this.push = (bytes) => controller.enqueue(bytes);
        this.end = () => controller.close();
      },
    });
    this.writable = new WritableStream<Uint8Array>({
      write: (bytes) => {
        // "<", the length, the frame: hand the frame to the radio.
        const length = bytes[1] | (bytes[2] << 8);
        void this.ble.write('usb', '', '', new DataView(bytes.slice(3, 3 + length).buffer));
      },
    });
  }

  async open(options: { baudRate: number }): Promise<void> {
    this.opened++;
    this.baudRate = options.baudRate;
    await this.ble.connect('usb');
    await this.ble.startNotifications('usb', '', '', (value) => {
      const frame = new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
      // Split across two reads, as a serial port may deliver it.
      const framed = new Uint8Array([
        ...this.noise,
        0x3e,
        frame.length & 0xff,
        frame.length >> 8,
        ...frame,
      ]);
      this.noise = new Uint8Array();
      const half = Math.ceil(framed.length / 2);
      this.push?.(framed.slice(0, half));
      this.push?.(framed.slice(half));
    });
  }

  async close(): Promise<void> {
    this.closed++;
    await this.ble.disconnect('usb');
  }

  getInfo(): PortInfo {
    return this.info;
  }

  addEventListener(_type: 'disconnect', listener: () => void): void {
    this.listeners.add(listener);
  }

  removeEventListener(_type: 'disconnect', listener: () => void): void {
    this.listeners.delete(listener);
  }

  /** Pull the cable. */
  unplug(): void {
    this.push = null;
    this.end?.();
    this.end = null;
    for (const listener of this.listeners) {
      listener();
    }
  }
}

/** Web Serial, for tests: the port the user picks, and the ones allowed before. */
export class FakeSerial implements Serial {
  /** What the list returns; null as if closed without picking. */
  picked: FakePort | null;
  allowed: FakePort[] = [];
  requests = 0;

  constructor(port: FakePort | null) {
    this.picked = port;
  }

  async requestPort(): Promise<Port> {
    this.requests++;
    if (!this.picked) {
      throw new DOMException('No port selected by the user.', 'NotFoundError');
    }
    this.allowed = [...new Set([...this.allowed, this.picked])];
    return this.picked;
  }

  async getPorts(): Promise<Port[]> {
    return this.allowed;
  }
}
