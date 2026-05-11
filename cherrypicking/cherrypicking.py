from opentrons import protocol_api
import csv
import datetime
import getpass
import os
from collections import defaultdict

metadata = {
    "protocolName": "OT-2 Cherrypicking",
    "author": "Sarah Mughal",
}
requirements = {"robotType": "OT-2", "apiLevel": "2.13"}

# --- User config ---
TRANSFER_CSV_PATH = "/Users/sarahmughal/Desktop/oldham lab/opentrons scripts/cherrypicking/cherrypicking_test.csv"
PIPETTE_TYPE = "p300_single_gen2"
PIPETTE_MOUNT = "right"
TIP_TYPE = "standard_300"
TIP_REUSE = "always"  # 'always' = new tip per transfer, 'never' = one tip throughout

LOG_DIR = "/Users/sarahmughal/Desktop/oldham lab/opentrons scripts/cherrypicking/simulation_logs"

# Dead volume per labware type (uL) — liquid unreachable at the bottom
DEAD_VOLUME = {
    "nest_96_wellplate_200ul_flat": 5,
    "nest_96_wellplate_100ul_pcr_full_skirt": 5,
    "nest_96_wellplate_2ml_deep": 50,
    "nest_12_reservoir_15ml": 200,
    "nest_1_reservoir_195ml": 1000,
    "agilent_1_reservoir_290ml": 1000,
}
SAFETY_BUFFER_PCT = 0.20  # 20% extra on top of total transfer volume


