import { TestBed } from '@angular/core/testing';

import { BLE } from './ble';
import { SERIAL } from './serial';
import { QUERY_MS } from './ble-connection';
import { FakeBle, NODE_KEY } from './fake-ble';
import { FakePort, FakeSerial } from './fake-serial';
import {
  ANSWER_MS,
  ChannelMessage,
  describe as describeProblem,
  DirectMessage,
  MIN_ACK_MS,
  Radio,
  REMEMBERED,
  SEND_ATTEMPTS,
} from './radio';

describe('Radio', () => {
  let ble: FakeBle;

  function radio(): Radio {
    TestBed.configureTestingModule({ providers: [{ provide: BLE, useValue: ble }] });
    return TestBed.inject(Radio);
  }

  beforeEach(() => {
    ble = new FakeBle();
    localStorage.clear();
  });

  afterEach(() => vi.useRealTimers());

  it('connects to the radio picked, and reads its name, battery and firmware', async () => {
    const r = radio();
    await r.pick();
    expect(r.state()).toBe('connected');
    expect(r.name()).toBe('Field T1000');
    expect(r.batteryMilliVolts()).toBe(3920);
    expect(r.firmware()).toBe('Seeed Tracker T1000-E, 19 Feb 2025');
    expect(r.connection).not.toBeNull();
    expect(ble.initialized).toBe(1);
  });

  it("sets the radio's clock from the phone's", async () => {
    const before = Math.floor(Date.now() / 1000);
    await radio().pick();
    const frame = ble.written.find((f) => f[0] === 6)!;
    const secs = new DataView(frame.buffer).getUint32(1, true);
    expect(secs).toBeGreaterThanOrEqual(before);
    expect(secs).toBeLessThanOrEqual(before + 5);
  });

  it('remembers the radio and reconnects to it when the app opens', async () => {
    await radio().pick();
    expect(JSON.parse(localStorage.getItem(REMEMBERED)!)).toEqual({
      via: 'bluetooth',
      deviceId: 'AA:BB:CC:DD:EE:FF',
      name: 'Field T1000',
    });

    TestBed.resetTestingModule();
    ble = new FakeBle();
    const again = radio();
    expect(again.name()).toBe('Field T1000');
    expect(again.state()).toBe('none');
    await again.reconnect();
    expect(again.state()).toBe('connected');
    expect(ble.connects).toEqual(['AA:BB:CC:DD:EE:FF']);
  });

  it('does nothing on reconnect with no radio remembered', async () => {
    const r = radio();
    await r.reconnect();
    expect(r.state()).toBe('none');
    expect(ble.connects).toEqual([]);
  });

  it('forgets the radio', async () => {
    const r = radio();
    await r.pick();
    await r.forget();
    expect(r.state()).toBe('none');
    expect(r.name()).toBeNull();
    expect(r.hasRemembered()).toBe(false);
    expect(localStorage.getItem(REMEMBERED)).toBeNull();
    expect(ble.disconnects).toEqual(['AA:BB:CC:DD:EE:FF']);
  });

  it('shows when the radio goes away, and keeps it to reconnect to', async () => {
    const r = radio();
    await r.pick();
    ble.drop();
    await vi.waitFor(() => expect(r.state()).toBe('lost'));
    expect(r.connection).toBeNull();
    expect(r.problem()).toContain('out of range');
    expect(r.hasRemembered()).toBe(true);
  });

  it('says nothing when the user cancels the list, and clears the last problem', async () => {
    const r = radio();
    r.problem.set('The radio went out of range or was turned off.');
    ble.failPick = 'requestDevice cancelled.';
    await r.pick();
    expect(r.state()).toBe('none');
    expect(r.problem()).toBeNull();
  });

  it('explains a radio another app holds', async () => {
    ble.failConnect = 'Connection timeout';
    const r = radio();
    await r.pick();
    expect(r.state()).toBe('none');
    expect(r.problem()).toContain('MeshCore app');
    expect(r.problem()).toContain('Connection timeout');
  });

  it("gives up on a radio that connects but doesn't answer", async () => {
    vi.useFakeTimers();
    try {
      ble.radio.answers = false;
      const r = radio();
      const picked = r.pick();
      await vi.advanceTimersByTimeAsync(QUERY_MS + ANSWER_MS + 1000);
      await picked;
      expect(r.state()).toBe('none');
      expect(r.problem()).toContain("didn't answer (its name)");
      expect(ble.disconnects).toEqual(['AA:BB:CC:DD:EE:FF']);
    } finally {
      vi.useRealTimers();
    }
  });

  it('reconnects to a radio remembered from before USB, over Bluetooth', async () => {
    localStorage.setItem(REMEMBERED, JSON.stringify({ deviceId: 'AA:BB', name: 'Old One' }));
    const r = radio();
    expect(r.via()).toBe('bluetooth');
    await r.reconnect();
    expect(ble.connects).toEqual(['AA:BB']);
  });

  it('has no USB on a phone', async () => {
    const r = radio();
    expect(r.canUseUsb).toBe(false);
    await r.pickUsb();
    expect(r.state()).toBe('none');
    expect(r.problem()).toContain('Bluetooth');
  });

  describe('over USB', () => {
    let serial: FakeSerial;
    let port: FakePort;

    function usbRadio(): Radio {
      TestBed.configureTestingModule({
        providers: [
          { provide: BLE, useValue: ble },
          { provide: SERIAL, useValue: serial },
        ],
      });
      return TestBed.inject(Radio);
    }

    beforeEach(() => {
      port = new FakePort(ble);
      serial = new FakeSerial(port);
    });

    it('connects to the radio on the port picked, at 115200 baud', async () => {
      const r = usbRadio();
      expect(r.canUseUsb).toBe(true);
      port.noise = new TextEncoder().encode('booting...\r\n'); // not a frame: skipped
      await r.pickUsb();
      expect(r.state()).toBe('connected');
      expect(r.via()).toBe('usb');
      expect(r.name()).toBe('Field T1000');
      expect(r.batteryMilliVolts()).toBe(3920);
      expect(r.firmware()).toBe('Seeed Tracker T1000-E, 19 Feb 2025');
      expect(port.baudRate).toBe(115200);
      expect(ble.initialized).toBe(0); // no Bluetooth needed
    });

    it('sends and reads through it like over Bluetooth', async () => {
      const r = usbRadio();
      await r.pickUsb();
      ble.contacts = [{ name: 'Ridge Node', publicKey: NODE_KEY, type: 1 }];
      const contacts = await r.contacts();
      expect(contacts.map((c) => c.name)).toEqual(['Ridge Node']);
    });

    it('remembers the port and reconnects to it without asking', async () => {
      await usbRadio().pickUsb();
      expect(JSON.parse(localStorage.getItem(REMEMBERED)!)).toEqual({
        via: 'usb',
        deviceId: '',
        usb: { usbVendorId: 0x239a, usbProductId: 0x8029 },
        name: 'Field T1000',
      });
      TestBed.resetTestingModule();
      ble = new FakeBle();
      const again = new FakePort(ble);
      serial = new FakeSerial(null);
      serial.allowed = [new FakePort(ble, { usbVendorId: 1, usbProductId: 2 }), again];
      const r = usbRadio();
      await r.reconnect();
      expect(r.state()).toBe('connected');
      expect(again.opened).toBe(1);
      expect(serial.requests).toBe(0);
    });

    it("won't guess between two radios of the same model", async () => {
      await usbRadio().pickUsb();
      TestBed.resetTestingModule();
      ble = new FakeBle();
      serial = new FakeSerial(null);
      serial.allowed = [new FakePort(ble), new FakePort(ble)];
      const r = usbRadio();
      await r.reconnect();
      expect(r.state()).toBe('none');
      expect(serial.allowed.map((p) => p.opened)).toEqual([0, 0]);
      expect(r.problem()).toContain('More than one radio like yours');
    });

    it('reconnects to the very port picked, beside one of the same model', async () => {
      const r = usbRadio();
      await r.pickUsb();
      await r.disconnect();
      serial.allowed = [new FakePort(ble), port];
      await r.reconnect();
      expect(r.state()).toBe('connected');
      expect(port.opened).toBe(2);
      expect(serial.allowed[0].opened).toBe(0);
    });

    it('asks to plug it in when the port remembered is gone', async () => {
      await usbRadio().pickUsb();
      TestBed.resetTestingModule();
      serial = new FakeSerial(null);
      const r = usbRadio();
      await r.reconnect();
      expect(r.state()).toBe('none');
      expect(r.problem()).toBe('Plug your radio in over USB, or pick it again.');
    });

    it('says when the cable is pulled, and closes the port on disconnect', async () => {
      const r = usbRadio();
      await r.pickUsb();
      port.unplug();
      await vi.waitFor(() => expect(r.state()).toBe('lost'));
      expect(r.problem()).toContain('unplugged');
      await r.pickUsb();
      await r.disconnect();
      expect(port.closed).toBeGreaterThan(0);
    });

    it('says nothing when the list is closed without picking', async () => {
      serial.picked = null;
      const r = usbRadio();
      await r.pickUsb();
      expect(r.state()).toBe('none');
      expect(r.problem()).toBeNull();
    });
  });

  it('explains Bluetooth being off and a missing permission', () => {
    expect(describeProblem(new Error('Bluetooth not enabled.'))).toContain('Bluetooth is off');
    expect(describeProblem(new Error('Permission denied.'))).toContain('Nearby devices');
  });

  describe('messages', () => {
    it("lists the radio's contacts by name, with their keys and paths", async () => {
      const r = radio();
      await r.pick();
      const heard = 1_790_000_000;
      expect(await r.contacts()).toEqual([
        { publicKey: 'e0'.repeat(32), name: 'Erin', type: 1, hops: 2, lastAdvert: heard },
        {
          publicKey: 'a1'.repeat(32),
          name: 'Hill Repeater',
          type: 2,
          hops: null,
          lastAdvert: heard,
        },
        { publicKey: NODE_KEY, name: 'Ridge Node', type: 1, hops: 0, lastAdvert: heard },
      ]);
    });

    it('changes its name, power, position and whether adverts share it', async () => {
      const r = radio();
      await r.pick();
      await r.rename('Dana T1000');
      expect(r.name()).toBe('Dana T1000');
      expect(JSON.parse(localStorage.getItem(REMEMBERED)!).name).toBe('Dana T1000');

      await r.setPower(14);
      expect(r.self()?.txPower).toBe(14);
      await expect(r.setPower(30)).rejects.toThrow('the radio refused taking the TX power');

      await r.setPosition(32.448736, -99.733144);
      expect([r.self()?.advLat, r.self()?.advLon]).toEqual([32448736, -99733144]);
      expect(r.sharesPosition()).toBe(false);
      await r.sharePosition(true);
      expect(ble.radio.sharesPosition).toBe(true);
      expect(r.sharesPosition()).toBe(true);
    });

    it('reads its clock against the phone, and sets it', async () => {
      ble.radio.clockAhead = -300;
      const r = radio();
      await r.pick();
      // Connecting sets it; it drifts again.
      ble.radio.clockAhead = -300;
      await r.refresh();
      expect(r.clockOffset()).toBeCloseTo(-300, -1);
      await r.setClock();
      expect(r.clockOffset()).toBeCloseTo(0, -1);
    });

    it('sends a flood or zero-hop advert', async () => {
      const r = radio();
      await r.pick();
      await r.advert();
      await r.advert('zero-hop');
      expect(ble.adverts).toEqual(['flood', 'zero-hop']);
    });

    it('sets its frequency, then restarts it and says so when it goes', async () => {
      const r = radio();
      await r.pick();
      expect(r.frequency()).toEqual({ freq: 910.525, bw: 62.5, sf: 7, cr: 5 });
      await r.setFrequency({ freq: 927.875, bw: 62.5, sf: 7, cr: 5 });
      expect([ble.radio.freq, ble.radio.bw, ble.radio.sf, ble.radio.cr]).toEqual([
        927875, 62500, 7, 5,
      ]);
      expect(ble.reboots).toBe(1);
      await vi.waitFor(() => expect(r.state()).toBe('lost'));
      expect(r.problem()).toContain('The radio is restarting');
      await r.reconnect();
      expect(r.frequency()).toEqual({ freq: 927.875, bw: 62.5, sf: 7, cr: 5 });
    });

    it('removes a contact, and resets the path to one', async () => {
      const r = radio();
      await r.pick();
      await r.resetPath('e0'.repeat(32));
      expect((await r.contacts()).find((c) => c.name === 'Erin')?.hops).toBeNull();
      await r.removeContact('a1'.repeat(32));
      expect((await r.contacts()).map((c) => c.name)).toEqual(['Erin', 'Ridge Node']);
      await expect(r.removeContact('a1'.repeat(32))).rejects.toThrow('refused');
    });

    it('sends a direct message, true once it is acknowledged', async () => {
      const r = radio();
      await r.pick();
      expect(await r.sendText(NODE_KEY, 'whoami')).toBe(true);
      expect(ble.sent).toEqual([['c0c0c0c0c0c0', 'whoami', 0]]);
    });

    it('tries again while it is not acknowledged, then gives up', async () => {
      const r = radio();
      await r.pick();
      // The fetch of waiting messages on connect finishes first.
      await new Promise((resolve) => setTimeout(resolve, 20));
      vi.useFakeTimers();
      try {
        ble.ackFrom = 1;
        const attempts: number[] = [];
        const again = r.sendText(NODE_KEY, 'whoami', (n) => attempts.push(n));
        await vi.advanceTimersByTimeAsync(MIN_ACK_MS + 1000);
        expect(await again).toBe(true);
        expect(attempts).toEqual([1, 2]);

        ble.ackFrom = null;
        const never = r.sendText(NODE_KEY, 'whoami');
        await vi.advanceTimersByTimeAsync(MIN_ACK_MS * SEND_ATTEMPTS + 1000);
        expect(await never).toBe(false);
        expect(ble.sent.slice(2).map(([, , attempt]) => attempt)).toEqual([0, 1, 2]);
      } finally {
        vi.useRealTimers();
      }
    });

    it('fetches direct messages when the radio says they are waiting', async () => {
      const r = radio();
      await r.pick();
      const heard: DirectMessage[] = [];
      r.messages.subscribe((m) => heard.push(m));
      ble.deliver('e0'.repeat(32), 'hello');
      ble.deliver(NODE_KEY, 'inbox: new message from Erin; send inbox to read');
      await vi.waitFor(() =>
        expect(heard.map((m) => [m.from, m.text])).toEqual([
          ['e0e0e0e0e0e0', 'hello'],
          ['c0c0c0c0c0c0', 'inbox: new message from Erin; send inbox to read'],
        ]),
      );
    });

    it('sends an advert', async () => {
      const r = radio();
      await r.pick();
      await r.advert();
      expect(ble.commands()).toContain(7);
    });

    it("reads the radio's channels, leaving out empty slots", async () => {
      const r = radio();
      await r.pick();
      expect(await r.channels()).toEqual([
        { index: 0, name: 'Public' },
        { index: 1, name: '#contingency-wx' },
        { index: 3, name: '#contingency-comm' },
      ]);
    });

    it('posts to a channel, and fetches what is heard on one', async () => {
      const r = radio();
      await r.pick();
      await r.sendToChannel(3, 'net at 7');
      expect(ble.channelSent).toEqual([[3, 'net at 7']]);

      const heard: ChannelMessage[] = [];
      r.channelMessages.subscribe((m) => heard.push(m));
      ble.hear(1, 'Ridge Node', 'Flash Flood Warning: Taylor');
      await vi.waitFor(() =>
        expect(heard.map((m) => [m.channel, m.text])).toEqual([
          [1, 'Ridge Node: Flash Flood Warning: Taylor'],
        ]),
      );
    });

    it('waits for one answer before asking the next', async () => {
      const r = radio();
      await r.pick();
      const [contacts, channels, delivered] = await Promise.all([
        r.contacts(),
        r.channels(),
        r.sendText(NODE_KEY, 'whoami'),
      ]);
      expect(contacts.map((c) => c.name)).toEqual(['Erin', 'Hill Repeater', 'Ridge Node']);
      expect(channels).toHaveLength(3);
      expect(delivered).toBe(true);
    });

    it('says when there is no radio to send through', async () => {
      await expect(radio().sendText(NODE_KEY, 'whoami')).rejects.toThrow('no radio connected');
    });
  });
});
