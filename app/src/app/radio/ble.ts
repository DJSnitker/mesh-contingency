import { InjectionToken } from '@angular/core';
import { BleClient } from '@capacitor-community/bluetooth-le';
import Constants from '@liamcottle/meshcore.js/src/constants.js';

/** The Bluetooth calls the app makes (the plugin's BleClient), so tests can fake them. */
export type Ble = Pick<
  typeof BleClient,
  'initialize' | 'requestDevice' | 'connect' | 'disconnect' | 'startNotifications' | 'write'
>;

export const BLE = new InjectionToken<Ble>('BLE', { factory: () => BleClient });

/** MeshCore's companion radios speak over the Nordic UART service. */
export const SERVICE = Constants.Ble.ServiceUuid.toLowerCase();
/** The app writes to RX, where the radio reads. */
export const RX = Constants.Ble.CharacteristicUuidRx.toLowerCase();
/** The radio notifies on TX. */
export const TX = Constants.Ble.CharacteristicUuidTx.toLowerCase();
