"""MeshCore's regional radio presets, as its apps offer them.

A copy of suggested_radio_settings from MeshCore's feed,
https://api.meshcore.nz/api/v1/config, taken on 2026-10-23: the node may
have no internet when its radio needs setting. Each is (title, frequency
MHz, bandwidth kHz, spreading factor, coding rate, path hash size or None).
A path hash size is a network setting the preset suggests; the radio
command only sets the radio's four.
"""

SOURCE = "https://api.meshcore.nz/api/v1/config"
TAKEN = "2026-10-23"

PRESETS = [
    ("Australia", 915.8, 250, 10, 5, None),
    ("Australia (Narrow)", 916.575, 62.5, 7, 7, None),
    ("Australia (Mid)", 915.075, 125, 9, 5, None),
    ("Australia: SA, WA", 923.125, 62.5, 8, 8, None),
    ("Australia: QLD", 923.125, 62.5, 8, 5, None),
    ("Brazil", 923.125, 62.5, 8, 8, None),
    ("Canada", 910.525, 62.5, 7, 5, 3),
    ("Costa Rica", 910.525, 125, 11, 5, None),
    ("EU/UK (Narrow)", 869.618, 62.5, 8, 8, None),
    ("EU/UK (Deprecated)", 869.525, 250, 11, 5, None),
    ("Czech Republic (Narrow)", 869.432, 62.5, 7, 5, 2),
    ("EU 433MHz (Long Range)", 433.65, 250, 11, 5, None),
    ("EU 433MHz (Narrow)", 433.65, 62.5, 8, 8, None),
    ("Hungary", 869.618, 62.5, 7, 5, 2),
    ("Netherlands", 869.618, 62.5, 7, 5, None),
    ("Netherlands (Limburg)", 869.618, 62.5, 8, 8, 2),
    ("New Zealand (Narrow)", 917.375, 62.5, 7, 5, 2),
    ("New Zealand (Gisborne)", 917.375, 250, 11, 5, 1),
    ("Portugal 433", 433.375, 62.5, 9, 6, None),
    ("Portugal 868", 869.618, 62.5, 7, 6, None),
    ("Slovakia", 869.618, 62.5, 7, 5, 2),
    ("Switzerland", 869.618, 62.5, 8, 8, None),
    ("USA", 910.525, 62.5, 7, 5, None),
    ("USA - Southern California", 927.875, 62.5, 7, 5, 3),
    ("Vietnam (Narrow)", 920.25, 62.5, 8, 5, None),
    ("Vietnam (Deprecated)", 920.25, 250, 11, 5, None),
]
