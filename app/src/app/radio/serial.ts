import { InjectionToken } from '@angular/core';

/** What a USB serial port says about itself (Web Serial's SerialPortInfo). */
export interface PortInfo {
  usbVendorId?: number;
  usbProductId?: number;
}

/** The parts of Web Serial's SerialPort the app uses. */
export interface Port {
  readonly readable: ReadableStream<Uint8Array> | null;
  readonly writable: WritableStream<Uint8Array> | null;
  open(options: { baudRate: number }): Promise<void>;
  close(): Promise<void>;
  getInfo(): PortInfo;
  addEventListener(type: 'disconnect', listener: () => void): void;
  removeEventListener(type: 'disconnect', listener: () => void): void;
}

/** Web Serial (navigator.serial), so tests can fake it. */
export interface Serial {
  /** Shows the system's list of serial ports; rejects if none is picked. */
  requestPort(options?: { filters: PortInfo[] }): Promise<Port>;
  /** The ports this app was allowed before, to reconnect without asking. */
  getPorts(): Promise<Port[]>;
}

/**
 * Web Serial, where there is one: in Chromium on a computer (the desktop
 * app, Chrome or Edge), not in Android's web view. null means no USB.
 */
export const SERIAL = new InjectionToken<Serial | null>('SERIAL', {
  factory: () => (globalThis.navigator as { serial?: Serial } | undefined)?.serial ?? null,
});

/** MeshCore's companion firmware talks over USB at this speed. */
export const BAUD = 115200;
