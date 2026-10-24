// The parts of meshcore.js (@liamcottle/meshcore.js, plain JavaScript) the
// app uses, imported file by file: its index also loads Node.js-only
// connections (serial, TCP) that don't bundle for a phone.

declare module '@liamcottle/meshcore.js/src/constants.js' {
  const Constants: {
    SupportedCompanionProtocolVersion: number;
    Ble: { ServiceUuid: string; CharacteristicUuidRx: string; CharacteristicUuidTx: string };
    ResponseCodes: Record<string, number>;
    PushCodes: Record<string, number>;
  };
  export default Constants;
}

declare module '@liamcottle/meshcore.js/src/connection/connection.js' {
  /** The radio's own identity and settings, as it reports them. */
  export interface SelfInfo {
    type: number;
    txPower: number;
    maxTxPower: number;
    publicKey: Uint8Array;
    advLat: number;
    advLon: number;
    manualAddContacts: number;
    radioFreq: number;
    radioBw: number;
    radioSf: number;
    radioCr: number;
    name: string;
  }

  /** The radio's firmware, from a device query. */
  export interface DeviceInfo {
    firmwareVer: number;
    firmware_build_date: string;
    manufacturerModel: string;
  }

  /**
   * A companion radio, over some transport: subclasses pass frames to the
   * radio (sendToRadioFrame) and hand back what it sends (onFrameReceived).
   * Its requests resolve when the radio answers, and never time out.
   */
  export default class Connection {
    on(event: string | number, callback: (...data: any[]) => void): void;
    off(event: string | number, callback: (...data: any[]) => void): void;
    once(event: string | number, callback: (...data: any[]) => void): void;
    emit(event: string | number, ...data: unknown[]): void;

    onConnected(): Promise<void>;
    onDisconnected(): void;
    onFrameReceived(frame: Uint8Array): void;
    close(): Promise<void>;
    sendToRadioFrame(frame: Uint8Array): Promise<void>;

    deviceQuery(appTargetVer: number): Promise<DeviceInfo>;
    getSelfInfo(timeoutMillis?: number | null): Promise<SelfInfo>;
    getBatteryVoltage(): Promise<{ batteryMilliVolts: number }>;
    syncDeviceTime(): Promise<void>;
  }
}
