"""radio: the radio's own settings; changing them from the web console only.

radio alone shows them: its name, frequency, bandwidth, spreading factor and
coding rate (and the MeshCore preset they match), TX power, position, clock
and firmware. The changes come only from the web console on the node's
computer, never over the mesh: a wrong one sent over the radio could cut off
the admin who sent it, and the console reaches the radio over USB, so it can
always set things back.

    radio name <name>                    the name others see, after the next advert
    radio power <dBm>                    up to the radio's maximum
    radio position <lat> <lon>           the position it adverts, if it shares one
    radio clock                          set from the computer's clock
    radio reboot                         asks first; the bot restarts with it
    radio freq <preset>                  one of MeshCore's presets (radio_presets.py)
    radio freq <MHz> <kHz> <SF> <CR>     or the four values

freq asks first and says how to go back: a node on settings different from
the rest of the mesh hears no one. Then it reboots the radio, so the new
settings are surely in use, and the bot restarts with it (state.restart: as
the service, systemd starts it again).
"""

import time

from meshcore import EventType

from ..api import CONFIRM_SECONDS, CONSOLE, Command, CommandError, CommandResult, Confirmations
from ..radio_presets import PRESETS
from ..state import duration
from ..watch import ask_radio

RADIO_SECONDS = 5
MAX_NAME_BYTES = 31
# The bandwidths a LoRa radio can use, kHz.
BANDWIDTHS = (7.8, 10.4, 15.6, 20.8, 31.25, 41.7, 62.5, 125, 250, 500)
CHANGES = ("name", "power", "position", "clock", "reboot", "freq")


def settings_text(freq, bw, sf, cr):
    return f"{freq:g} MHz BW{bw:g} SF{sf} CR{cr}"


def matching_presets(freq, bw, sf, cr):
    """The titles of the presets with these four values."""
    return [title for title, *values, _ in PRESETS if values == [freq, bw, sf, cr]]


