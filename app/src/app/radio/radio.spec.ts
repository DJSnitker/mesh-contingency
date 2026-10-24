import { TestBed } from '@angular/core/testing';

import { BLE } from './ble';
import { QUERY_MS } from './ble-connection';
import { FakeBle } from './fake-ble';
import { ANSWER_MS, describe as describeProblem, Radio, REMEMBERED } from './radio';

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
      await vi.advanceTimersByTimeAsync(QUERY_MS + ANSWER_MS);
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
});
