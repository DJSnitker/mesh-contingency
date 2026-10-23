/** How long ago a time was, briefly, as the bot says it: "just now", "5m ago", "2d ago". */
export function ago(then: number, now: number): string {
  const seconds = now - then;
  for (const [unit, size] of [
    ['d', 86400],
    ['h', 3600],
    ['m', 60],
  ] as const) {
    if (seconds >= size) {
      return `${Math.floor(seconds / size)}${unit} ago`;
    }
  }
  return 'just now';
}

/** A length of time in its two largest units, as the bot says it: "2d 3h", "3h 5m", "12m". */
export function duration(seconds: number): string {
  const s = Math.floor(seconds);
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  if (days) {
    return `${days}d ${hours}h`;
  }
  if (hours) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

/** A day and time, e.g. "Oct 22, 21:05". */
export function when(time: number): string {
  return new Date(time * 1000).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

/** A clock time, e.g. "21:05:08". */
export function clock(time: number): string {
  return new Date(time * 1000).toLocaleTimeString([], { hour12: false });
}