def parse_freq(text):
    """(freq, bw, sf, cr) from a preset's title (any case) or the four values;
    raises ValueError saying why not."""
    for title, *values, _ in PRESETS:
        if title.lower() == text.lower():
            return tuple(values)
    parts = text.split()
    if len(parts) != 4:
        raise ValueError(f"give a preset (e.g. {PRESETS[0][0]}) or <MHz> <bandwidth kHz> <SF> <CR>")
    try:
        freq, bw, sf, cr = float(parts[0]), float(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        raise ValueError("the frequency and bandwidth are numbers, SF and CR whole numbers") from None
    if not 150 <= freq <= 960:
        raise ValueError(f"{freq:g} MHz isn't a LoRa frequency (150-960)")
    if bw not in BANDWIDTHS:
        raise ValueError(f"bandwidth {bw:g} kHz isn't one of {', '.join(f'{b:g}' for b in BANDWIDTHS)}")
    if not 5 <= sf <= 12:
        raise ValueError("SF is 5 to 12")
    if not 5 <= cr <= 8:
        raise ValueError("CR is 5 to 8")
    return freq, int(bw) if bw.is_integer() else bw, sf, cr


class RadioCommand(Command):
    args = "[name|power|position|clock|reboot|freq ...]"
    summary = "Show the radio's settings; the web console can change them"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.radio = ctx.radio  # connected MeshCore instance
        self.confirmations = Confirmations()

    def current(self):
        info = self.radio.self_info
        return info.get("radio_freq"), info.get("radio_bw"), info.get("radio_sf"), info.get("radio_cr")

    async def describe(self):
        """The settings, briefly, as parts of the reply."""
        info = self.radio.self_info
        parts = [f"{self.name}: {info.get('name', '?')}"]
        if None not in self.current():
            presets = matching_presets(*self.current())
            parts.append(settings_text(*self.current()) + (f" ({', '.join(presets)})" if presets else ""))
        if "tx_power" in info:
            parts.append(f"TX {info['tx_power']}" + (f"/{info['max_tx_power']}" if info.get("max_tx_power") else "")
                         + " dBm")
        if info.get("adv_lat") or info.get("adv_lon"):
            shared = "in adverts" if info.get("adv_loc_policy") else "not in adverts"
            parts.append(f"position {info['adv_lat']:.5f}, {info['adv_lon']:.5f} ({shared})")
        else:
            parts.append("no position")
        clock = await ask_radio(self.radio.commands.get_time, EventType.CURRENT_TIME, RADIO_SECONDS)
        if clock and clock.get("time"):
            off = clock["time"] - time.time()
            parts.append("clock right" if abs(off) < 5 else
                         f"clock {duration(abs(off))} {'ahead' if off > 0 else 'behind'}")
        device = await ask_radio(self.radio.commands.send_device_query, EventType.DEVICE_INFO, RADIO_SECONDS) or {}
        firmware = " ".join(str(device[k]) for k in ("model", "ver", "fw_build") if device.get(k))
        if firmware:
            parts.append(f"firmware {firmware}")
        return parts

    async def ask(self, request, what):
        """Run a radio request; raise CommandError if the radio refuses."""
        result = await request
        if result is None or result.type == EventType.ERROR:
            raise CommandError(f"{self.name}: the radio didn't {what}: {getattr(result, 'payload', 'no answer')}")

    async def refresh(self):
        """Have the radio send its settings again, so self_info shows the change."""
        await ask_radio(self.radio.commands.send_appstart, EventType.SELF_INFO, RADIO_SECONDS)

    def restart_bot(self, why):
        """Have the bot restart (it waits for the reply to go), if it runs
        under the bot: before the reboot, so the radio dropping is expected."""
        if self.ctx.state.restart:
            self.ctx.state.restart(why)
        # So the next run's node watch doesn't announce the restart as a problem.
        rebooting = getattr(self.ctx.state.watch, "rebooting", None)
        if rebooting:
            rebooting(why)

    def confirm(self, sender, what, question):
        """None if sender confirmed `what`; otherwise the reply asking them to."""
        if self.confirmations.confirmed(sender.public_key, what):
            return None
        return CommandResult(console="", reply=f"{self.name}: {question} Send it again within "
                                               f"{CONFIRM_SECONDS // 60} min to confirm.", asks=True)

    async def execute(self, text, sender):
        action, _, rest = text.strip().partition(" ")
        action, rest = action.lower(), rest.strip()
        if not action:
            return CommandResult(console="", reply="; ".join(await self.describe()))
        if action not in CHANGES:
            raise CommandError(f"usage: {self.usage}")
        if sender.public_key != CONSOLE.public_key:
            raise CommandError(f"{self.name}: changes only from the web console on the node's computer")
        by = self.ctx.name_of(sender)
        changed = await getattr(self, f"set_{action}")(rest, sender)
        if isinstance(changed, CommandResult):  # a question
            return changed
        self.ctx.state.record(by, f"radio: {changed}")
        reply = f"{self.name}: {changed}"
        return CommandResult(console=f"{by}: {reply}", reply=reply)

    async def set_name(self, rest, sender):
        if not rest:
            raise CommandError(f"usage: {self.name} name <name>")
        if len(rest.encode("utf-8")) > MAX_NAME_BYTES or any(ord(c) < 0x20 for c in rest):
            raise CommandError(f"{self.name}: a name is up to {MAX_NAME_BYTES} bytes, without control characters")
        old = self.radio.self_info.get("name", "?")
        await self.ask(self.radio.commands.set_name(rest), "take the name")
        await self.refresh()
        return f"name {old} -> {rest}; others see it after the next advert"

    async def set_power(self, rest, sender):
        top = self.radio.self_info.get("max_tx_power") or 30
        try:
            power = int(rest)
        except ValueError:
            raise CommandError(f"usage: {self.name} power <dBm, 1-{top}>") from None
        if not 1 <= power <= top:
            raise CommandError(f"{self.name}: TX power is 1 to {top} dBm on this radio")
        old = self.radio.self_info.get("tx_power")
        await self.ask(self.radio.commands.set_tx_power(power), "take the TX power")
        await self.refresh()
        return f"TX power {old} -> {power} dBm"

    async def set_position(self, rest, sender):
        try:
            lat, lon = (float(part) for part in rest.replace(",", " ").split())
        except ValueError:
            raise CommandError(f"usage: {self.name} position <latitude> <longitude>") from None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise CommandError(f"{self.name}: latitude is -90 to 90, longitude -180 to 180")
        await self.ask(self.radio.commands.set_coords(lat, lon), "take the position")
        await self.refresh()
        return f"position {lat:.5f}, {lon:.5f}"

    async def set_clock(self, rest, sender):
        if rest:
            raise CommandError(f"usage: {self.name} clock")
        await self.ask(self.radio.commands.set_time(int(time.time())), "set its clock")
        return "clock set from the computer"

    async def set_reboot(self, rest, sender):
        if rest:
            raise CommandError(f"usage: {self.name} reboot")
        question = self.confirm(sender, "reboot", "this reboots the radio, and the bot restarts with it (about a "
                                                  "minute): open the console again then.")
        if question:
            return question
        self.restart_bot("the radio was rebooted from the console")
        await self.radio.commands.reboot()  # it answers nothing: it's restarting
        return "rebooting; the bot restarts with it"

    async def set_freq(self, rest, sender):
        try:
            new = parse_freq(rest)
        except ValueError as e:
            raise CommandError(f"{self.name}: {e}") from None
        old = self.current()
        presets = matching_presets(*new)
        named = settings_text(*new) + (f" ({', '.join(presets)})" if presets else "")
        back = (f" To go back, from the console: {self.name} freq {' '.join(f'{v:g}' for v in old)}."
                if None not in old else "")
        question = self.confirm(sender, ("freq", new), f"this sets the radio to {named} and reboots it; the bot "
                                                       f"restarts with it. Radios on other settings won't hear this "
                                                       f"node.{back}")
        if question:
            return question
        await self.ask(self.radio.commands.set_radio(*new), "take the settings")
        self.restart_bot(f"the radio was set to {settings_text(*new)} from the console")
        await self.radio.commands.reboot()
        was = f" (was {settings_text(*old)})" if None not in old else ""
        return f"set to {named}{was}; rebooting, and the bot restarts with it"
