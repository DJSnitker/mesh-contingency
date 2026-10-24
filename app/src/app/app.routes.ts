import { Routes } from '@angular/router';

import { Planned } from './planned';

/**
 * The app's screens (docs/plans/mobile-app.md). Each is Planned until the PR
 * that builds it; its data says what it will do.
 */
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'node' },
  {
    path: 'node',
    component: Planned,
    title: 'Node',
    data: {
      icon: 'radio',
      what: 'Connect to your radio over Bluetooth, pick the node, see whether you are a user, and ask to join.',
      pr: 'Bluetooth and the node',
      more: [
        { path: '/email', label: 'Email', icon: 'mail' },
        { path: '/weather', label: 'Weather and verse', icon: 'cloud' },
      ],
    },
  },
  {
    path: 'mailbox',
    component: Planned,
    title: 'Mailbox',
    data: {
      icon: 'inbox',
      what: 'Read the messages left for you, leave one for another user, and seal yours with a passphrase.',
      pr: 'Mailbox',
    },
  },
  {
    path: 'checkins',
    component: Planned,
    title: 'Check-ins',
    data: {
      icon: 'check',
      what: "Tell the others you're ok, or how you are, and look up someone's last check-in.",
      pr: 'Check-ins',
    },
  },
  {
    path: 'chat',
    component: Planned,
    title: 'Chat',
    data: {
      icon: 'chat',
      what: "Direct messages with your radio's contacts, and its channels.",
      pr: 'Chat',
    },
  },
  {
    path: 'radio',
    component: Planned,
    title: 'Radio',
    data: {
      icon: 'sliders',
      what: "Your own radio's name, power, position, clock, frequency and contacts.",
      pr: 'Radio',
    },
  },
  {
    path: 'email',
    component: Planned,
    title: 'Email',
    data: {
      icon: 'mail',
      what: 'Email your message to your preset contact or group, or any address, and change your addresses.',
      pr: 'Email, weather and verse',
    },
  },
  {
    path: 'weather',
    component: Planned,
    title: 'Weather and verse',
    data: {
      icon: 'cloud',
      what: 'The weather and alerts for a zipcode or county, and a Bible verse.',
      pr: 'Email, weather and verse',
    },
  },
  { path: '**', redirectTo: 'node' },
];

/** The tab bar, in order. Email and weather are reached from Node. */
export const TABS = [
  { path: '/node', label: 'Node', icon: 'radio' },
  { path: '/mailbox', label: 'Mailbox', icon: 'inbox' },
  { path: '/checkins', label: 'Check-ins', icon: 'check' },
  { path: '/chat', label: 'Chat', icon: 'chat' },
  { path: '/radio', label: 'Radio', icon: 'sliders' },
];
