"""Example third-party mesh-contingency commands: dice rolls and coin flips.

Shows both ways to write a command: a plain function (roll) and a Command
subclass (flip). Install with `pip install ./examples/mesh-dice`, then enable
in config.toml:

    [commands.roll]
    permission = "public"
    max_dice = 10

    [commands.flip]
    permission = "public"
"""

import random
import re

from mesh_contingency.api import Command, CommandError, CommandResult, command

DICE_RE = re.compile(r"(\d*)d(\d+)", re.IGNORECASE)


@command(args="[NdS]", summary="Roll dice, e.g. 2d6 (default 1d6)")
def roll(text, sender, ctx):
    """A function command: gets the text after the name, the Sender and the
    Context, and returns the reply text."""
    m = DICE_RE.fullmatch(text or "1d6")
    if not m:
        raise CommandError(f"usage: {ctx.name} [NdS], e.g. 2d6")
    count, sides = int(m[1] or 1), int(m[2])
    max_dice = ctx.options.get("max_dice", 10)  # from [commands.roll] in config.toml
    if not 1 <= count <= max_dice or not 2 <= sides <= 1000:
        raise CommandError(f"{ctx.name}: 1-{max_dice} dice of 2-1000 sides")
    rolls = [random.randint(1, sides) for _ in range(count)]
    detail = f" ({' + '.join(map(str, rolls))})" if count > 1 else ""
    return f"{sender.name} rolled {count}d{sides}: {sum(rolls)}{detail}"


class FlipCommand(Command):
    """A class command: set args and summary, implement execute(), and use
    self.ctx for options, users, the radio and the other commands."""

    args = "[times]"
    summary = "Flip a coin"

    async def execute(self, text, sender):
        times = int(text) if text.isdigit() else 1
        if not 1 <= times <= 20:
            raise CommandError(f"usage: {self.usage} (1-20)")
        flips = [random.choice("HT") for _ in range(times)]
        return CommandResult(console=f"{sender.name} flipped {''.join(flips)}",
                             reply=f"{''.join(flips)} ({flips.count('H')} heads)")
