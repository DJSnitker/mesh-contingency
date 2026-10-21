"""Checking a radio's name before its owner joins.

A user's name is always their radio's name, which they set on the radio, so
it may have spaces and punctuation ("Ridge Base 1"). Names that are, or contain,
profanity are refused at join; the list catches the obvious, and an admin
still approves every join.
"""

import re

# Refused anywhere in a name, e.g. "BigShitHead". Rarely part of a real word.
ANYWHERE = {
    "bitch", "cunt", "faggot", "fuck", "motherf", "nigga", "nigger", "shit", "slut", "twat", "whore",
}
# Refused as the whole name or one CamelCase part ("BigAss"), but not inside
# other words, so "Bass", "Hancock", "Dickson" and "Fagan" are fine.
WORDS = {
    "anal", "anus", "arse", "ass", "asshole", "bastard", "bollock", "bollocks", "boner", "boob", "boobs",
    "chink", "clit", "cock", "coon", "cum", "dick", "dildo", "dyke", "fag", "fags", "gook",
    "jizz", "kike", "kkk", "milf", "nazi", "penis", "piss", "porn", "prick", "pussy", "rape",
    "retard", "sex", "spic", "tit", "tits", "vagina", "wank", "wanker", "wetback",
}
# Leetspeak digits, e.g. "5h1t". 1 may stand for i or l.
LEET = [str.maketrans("013456789", "oieasbtbg"), str.maketrans("013456789", "oleasbtbg")]
PARTS_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")


def _spellings(text):
    """text in lower case, as typed and with leetspeak digits read as letters."""
    lowered = text.lower()
    return {lowered} | {lowered.translate(table) for table in LEET}


def is_profane(name):
    """True if name is, contains or is made of a word it shouldn't."""
    for spelling in _spellings(name):
        if spelling in WORDS or any(word in spelling for word in ANYWHERE):
            return True
    # CamelCase parts, reading digits as letters first so "B1gAss" is "Big", "Ass".
    variants = {name} | {name.translate(table) for table in LEET}
    return any(part.lower() in WORDS for variant in variants for part in PARTS_RE.findall(variant))


def name_problem(name):
    """Why a radio's name can't be used to join, or None if it can."""
    if not name.strip():
        return "your radio has no name; set one on the radio, send an advert and try again"
    if any(ord(c) < 0x20 or 0x7f <= ord(c) < 0xa0 for c in name):
        return "your radio's name has control characters; change it on the radio and try again"
    if "(" in name or ")" in name:  # they mark where a name ends in commands
        return "your radio's name can't contain ( or ); change it on the radio and try again"
    if is_profane(name):
        return "your radio's name isn't allowed; change it on the radio and try again"
    return None
