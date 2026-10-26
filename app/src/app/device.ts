import { InjectionToken } from '@angular/core';
import { Capacitor } from '@capacitor/core';

/** What the app runs on, for its wording: the phone app, or the desktop app (or a browser). */
export type Device = 'phone' | 'computer';

export const DEVICE = new InjectionToken<Device>('DEVICE', {
  factory: () => (Capacitor.isNativePlatform() ? 'phone' : 'computer'),
});

/** Whether this is the desktop app (Electron), not a browser or the phone app. */
export const DESKTOP = new InjectionToken<boolean>('DESKTOP', {
  factory: () => /\bElectron\//.test(globalThis.navigator?.userAgent ?? ''),
});
