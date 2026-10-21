"""Checking the names people choose with join and rename.

A name is one word of ASCII letters and digits, so commands can always tell
it from what follows, and every radio can show it. Names that are, or contain,
profanity are refused. The list catches the obvious; an admin still approves
every join.
"""

import re

from .api import CommandError

MAX_NAME = 32
NAME_RE = re.compile(rf"[A-Za-z0-9]{{1,{MAX_NAME}}}")

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
    """Why name can't be used, or None if it can."""
    if not NAME_RE.fullmatch(name):
        return f"name must be one word of letters and numbers, up to {MAX_NAME}, e.g. SamJones"
    if is_profane(name):
        return "that name isn't allowed; choose another"
    return None


def check_name(command, name):
    """Raise CommandError if name can't be used."""
    problem = name_problem(name)
    if problem:
        raise CommandError(f"{command}: {problem}")


def suggest(name):
    """A usable name made from name (a radio's name, say), or None."""
    letters = re.sub(r"[^A-Za-z0-9]", "", name)[:MAX_NAME]
    return letters if letters and not name_problem(letters) else None
