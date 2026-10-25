// The demo build (npm run demo): the app in a browser, on the fake radio
// from the tests, with made-up contacts and chats and the node answering
// with the bot's real replies (tests/fixtures/app_replies.json). For seeing
// the screens, at a phone's size or a tablet's, without a radio.
import { Provider } from '@angular/core';

import fixtures from '../../../tests/fixtures/app_replies.json';
import { HISTORY } from './chat/chat-history';
import { CHOSEN } from './node/node-link';
import { BLE } from './radio/ble';
import { FakeBle, NODE_KEY } from './radio/fake-ble';
import { REMEMBERED } from './radio/radio';

const NAMES = [
  'Abilene Info',
  'Erin',
  'Dana KJ5AAA',
  'Fourbirds Control',
  'Logan',
  'Quigly Ranger',
  'Steve R.',
  'Tri-County South',
  'V-RAP',
  'WS5EAB',
];

function demoBle(): FakeBle {
  const ble = new FakeBle();
  const now = Math.floor(Date.now() / 1000);
  ble.contacts = [
    { name: 'Ridge Node', publicKey: NODE_KEY, type: 1 },
    { name: 'Hill Repeater', publicKey: 'a1'.repeat(32), type: 2, hops: -1 },
    ...NAMES.map((name, i) => ({
      name,
      publicKey: (i + 16).toString(16).repeat(32),
      type: 1,
      hops: i % 4 === 3 ? -1 : i % 3,
      lastAdvert: now - i * 2400,
    })),
  ];
  // A real radio takes a while to list many contacts.
  ble.contactsMs = 2500;
  ble.node = (text) => fixtures.cases.find((c) => 'send' in c && c.send === text)?.reply ?? [];
  return ble;
}

function seed(): void {
  localStorage.setItem(
    REMEMBERED,
    JSON.stringify({ deviceId: 'AA:BB:CC:DD:EE:FF', name: 'Field T1000' }),
  );
  localStorage.setItem(CHOSEN, JSON.stringify({ publicKey: NODE_KEY, name: 'Ridge Node' }));
  if (localStorage.getItem(HISTORY)) {
    return;
  }
  const at = Date.now();
  const erin = (17).toString(16).repeat(6);
  const dana = (18).toString(16).repeat(6);
  localStorage.setItem(
    HISTORY,
    JSON.stringify({
      [`dm:${erin}`]: {
        lines: [
          { id: 1, mine: false, text: 'Are you at the shelter?', at: at - 3_600_000 },
          {
            id: 2,
            mine: true,
            text: 'Yes, with the kids. All ok.',
            at: at - 3_500_000,
            status: 'delivered',
          },
          { id: 3, mine: false, text: 'Good. Bringing water at 6.', at: at - 600_000 },
        ],
        unread: 1,
      },
      'ch:#contingency-wx': {
        lines: [
          {
            id: 4,
            mine: false,
            from: 'Ridge Node',
            text: 'Severe Thunderstorm Warning: Taylor, TX until 7:45 PM',
            at: at - 1_800_000,
          },
        ],
        unread: 0,
      },
      [`dm:${dana}`]: {
        lines: [
          {
            id: 5,
            mine: true,
            text: 'Net at 7 tonight',
            at: at - 90_000_000,
            status: 'not delivered',
          },
        ],
        unread: 0,
      },
    }),
  );
}

seed();

export const DEMO: Provider[] = [{ provide: BLE, useValue: demoBle() }];