def run(ctx: protocol_api.ProtocolContext):

    # ------------------------------------------------------------------ #
    #  Logging setup — inside run() so opentrons_simulate picks it up     #
    # ------------------------------------------------------------------ #
    username = getpass.getuser()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"simulation_{username}_{timestamp}.txt")

    def log(message):
        """Print to terminal and append to log file simultaneously."""
        print(message)
        with open(log_path, "a") as f:
            f.write(message + "\n")

    # Write header block
    log("Simulation Log")
    log("=" * 60)
    log(f"User:       {username}")
    log(f"Timestamp:  {timestamp}")
    log(f"Protocol:   {metadata['protocolName']}")
    log(f"CSV:        {TRANSFER_CSV_PATH}")
    log(f"Pipette:    {PIPETTE_TYPE} on {PIPETTE_MOUNT} mount")
    log(f"Tip reuse:  {TIP_REUSE}")
    log("=" * 60)
    log("")

    # ------------------------------------------------------------------ #
    #  Read CSV                                                            #
    # ------------------------------------------------------------------ #
    with open(TRANSFER_CSV_PATH, "r") as f:
        reader = csv.reader(f)
        next(reader)  # skip header row
        transfer_info = [
            [val.strip().lower() for val in row]
            for row in reader
            if row and row[0].strip()
        ]

    log(f"Loaded {len(transfer_info)} transfers from CSV")
    log("")

    # ------------------------------------------------------------------ #
    #  Pre-run volume check                                                #
    # ------------------------------------------------------------------ #
    log("--- Pre-Run Volume Check ---")
    log(
        f"{'Slot':<6} {'Well':<6} {'Labware':<45} {'Transfer Vol':>13} {'Dead Vol':>10} {'Safety +20%':>12} {'MINIMUM LOAD':>13}"
    )
    log("-" * 110)

    required = defaultdict(float)
    well_to_labware = {}
    for line in transfer_info:
        s_lw, s_slot, s_well = line[0], line[1], line[2]
        key = (s_slot, s_well.upper())
        required[key] += float(line[7])
        well_to_labware[key] = s_lw

    for (slot, well), total_vol in sorted(required.items()):
        lw = well_to_labware[(slot, well)]
        dead = DEAD_VOLUME.get(lw, 0)
        buffer = total_vol * SAFETY_BUFFER_PCT
        minimum = total_vol + dead + buffer
        log(
            f"{slot:<6} {well:<6} {lw:<45} {total_vol:>12.1f}uL {dead:>9.1f}uL {buffer:>11.1f}uL {minimum:>12.1f}uL"
        )

    log("-" * 110)
    log("Dead Vol    = liquid unreachable at the bottom of each vessel")
    log("Safety +20% = extra buffer on top of total transfer volume")
    log("MINIMUM LOAD = fill each source well to at least this amount before starting")
    log("")

    # ------------------------------------------------------------------ #
    #  Tiprack map                                                         #
    # ------------------------------------------------------------------ #
    tiprack_map = {
        "p20_single_gen2": {
            "standard_20": "opentrons_96_tiprack_20ul",
            "filter_20": "opentrons_96_filtertiprack_20ul",
        },
        "p300_single_gen2": {
            "standard_300": "opentrons_96_tiprack_300ul",
            "filter_300": "opentrons_96_filtertiprack_300ul",
        },
        "p1000_single_gen2": {
            "standard_1000": "opentrons_96_tiprack_1000ul",
            "filter_1000": "opentrons_96_filtertiprack_1000ul",
        },
    }

    # ------------------------------------------------------------------ #
    #  Load labware                                                        #
    # ------------------------------------------------------------------ #
    log("--- Deck Setup ---")
    for line in transfer_info:
        s_lw, s_slot, d_lw, d_slot = line[:2] + line[4:6]
        for slot, lw in zip([s_slot, d_slot], [s_lw, d_lw]):
            if not int(slot) in ctx.loaded_labwares:
                ctx.load_labware(lw.lower(), slot)
                log(f"Loaded labware:  {lw} in slot {slot}")

    # Load tipracks in remaining slots
    tiprack_type = tiprack_map[PIPETTE_TYPE][TIP_TYPE]
    tipracks = []
    for slot in range(1, 12):
        if slot not in ctx.loaded_labwares:
            tipracks.append(ctx.load_labware(tiprack_type, str(slot)))
            log(f"Loaded tiprack:  {tiprack_type} in slot {slot}")

    # Load pipette
    pip = ctx.load_instrument(PIPETTE_TYPE, PIPETTE_MOUNT, tip_racks=tipracks)
    log("")
    log(f"Pipette ready:   {PIPETTE_TYPE} on {PIPETTE_MOUNT} mount")
    log(f"Tips available:  {len(tipracks) * 96}")
    log("")

    # ------------------------------------------------------------------ #
    #  Tip management                                                      #
    # ------------------------------------------------------------------ #
    tip_count = 0
    tip_max = len(tipracks) * 96

    def pick_up():
        nonlocal tip_count
        if tip_count == tip_max:
            ctx.pause("Please refill tipracks before resuming.")
            pip.reset_tipracks()
            tip_count = 0
        pip.pick_up_tip()
        tip_count += 1

    def parse_well(well):
        letter = well[0]
        number = well[1:]
        return letter.upper() + str(int(number))

    # ------------------------------------------------------------------ #
    #  Transfers                                                           #
    # ------------------------------------------------------------------ #
    log("--- Transfers ---")
    transfer_num = 1

    if TIP_REUSE == "never":
        pick_up()

    for line in transfer_info:
        _, s_slot, s_well, h, _, d_slot, d_well, vol = line[:8]
        source = (
            ctx.loaded_labwares[int(s_slot)]
            .wells_by_name()[parse_well(s_well)]
            .bottom(float(h))
        )
        dest = ctx.loaded_labwares[int(d_slot)].wells_by_name()[parse_well(d_well)]
        log(
            f"Transfer {transfer_num}: {float(vol):>6.1f} uL | "
            f"Slot {s_slot} {parse_well(s_well):<3} -> Slot {d_slot} {parse_well(d_well):<3} | "
            f"Aspiration height: {h} mm"
        )
        if TIP_REUSE == "always":
            pick_up()
        pip.transfer(float(vol), source, dest, new_tip="never")
        if TIP_REUSE == "always":
            pip.drop_tip()
        transfer_num += 1

    if pip.has_tip:
        pip.drop_tip()

    log("")
    log("=" * 60)
    log(f"Simulation complete: {transfer_num - 1} transfers logged")
    log(f"Log saved to: {log_path}")
