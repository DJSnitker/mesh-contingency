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

  /** One of the radio's contacts. */
  export interface Contact {
    publicKey: Uint8Array;
    /** 1 a companion (chat), 2 a repeater, 3 a room server, 4 a sensor. */
    type: number;
    flags: number;
    outPathLen: number;
    advName: string;
    lastAdvert: number;
  }

  /** A direct message the radio received. */
  export interface ContactMessage {
    /** The first 6 bytes of the sender's key. */
    pubKeyPrefix: Uint8Array;
    pathLen: number;
    txtType: number;
    senderTimestamp: number;
    text: string;
  }

  /** A message heard on one of the radio's channels. */
  export interface ChannelMessage {
    channelIdx: number;
    /** 0xff when sent direct, else the hops it came over. */
    pathLen: number;
    txtType: number;
    senderTimestamp: number;
    /** "<sender's name>: <text>". */
    text: string;
  }

  /** One of the radio's channel slots ("" for an empty one). */
  export interface ChannelInfo {
    channelIdx: number;
    name: string;
    secret: Uint8Array;
  }

  /** The radio's answer to sending a direct message. */
  export interface Sent {
    result: number;
    /** The code the recipient's acknowledgement will carry. */
    expectedAckCrc: number;
    /** How long the radio expects the acknowledgement to take (ms). */
    estTimeout: number;
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
    getContacts(): Promise<Contact[]>;
    sendFloodAdvert(): Promise<void>;
    /** The channel slots, until the radio says there are no more. */
    getChannels(): Promise<ChannelInfo[]>;
    /** Resolves on the radio's Ok; rejects (with nothing) on its Err. */
    sendChannelTextMessage(channelIdx: number, text: string): Promise<void>;
    /** The next waiting message, or null when there are none. */
    syncNextMessage(): Promise<{
      contactMessage?: ContactMessage;
      channelMessage?: ChannelMessage;
    } | null>;
    sendCommandSendTxtMsg(
      txtType: number,
      attempt: number,
      senderTimestamp: number,
      pubKeyPrefix: Uint8Array,
      text: string,
    ): Promise<void>;
  }
}
