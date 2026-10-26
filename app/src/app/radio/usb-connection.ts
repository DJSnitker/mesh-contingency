import SerialConnection from '@liamcottle/meshcore.js/src/connection/serial_connection.js';

import { askFirmware } from './ble-connection';
import { BAUD, Port } from './serial';

/**
 * A companion radio on a USB cable, over Web Serial: meshcore.js's
 * SerialConnection frames what goes each way; this reads and writes the
 * port, and says when the cable is pulled.
 */
export class UsbConnection extends SerialConnection {
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private closed = false;
  /** The firmware's build date and model, if the radio answered the device query. */
  firmware: string | null = null;
  private readonly unplugged = () => this.gone();

  constructor(readonly port: Port) {
    super();
  }

  /** Open the port, listen to the radio, and say which protocol version the app speaks. */
  async open(): Promise<void> {
    await this.port.open({ baudRate: BAUD });
    this.port.addEventListener('disconnect', this.unplugged);
    if (!this.port.readable || !this.port.writable) {
      throw new Error("the radio's USB port can't be read");
    }
    this.reader = this.port.readable.getReader();
    void this.read(this.reader);
    this.firmware = await askFirmware(this);
    this.emit('connected');
  }

  override async close(): Promise<void> {
    this.closed = true;
    this.port.removeEventListener('disconnect', this.unplugged);
    await this.reader?.cancel().catch(() => undefined);
    this.reader?.releaseLock();
    this.reader = null;
    await this.port.close().catch(() => undefined);
  }

  override async write(bytes: Uint8Array): Promise<void> {
    const writer = this.port.writable!.getWriter();
    try {
      await writer.write(new Uint8Array(bytes));
    } finally {
      writer.releaseLock();
    }
  }

  /** Pass what the radio sends to the framing, until the port closes or goes. */
  private async read(reader: ReadableStreamDefaultReader<Uint8Array>): Promise<void> {
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        await this.onDataReceived(value);
      }
    } catch {
      // The cable was pulled, or the port closed under the read.
    }
    this.gone();
  }

  private gone(): void {
    if (!this.closed) {
      this.closed = true;
      this.onDisconnected();
    }
  }
}
