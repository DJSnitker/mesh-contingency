/** Bytes as lowercase hex, as the bot writes keys. */
export function toHex(bytes: Uint8Array): string {
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export function fromHex(hex: string): Uint8Array {
  return new Uint8Array((hex.match(/../g) ?? []).map((pair) => parseInt(pair, 16)));
}
