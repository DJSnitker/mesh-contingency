import { TestBed } from '@angular/core/testing';

import { BLE } from '../radio/ble';
import { FakeBle, NODE_KEY } from '../radio/fake-ble';
import { MIN_ACK_MS, Radio, SEND_ATTEMPTS } from '../radio/radio';
import { CHOSEN, FIRST_REPLY_MS, NodeLink, PARTS_MS, QUIET_MS } from './node-link';

const NODE = { publicKey: NODE_KEY, name: 'Ridge Node', type: 1 };

describe('NodeLink', () => {
  let ble: FakeBle;

  async function connected(): Promise<NodeLink> {
    TestBed.configureTestingModule({ providers: [{ provide: BLE, useValue: ble }] });
    await TestBed.inject(Radio).pick();
    // Let the fetch of waiting messages on connect finish, before a test
    // turns to fake timers.
    await new Promise((resolve) => setTimeout(resolve, 20));
    return TestBed.inject(NodeLink);
  }

  beforeEach(() => {
    ble = new FakeBle();
    localStorage.clear();
  });

  afterEach(() => vi.useRealTimers());

  it('remembers the node picked', async () => {
    const link = await connected();
    link.choose(NODE);
    expect(JSON.parse(localStorage.getItem(CHOSEN)!)).toEqual({
      publicKey: NODE_KEY,
      name: 'Ridge Node',
    });
    link.unchoose();
    expect(localStorage.getItem(CHOSEN)).toBeNull();
    expect(link.node()).toBeNull();
  });

  it('sends a command and reads the answer', async () => {
    const link = await connected();
    link.choose(NODE);
    const exchange = await link.ask('whoami', { one: true });
    expect(exchange).toMatchObject({ label: 'whoami', step: 'answered', attempt: 1 });
    expect(exchange.text).toBe('Field T1000 (abababababab); no passphrase; no messages');
  });

  it('checks whether the user is a user, and joins', async () => {
    const link = await connected();
    link.choose(NODE);
    await link.check();
    expect(link.whoami()).toMatchObject({ user: true, name: 'Field T1000', messages: 0 });

    ble.node = (text) =>
      text === 'whoami'
        ? ['unrecognized user or function']
        : ['join: request sent to the admins as Field T1000'];
    await link.check();
    expect(link.whoami()).toEqual({ kind: 'whoami', user: false });
    await link.join();
    expect(link.joined()).toEqual({ kind: 'join', outcome: 'sent', name: 'Field T1000' });
  });

  it('takes silence after whoami as likely not a user (strangers hear back once in 5 minutes)', async () => {
    const link = await connected();
    link.choose(NODE);
    vi.useFakeTimers();
    ble.node = () => [];
    const checked = link.check();
    await vi.advanceTimersByTimeAsync(FIRST_REPLY_MS + 1000);
    await checked;
    expect(link.whoami()).toBeNull();
    expect(link.unanswered()).toBe(true);
    expect(link.exchange()?.step).toBe('no answer');
  });

  it('puts numbered parts back in order, done once all are in', async () => {
    const link = await connected();
    link.choose(NODE);
    ble.node = () => ['(2/2) world', '(1/2) hello'];
    const exchange = await link.ask('wx 59601');
    expect(exchange.step).toBe('answered');
    expect(exchange.text).toBe('hello world');
    expect(exchange.messages).toEqual(['(2/2) world', '(1/2) hello']);
  });

  it('shows what came of a numbered reply when the rest never does', async () => {
    const link = await connected();
    link.choose(NODE);
    vi.useFakeTimers();
    ble.node = () => ['(1/3) hello'];
    const asked = link.ask('wx 59601');
    await vi.advanceTimersByTimeAsync(PARTS_MS + 1000);
    expect((await asked).text).toBe('hello');
  });

  it('waits a little for more messages of a reply that isn’t numbered', async () => {
    const link = await connected();
    link.choose(NODE);
    vi.useFakeTimers();
    ble.node = () => ['first'];
    const asked = link.ask('inbox');
    await vi.advanceTimersByTimeAsync(QUIET_MS / 2 + 1000);
    expect(link.exchange()?.step).toBe('waiting');
    ble.deliver(NODE_KEY, 'second');
    await vi.advanceTimersByTimeAsync(QUIET_MS + 1000);
    expect((await asked).text).toBe('first\nsecond');
  });

  it("says when the node's radio never acknowledged the command", async () => {
    const link = await connected();
    link.choose(NODE);
    vi.useFakeTimers();
    ble.ackFrom = null;
    const asked = link.ask('whoami', { one: true });
    await vi.advanceTimersByTimeAsync(MIN_ACK_MS * SEND_ATTEMPTS + 1000);
    expect(await asked).toMatchObject({
      step: 'not delivered',
      attempt: SEND_ATTEMPTS,
      text: null,
    });
  });

  it('sends one command at a time', async () => {
    const link = await connected();
    link.choose(NODE);
    ble.node = (text) => [`${text}: done`];
    const [a, b] = await Promise.all([
      link.ask('one', { one: true }),
      link.ask('two', { one: true }),
    ]);
    expect([a.text, b.text]).toEqual(['one: done', 'two: done']);
    expect(ble.sent.map(([, text]) => text)).toEqual(['one', 'two']);
  });

  it("keeps the node's notices, and reads nobody else's messages", async () => {
    const link = await connected();
    link.choose(NODE);
    ble.deliver('e0'.repeat(32), 'hello from Erin');
    ble.deliver(NODE_KEY, 'inbox: new message from Erin; send inbox to read');
    await vi.waitFor(() =>
      expect(link.notices().map((n) => n.text)).toEqual([
        'inbox: new message from Erin; send inbox to read',
      ]),
    );
  });

  it('a notice arriving while a command waits is still a notice', async () => {
    const link = await connected();
    link.choose(NODE);
    ble.node = () => [
      'An admin changed your email addresses: qm a@example.com',
      "join: you're already a user",
    ];
    const exchange = await link.ask('join', { one: true });
    expect(exchange.text).toBe("join: you're already a user");
    expect(link.notices()[0].text).toContain('An admin changed');
  });

  it('checks again when the welcome comes', async () => {
    const link = await connected();
    link.choose(NODE);
    ble.deliver(NODE_KEY, "Welcome, Field T1000: you're now a user. Send help for your commands.");
    await vi.waitFor(() => expect(link.whoami()).toMatchObject({ user: true }));
    expect(ble.sent.map(([, text]) => text)).toEqual(['whoami']);
  });

  it('says to pick the node first', async () => {
    const link = await connected();
    expect(await link.ask('whoami')).toMatchObject({
      step: 'failed',
      text: 'Pick the node first.',
    });
  });
});
