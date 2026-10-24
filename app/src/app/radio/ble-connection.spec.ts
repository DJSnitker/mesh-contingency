import { CapacitorBleConnection, QUERY_MS, within } from './ble-connection';
import { RX, SERVICE, TX } from './ble';
import { FakeBle } from './fake-ble';

describe('CapacitorBleConnection', () => {
  it('uses the Nordic UART service MeshCore radios offer', () => {
    expect(SERVICE).toBe('6e400001-b5a3-f393-e0a9-e50e24dcca9e');
    expect(RX).toBe('6e400002-b5a3-f393-e0a9-e50e24dcca9e');
    expect(TX).toBe('6e400003-b5a3-f393-e0a9-e50e24dcca9e');
  });

  it('connects, asks the device query, and reads what the radio says', async () => {
    const ble = new FakeBle();
    const connection = new CapacitorBleConnection(ble, 'radio-1');
    await connection.open();
    expect(ble.connects).toEqual(['radio-1']);
    expect(ble.commands()).toEqual([22]);
    expect(connection.firmware).toBe('Seeed Tracker T1000-E, 19 Feb 2025');

    const self = await connection.getSelfInfo();
    expect(self.name).toBe('Field T1000');
    expect(self.radioFreq).toBe(910525);
  });

  it("goes on when older firmware doesn't answer the device query", async () => {
    vi.useFakeTimers();
    try {
      const ble = new FakeBle();
      ble.radio.answersQuery = false;
      const connection = new CapacitorBleConnection(ble, 'radio-1');
      const opened = connection.open();
      await vi.advanceTimersByTimeAsync(QUERY_MS);
      await opened;
      expect(connection.firmware).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('writes one frame at a time, in order', async () => {
    const ble = new FakeBle();
    const started: number[] = [];
    const finish: (() => void)[] = [];
    ble.write = (_id, _service, _characteristic, value) => {
      started.push(value.getUint8(0));
      return new Promise((resolve) => finish.push(resolve));
    };
    const connection = new CapacitorBleConnection(ble, 'radio-1');

    const first = connection.sendToRadioFrame(new Uint8Array([1]));
    const second = connection.sendToRadioFrame(new Uint8Array([2]));
    await Promise.resolve();
    expect(started).toEqual([1]);

    finish[0]();
    await first;
    await vi.waitFor(() => expect(started).toEqual([1, 2]));
    finish[1]();
    await second;
  });

  it("doesn't let one failed write hold up the next", async () => {
    const ble = new FakeBle();
    let calls = 0;
    ble.write = async () => {
      if (calls++ === 0) {
        throw new Error('GATT error');
      }
    };
    const connection = new CapacitorBleConnection(ble, 'radio-1');
    await expect(connection.sendToRadioFrame(new Uint8Array([1]))).rejects.toThrow('GATT error');
    await expect(connection.sendToRadioFrame(new Uint8Array([2]))).resolves.toBeUndefined();
  });

  it('says when the radio drops, but not when the app closes it', async () => {
    const ble = new FakeBle();
    const connection = new CapacitorBleConnection(ble, 'radio-1');
    const dropped = vi.fn();
    connection.on('disconnected', dropped);
    await connection.open();

    // meshcore.js delivers its events on a later tick.
    ble.drop();
    await vi.waitFor(() => expect(dropped).toHaveBeenCalledTimes(1));

    await connection.close();
    ble.drop();
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(dropped).toHaveBeenCalledTimes(1);
    expect(ble.disconnects).toEqual(['radio-1']);
  });

  it('gives up waiting on a radio that never answers', async () => {
    vi.useFakeTimers();
    try {
      const waited = within(new Promise(() => undefined), 1000, 'its name');
      const check = expect(waited).rejects.toThrow("the radio didn't answer (its name)");
      await vi.advanceTimersByTimeAsync(1000);
      await check;
    } finally {
      vi.useRealTimers();
    }
  });
});
