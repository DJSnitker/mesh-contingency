// Reading the bot's replies, as tests/fixtures/app_replies.json pins them.
// A reply that doesn't match reads as null, and the screen shows its text.

/** What the bot sends a sender who isn't allowed the command (bot.py). */
export const UNRECOGNIZED = 'unrecognized user or function';

export interface WhoAmIUser {
  kind: 'whoami';
  user: true;
  name: string;
  keyPrefix: string;
  admin: boolean;
  passphrase: boolean;
  /** Other settings, as the bot words them ("qm erin@example.com"). */
  settings: string[];
  messages: number;
  unread: number;
}

export type WhoAmI = WhoAmIUser | { kind: 'whoami'; user: false };

export type Join =
  | { kind: 'join'; outcome: 'sent' | 'updated'; name: string }
  | { kind: 'join'; outcome: 'already' | 'refused' };

export type Notice =
  | { kind: 'notice'; notice: 'welcome' | 'admin' | 'join request' }
  | { kind: 'notice'; notice: 'message'; from: string };

export function parseWhoami(text: string): WhoAmI | null {
  if (text === UNRECOGNIZED) {
    return { kind: 'whoami', user: false };
  }
  const [first, ...rest] = text.split('; ');
  const who = /^(.+) \(([0-9a-f]{12})\)$/.exec(first);
  if (!who) {
    return null;
  }
  const parsed: WhoAmIUser = {
    kind: 'whoami',
    user: true,
    name: who[1],
    keyPrefix: who[2],
    admin: false,
    passphrase: false,
    settings: [],
    messages: 0,
    unread: 0,
  };
  for (const part of rest) {
    const box = /^(\d+) message\(s\), (\d+) unread$/.exec(part);
    if (part === 'admin') {
      parsed.admin = true;
    } else if (part === 'passphrase set') {
      parsed.passphrase = true;
    } else if (box) {
      parsed.messages = Number(box[1]);
      parsed.unread = Number(box[2]);
    } else if (part !== 'no passphrase' && part !== 'no messages') {
      parsed.settings.push(part);
    }
  }
  return parsed;
}

export function parseJoin(text: string): Join | null {
  const asked =
    /^join: request (sent to the admins|updated) as (.+?)(?:; you're listed under .*)?$/.exec(text);
  if (asked) {
    return { kind: 'join', outcome: asked[1] === 'updated' ? 'updated' : 'sent', name: asked[2] };
  }
  if (text === "join: you're already a user") {
    return { kind: 'join', outcome: 'already' };
  }
  return text.startsWith('join: ') ? { kind: 'join', outcome: 'refused' } : null;
}

/** A message the node sends on its own, not in answer to a command; else null. */
export function parseNotice(text: string): Notice | null {
  if (/^Welcome, .+: you're now a user\./.test(text)) {
    return { kind: 'notice', notice: 'welcome' };
  }
  const message = /^\S+: new message from (.+?)(?:; send \S+ to read)?$/.exec(text);
  if (message) {
    return { kind: 'notice', notice: 'message', from: message[1] };
  }
  if (text.startsWith('An admin ')) {
    return { kind: 'notice', notice: 'admin' };
  }
  return text.startsWith('Join request: ') ? { kind: 'notice', notice: 'join request' } : null;
}

const PART = /^\((\d+)\/(\d+)\) ([\s\S]*)$/;

/**
 * A reply's messages put back together. Numbered parts ("(2/3) ...") are put
 * in order and joined, complete once every one is in; other messages are
 * kept in the order they came, one per line.
 */
export function reassemble(messages: string[]): {
  text: string;
  numbered: boolean;
  complete: boolean;
} {
  const parts = messages.map((m) => PART.exec(m));
  const total = parts[0]?.[2];
  if (!parts.length || parts.some((p) => !p || p[2] !== total)) {
    return { text: messages.join('\n'), numbered: false, complete: true };
  }
  const byNumber = new Map(parts.map((p) => [Number(p![1]), p![3]]));
  const count = Number(total);
  const ordered = [...byNumber.entries()].sort(([a], [b]) => a - b).map(([, text]) => text);
  return { text: ordered.join(' '), numbered: true, complete: byNumber.size === count };
}
