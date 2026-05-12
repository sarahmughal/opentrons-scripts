from opentrons import protocol_api
import csv
import datetime
import getpass
import os
from collections import defaultdict

metadata = {
    "protocolName": "MOMA RNA/DNA Normalization",
    "author": "Oldham Lab — UCSF",
    "description": "Normalizes RNA and DNA concentrations after AllPrep extraction using Qubit data. "
    "Calculates dilution volumes per section, flags QC failures, and dispenses "
    "into a normalized 96-well plate ready for Smart-seq3xpress and amp-seq library prep.",
}
requirements = {"robotType": "OT-2", "apiLevel": "2.13"}

# ============================================================
#  USER CONFIG — edit these before each run
# ============================================================

# Path to your Qubit export CSV (see format requirements below)
QUBIT_CSV_PATH = "/Users/sarahmughal/Desktop/oldham lab/opentrons scripts/normalization/qubit_data_example.csv"

# Log directory
LOG_DIR = "/Users/sarahmughal/Desktop/oldham lab/opentrons scripts/normalization/normalization_logs"

# Normalization targets (ng)
RNA_TARGET_NG = 20.0  # target ng of RNA per normalized well (10–50 ng per pipeline doc)
DNA_TARGET_NG = 50.0  # target ng of DNA per normalized well

# Final volume in each normalized well (uL)
# OT-2 will add sample + water to reach this volume
RNA_FINAL_VOL_UL = 10.0  # typical Smart-seq3xpress input volume
DNA_FINAL_VOL_UL = 10.0  # typical amp-seq input volume

# QC threshold — exclude sections below this RNA yield (ng)
# Per pipeline doc: "Include sections with Qubit RNA ≥200 ng"
RNA_QC_THRESHOLD_NG = 200.0

# Pipette mounts — p20 for small volumes, p300 for water/larger transfers
P20_MOUNT = "left"
P300_MOUNT = "right"

# ============================================================
#  QUBIT CSV FORMAT
# ============================================================
# Your CSV must have these exact column headers (Qubit export format):
#
#   Well, Sample Name, RNA Concentration (ng/uL), RNA Volume (uL),
#   DNA Concentration (ng/uL), DNA Volume (uL)
#
# Example rows:
#   A1, Section_001, 45.2, 50, 82.3, 50
#   A2, Section_002, 12.8, 50, 55.1, 50   <- will be flagged (RNA <200 ng total)
#   A3, Section_003, 0,    50, 44.0, 50   <- will be flagged (no RNA detected)
#
# Notes:
# - Concentration in ng/uL, volume in uL
# - Total yield = concentration × volume
# - Leave concentration as 0 if below detection
# - Well must match source plate position (A1–H12)
# ============================================================


