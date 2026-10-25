import { Routes } from '@angular/router';

import { BibleScreen } from './bible/bible-screen';
import { ChatList } from './chat/chat-list';
import { ChatScreen } from './chat/chat-screen';
import { ContactList } from './chat/contact-list';
import { CheckinsScreen } from './checkins/checkins-screen';
import { EmailScreen } from './email/email-screen';
import { LicensesScreen } from './licenses/licenses-screen';
import { MailboxScreen } from './mailbox/mailbox-screen';
import { NodeScreen } from './node/node-screen';
import { RadioScreen } from './radio-tab/radio-screen';
import { WeatherScreen } from './weather/weather-screen';

/** The app's screens (docs/plans/mobile-app.md). */
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'node' },
  { path: 'node', component: NodeScreen, title: 'Node' },
  { path: 'mailbox', component: MailboxScreen, title: 'Mailbox' },
  { path: 'checkins', component: CheckinsScreen, title: 'Check-ins' },
  { path: 'chat', component: ChatList, title: 'Chat', data: { kind: 'dm' } },
  { path: 'chat/channels', component: ChatList, title: 'Channels', data: { kind: 'ch' } },
  { path: 'chat/contacts', component: ContactList, title: 'Contacts' },
  { path: 'chat/dm/:key', component: ChatScreen, title: 'Chat' },
  { path: 'chat/channel/:name', component: ChatScreen, title: 'Chat' },
  { path: 'radio', component: RadioScreen, title: 'Radio' },
  { path: 'email', component: EmailScreen, title: 'Email' },
  { path: 'weather', component: WeatherScreen, title: 'Weather' },
  { path: 'bible', component: BibleScreen, title: 'Bible' },
  { path: 'radio/licenses', component: LicensesScreen, title: 'Open-source licenses' },
  { path: '**', redirectTo: 'node' },
];

/** The tab bar, in order. Email is reached from Node. */
export const TABS = [
  { path: '/mailbox', label: 'Mailbox', icon: 'inbox' },
  { path: '/checkins', label: 'Check-ins', icon: 'check' },
  { path: '/chat', label: 'Chat', icon: 'chat' },
  { path: '/weather', label: 'Weather', icon: 'cloud' },
  { path: '/bible', label: 'Bible', icon: 'book' },
  { path: '/node', label: 'Node', icon: 'radio' },
  { path: '/radio', label: 'Radio', icon: 'sliders' },
];
