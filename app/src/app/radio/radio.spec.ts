import { TestBed } from '@angular/core/testing';

import { BLE } from './ble';
import { QUERY_MS } from './ble-connection';
import { FakeBle, NODE_KEY } from './fake-ble';
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

  it('explains Bluetooth being off and a missing permission', () => {
    expect(describeProblem(new Error('Bluetooth not enabled.'))).toContain('Bluetooth is off');
    expect(describeProblem(new Error('Permission denied.'))).toContain('Nearby devices');
  });

  describe('messages', () => {
    it("lists the radio's contacts by name, with their keys", async () => {
      const r = radio();
      await r.pick();
      expect(await r.contacts()).toEqual([
        { publicKey: 'e0'.repeat(32), name: 'Erin', type: 1 },
        { publicKey: 'a1'.repeat(32), name: 'Hill Repeater', type: 2 },
        { publicKey: NODE_KEY, name: 'Ridge Node', type: 1 },
      ]);
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