def run(ctx: protocol_api.ProtocolContext):

    # ------------------------------------------------------------------ #
    #  Logging setup                                                       #
    # ------------------------------------------------------------------ #
    username = getpass.getuser()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"normalization_{username}_{timestamp}.txt")

    def log(message=""):
        print(message)
        with open(log_path, "a") as f:
            f.write(message + "\n")

    log("MOMA Normalization Log")
    log("=" * 65)
    log(f"User:              {username}")
    log(f"Timestamp:         {timestamp}")
    log(f"Protocol:          {metadata['protocolName']}")
    log(f"Qubit CSV:         {QUBIT_CSV_PATH}")
    log(f"RNA target:        {RNA_TARGET_NG} ng in {RNA_FINAL_VOL_UL} uL")
    log(f"DNA target:        {DNA_TARGET_NG} ng in {DNA_FINAL_VOL_UL} uL")
    log(f"RNA QC threshold:  {RNA_QC_THRESHOLD_NG} ng total yield required")
    log("=" * 65)
    log()

    # ------------------------------------------------------------------ #
    #  Read and parse Qubit CSV                                            #
    # ------------------------------------------------------------------ #
    sections = []
    failed_qc = []

    with open(QUBIT_CSV_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            well = row["Well"].strip().upper()
            name = row["Sample Name"].strip()
            rna_conc = float(row["RNA Concentration (ng/uL)"] or 0)
            rna_vol = float(row["RNA Volume (uL)"] or 0)
            dna_conc = float(row["DNA Concentration (ng/uL)"] or 0)
            dna_vol = float(row["DNA Volume (uL)"] or 0)

            rna_total = rna_conc * rna_vol
            dna_total = dna_conc * dna_vol

            # ---- RNA dilution calculation ----
            # C1*V1 = C2*V2  →  V_sample = (target_ng) / (conc ng/uL)
            # V_water = final_vol - V_sample
            if rna_conc > 0 and rna_total >= RNA_QC_THRESHOLD_NG:
                rna_sample_vol = RNA_TARGET_NG / rna_conc
                rna_water_vol = RNA_FINAL_VOL_UL - rna_sample_vol
                rna_pass = True
                if rna_sample_vol > RNA_FINAL_VOL_UL:
                    # concentration too low to hit target in final volume
                    rna_pass = False
                    rna_note = f"FAIL — conc too low: max {rna_conc * RNA_FINAL_VOL_UL:.1f} ng in {RNA_FINAL_VOL_UL} uL"
                    rna_sample_vol = RNA_FINAL_VOL_UL
                    rna_water_vol = 0
                else:
                    rna_note = "PASS"
            else:
                rna_pass = False
                rna_sample_vol = 0
                rna_water_vol = 0
                rna_note = f"FAIL — total yield {rna_total:.0f} ng < {RNA_QC_THRESHOLD_NG} ng threshold"

            # ---- DNA dilution calculation ----
            if dna_conc > 0:
                dna_sample_vol = DNA_TARGET_NG / dna_conc
                dna_water_vol = DNA_FINAL_VOL_UL - dna_sample_vol
                dna_pass = True
                if dna_sample_vol > DNA_FINAL_VOL_UL:
                    dna_pass = False
                    dna_note = f"FAIL — conc too low: max {dna_conc * DNA_FINAL_VOL_UL:.1f} ng in {DNA_FINAL_VOL_UL} uL"
                    dna_sample_vol = DNA_FINAL_VOL_UL
                    dna_water_vol = 0
                else:
                    dna_note = "PASS"
            else:
                dna_pass = False
                dna_sample_vol = 0
                dna_water_vol = 0
                dna_note = "FAIL — no DNA detected"

            section = {
                "well": well,
                "name": name,
                "rna_conc": rna_conc,
                "rna_total": rna_total,
                "rna_sample_vol": round(rna_sample_vol, 2),
                "rna_water_vol": round(rna_water_vol, 2),
                "rna_pass": rna_pass,
                "rna_note": rna_note,
                "dna_conc": dna_conc,
                "dna_total": dna_total,
                "dna_sample_vol": round(dna_sample_vol, 2),
                "dna_water_vol": round(dna_water_vol, 2),
                "dna_pass": dna_pass,
                "dna_note": dna_note,
            }
            sections.append(section)

    # ------------------------------------------------------------------ #
    #  QC report                                                           #
    # ------------------------------------------------------------------ #
    rna_pass_sections = [s for s in sections if s["rna_pass"]]
    dna_pass_sections = [s for s in sections if s["dna_pass"]]

    log("--- QC Report ---")
    log(f"Total sections loaded:    {len(sections)}")
    log(f"RNA pass (≥{RNA_QC_THRESHOLD_NG} ng):       {len(rna_pass_sections)}")
    log(f"RNA fail:                 {len(sections) - len(rna_pass_sections)}")
    log(f"DNA pass:                 {len(dna_pass_sections)}")
    log(f"DNA fail:                 {len(sections) - len(dna_pass_sections)}")
    log()

    log(
        f"{'Well':<6} {'Sample':<15} {'RNA total':>10} {'RNA QC':>10} {'RNA spl':>8} {'RNA H2O':>8} | {'DNA total':>10} {'DNA QC':>10} {'DNA spl':>8} {'DNA H2O':>8}"
    )
    log("-" * 105)
    for s in sections:
        rna_flag = "PASS" if s["rna_pass"] else "FAIL"
        dna_flag = "PASS" if s["dna_pass"] else "FAIL"
        log(
            f"{s['well']:<6} {s['name']:<15} "
            f"{s['rna_total']:>9.0f}ng {rna_flag:>10} {s['rna_sample_vol']:>7.2f}uL {s['rna_water_vol']:>7.2f}uL | "
            f"{s['dna_total']:>9.0f}ng {dna_flag:>10} {s['dna_sample_vol']:>7.2f}uL {s['dna_water_vol']:>7.2f}uL"
        )
    log("-" * 105)
    log()

    # Log any failures with reasons
    failures = [s for s in sections if not s["rna_pass"] or not s["dna_pass"]]
    if failures:
        log("--- Failed Sections (excluded from normalization) ---")
        for s in failures:
            if not s["rna_pass"]:
                log(f"  {s['well']} ({s['name']}) RNA: {s['rna_note']}")
            if not s["dna_pass"]:
                log(f"  {s['well']} ({s['name']}) DNA: {s['dna_note']}")
        log()

    if not rna_pass_sections and not dna_pass_sections:
        raise Exception(
            "No sections passed QC. Check Qubit data and thresholds before proceeding."
        )

    # ------------------------------------------------------------------ #
    #  Deck layout
    #
    #  Slot 1  — Source plate (AllPrep eluate, 96-well deep well)
    #  Slot 2  — RNA normalized plate (NEST 96 PCR, full skirt)
    #  Slot 3  — DNA normalized plate (NEST 96 PCR, full skirt)
    #  Slot 4  — Water reservoir (NEST 12-well reservoir)
    #  Slot 5  — p20 tiprack
    #  Slot 6  — p20 tiprack
    #  Slot 7  — p300 tiprack
    #  Slot 8  — p300 tiprack
    # ------------------------------------------------------------------ #
    log("--- Deck Setup ---")

    source_plate = ctx.load_labware(
        "nest_96_wellplate_2ml_deep", "1", label="AllPrep eluate (source)"
    )
    rna_plate = ctx.load_labware(
        "nest_96_wellplate_100ul_pcr_full_skirt", "2", label="RNA normalized plate"
    )
    dna_plate = ctx.load_labware(
        "nest_96_wellplate_100ul_pcr_full_skirt", "3", label="DNA normalized plate"
    )
    water_res = ctx.load_labware("nest_12_reservoir_15ml", "4", label="Water reservoir")

    tiprack_p20_1 = ctx.load_labware("opentrons_96_tiprack_20ul", "5")
    tiprack_p20_2 = ctx.load_labware("opentrons_96_tiprack_20ul", "6")
    tiprack_p300 = ctx.load_labware("opentrons_96_tiprack_300ul", "7")
    tiprack_p300b = ctx.load_labware("opentrons_96_tiprack_300ul", "8")

    p20 = ctx.load_instrument(
        "p20_single_gen2", P20_MOUNT, tip_racks=[tiprack_p20_1, tiprack_p20_2]
    )
    p300 = ctx.load_instrument(
        "p300_single_gen2", P300_MOUNT, tip_racks=[tiprack_p300, tiprack_p300b]
    )

    water = water_res.wells_by_name()["A1"]

    log("Slot 1: AllPrep eluate source plate (NEST 96 deep well)")
    log("Slot 2: RNA normalized output plate (NEST 96 PCR full skirt)")
    log("Slot 3: DNA normalized output plate (NEST 96 PCR full skirt)")
    log("Slot 4: Water reservoir (NEST 12-well, A1 = nuclease-free water)")
    log("Slot 5–6: p20 tipracks")
    log("Slot 7–8: p300 tipracks")
    log()

    # ------------------------------------------------------------------ #
    #  Helper: choose pipette by volume
    # ------------------------------------------------------------------ #
    def get_pipette(vol):
        if vol <= 20:
            return p20
        else:
            return p300

    def transfer_vol(vol, source, dest, label=""):
        if vol <= 0:
            return
        pip = get_pipette(vol)
        pip.pick_up_tip()
        pip.transfer(vol, source, dest, new_tip="never")
        pip.drop_tip()
        if label:
            log(f"  {label}: {vol:.2f} uL")

    # ------------------------------------------------------------------ #
    #  Step 1 — Add water to RNA normalized plate                         #
    # ------------------------------------------------------------------ #
    log("--- Step 1: Add water to RNA plate ---")
    for s in rna_pass_sections:
        dest = rna_plate.wells_by_name()[s["well"]]
        transfer_vol(
            s["rna_water_vol"],
            water,
            dest,
            label=f"{s['well']} ({s['name']}) RNA water",
        )
    log()

    # ------------------------------------------------------------------ #
    #  Step 2 — Add water to DNA normalized plate                         #
    # ------------------------------------------------------------------ #
    log("--- Step 2: Add water to DNA plate ---")
    for s in dna_pass_sections:
        dest = dna_plate.wells_by_name()[s["well"]]
        transfer_vol(
            s["dna_water_vol"],
            water,
            dest,
            label=f"{s['well']} ({s['name']}) DNA water",
        )
    log()

    # ------------------------------------------------------------------ #
    #  Step 3 — Add RNA sample to RNA normalized plate                    #
    # ------------------------------------------------------------------ #
    log("--- Step 3: Add RNA sample to RNA plate ---")
    for s in rna_pass_sections:
        src = source_plate.wells_by_name()[s["well"]]
        dest = rna_plate.wells_by_name()[s["well"]]
        transfer_vol(
            s["rna_sample_vol"],
            src,
            dest,
            label=f"{s['well']} ({s['name']}) RNA sample",
        )
    log()

    # ------------------------------------------------------------------ #
    #  Step 4 — Add DNA sample to DNA normalized plate                    #
    # ------------------------------------------------------------------ #
    log("--- Step 4: Add DNA sample to DNA plate ---")
    for s in dna_pass_sections:
        src = source_plate.wells_by_name()[s["well"]]
        dest = dna_plate.wells_by_name()[s["well"]]
        transfer_vol(
            s["dna_sample_vol"],
            src,
            dest,
            label=f"{s['well']} ({s['name']}) DNA sample",
        )
    log()

    # ------------------------------------------------------------------ #
    #  Summary                                                             #
    # ------------------------------------------------------------------ #
    log("=" * 65)
    log(f"Normalization complete")
    log(f"RNA sections normalized: {len(rna_pass_sections)} / {len(sections)}")
    log(f"DNA sections normalized: {len(dna_pass_sections)} / {len(sections)}")
    log(
        f"RNA output plate:        Slot 2 — {RNA_TARGET_NG} ng in {RNA_FINAL_VOL_UL} uL per well"
    )
    log(
        f"DNA output plate:        Slot 3 — {DNA_TARGET_NG} ng in {DNA_FINAL_VOL_UL} uL per well"
    )
    log(f"Log saved to:            {log_path}")
