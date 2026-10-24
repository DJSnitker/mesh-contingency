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

export interface InboxMessage {
  from: string;
  /** As the bot says it: "just now", "5m ago", "2d ago". */
  ago: string;
  text: string;
}

export type Inbox =
  | { kind: 'inbox'; outcome: 'empty' | 'refused' }
  | { kind: 'inbox'; outcome: 'sealed'; count: number; senders: Omit<InboxMessage, 'text'>[] }
  | { kind: 'inbox'; outcome: 'messages'; messages: InboxMessage[]; page?: number; pages?: number };

export type Msg =
  | { kind: 'msg'; outcome: 'saved'; to: string; waiting: number }
  | { kind: 'msg'; outcome: 'refused' };

export type ClearInbox = { kind: 'clearinbox'; deleted: number; kept: number };

export type SetPass =
  | { kind: 'setpass'; outcome: 'set'; deleted: number }
  | { kind: 'setpass'; outcome: 'confirm'; sealed: number }
  | { kind: 'setpass'; outcome: 'already' | 'refused' };

export type Reply = WhoAmI | Join | Inbox | Msg | ClearInbox | SetPass;

const AGO = String.raw`just now|\d+[dhm] ago`;
const ENTRY = new RegExp(String.raw`^(.+?) (${AGO}): ([\s\S]*)$`);
const SENDER = new RegExp(String.raw`^(.+) (${AGO})$`);

export function parseInbox(messages: string[]): Inbox | null {
  const [first] = messages;
  if (messages.length === 1 && first === 'inbox: no messages') {
    return { kind: 'inbox', outcome: 'empty' };
  }
  const sealed = /^inbox: (\d+) message\(s\) from (.+)\. Send inbox <passphrase> to read\.$/.exec(
    first ?? '',
  );
  if (messages.length === 1 && sealed) {
    const senders = sealed[2].split(', ').map((s) => SENDER.exec(s));
    if (senders.some((s) => !s)) {
      return null;
    }
    return {
      kind: 'inbox',
      outcome: 'sealed',
      count: Number(sealed[1]),
      senders: senders.map((s) => ({ from: s![1], ago: s![2] })),
    };
  }
  if (messages.length === 1 && first.startsWith('inbox: ')) {
    return { kind: 'inbox', outcome: 'refused' };
  }
  const footer = /^inbox: page (\d+) of (\d+); send .+ for more$/.exec(messages.at(-1) ?? '');
  const entries = group(footer ? messages.slice(0, -1) : messages).map((g) => ENTRY.exec(g.text));
  if (!entries.length || entries.some((e) => !e)) {
    return null;
  }
  const parsed: Inbox = {
    kind: 'inbox',
    outcome: 'messages',
    messages: entries.map((e) => ({ from: e![1], ago: e![2], text: e![3] })),
  };
  return footer ? { ...parsed, page: Number(footer[1]), pages: Number(footer[2]) } : parsed;
}

export function parseMsg(text: string): Msg | null {
  const saved = /^msg: saved for (.+) \((\d+) in their inbox\)$/.exec(text);
  if (saved) {
    return { kind: 'msg', outcome: 'saved', to: saved[1], waiting: Number(saved[2]) };
  }
  return text.startsWith('msg: ') ? { kind: 'msg', outcome: 'refused' } : null;
}

export function parseClearInbox(text: string): ClearInbox | null {
  const cleared =
    /^clearinbox: deleted (\d+) message\(s\)(?:; (\d+) new one\(s\) kept, see inbox)?$/.exec(text);
  return cleared
    ? { kind: 'clearinbox', deleted: Number(cleared[1]), kept: Number(cleared[2] ?? 0) }
    : null;
}

export function parseSetPass(messages: string[]): SetPass | null {
  const [first = ''] = messages;
  if (first === 'setpass: passphrase set; new messages to you will be sealed.') {
    const deleted = messages
      .map((m) => /^setpass: deleted (\d+) message\(s\) sealed/.exec(m))
      .find(Boolean);
    return { kind: 'setpass', outcome: 'set', deleted: Number(deleted?.[1] ?? 0) };
  }
  if (first === 'setpass: that is already your passphrase') {
    return { kind: 'setpass', outcome: 'already' };
  }
  const confirm =
    /^setpass: your (\d+) sealed message\(s\) only open with your old passphrase/.exec(first);
  if (confirm) {
    return { kind: 'setpass', outcome: 'confirm', sealed: Number(confirm[1]) };
  }
  return first.startsWith('setpass: ') ? { kind: 'setpass', outcome: 'refused' } : null;
}

/** What the app reads from the node's reply to a command, or null when it can't. */
export function parseReply(command: string, messages: string[]): Reply | null {
  const text = reassemble(messages).text;
  switch (command.split(' ')[0]) {
    case 'whoami':
      return parseWhoami(text);
    case 'join':
      return parseJoin(text);
    case 'inbox':
      return parseInbox(messages);
    case 'msg':
      return parseMsg(text);
    case 'clearinbox':
      return parseClearInbox(text);
    case 'setpass':
      return parseSetPass(messages);
    default:
      return null;
  }
}

const PART = /^\((\d+)\/(\d+)\) ([\s\S]*)$/;

/** One message of a reply, from one or more mesh messages. */
export interface Group {
  text: string;
  numbered: boolean;
  /** Every numbered part is in (always, for one not numbered). */
  complete: boolean;
}

/**
 * A reply's mesh messages, grouped into the messages they make: numbered
 * parts ("(2/3) ...") go with the others of their message, in order (a reply
 * can hold several numbered messages, as inbox's can); the rest stand alone.
 */
export function group(messages: string[]): Group[] {
  const groups: { total: number | null; parts: Map<number, string> }[] = [];
  for (const message of messages) {
    const part = PART.exec(message);
    if (!part) {
      groups.push({ total: null, parts: new Map([[1, message]]) });
      continue;
    }
    const [number, total] = [Number(part[1]), Number(part[2])];
    const open = groups.find(
      (g) => g.total === total && g.parts.size < total && !g.parts.has(number),
    );
    if (open) {
      open.parts.set(number, part[3]);
    } else {
      groups.push({ total, parts: new Map([[number, part[3]]]) });
    }
  }
  return groups.map((g) => ({
    text: [...g.parts.entries()]
      .sort(([a], [b]) => a - b)
      .map(([, text]) => text)
      .join(' '),
    numbered: g.total !== null,
    complete: g.total === null || g.parts.size === g.total,
  }));
}

/** A reply put back together: its messages, one per line. */
export function reassemble(messages: string[]): {
  text: string;
  numbered: boolean;
  complete: boolean;
} {
  const groups = group(messages);
  return {
    text: groups.map((g) => g.text).join('\n'),
    numbered: groups.length === 1 && groups[0].numbered,
    complete: groups.every((g) => g.complete),
  };
}
