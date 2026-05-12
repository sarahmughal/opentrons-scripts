# MOMA RNA/DNA Normalization — Instructions

**Lab:** Oldham Lab, UCSF  
**Robot:** Opentrons OT-2  
**Script:** `normalization.py`  
**Purpose:** Normalize RNA and DNA concentrations from AllPrep co-extractions into ready-to-use plates for Smart-seq3xpress (RNA) and amp-seq (DNA) library prep.

---

## Files

| File | Purpose |
|---|---|
| `normalization.py` | Main normalization script |
| `qubit_data_example.csv` | Example Qubit input — use as a template |
| `normalization_logs/` | Auto-generated timestamped logs per run |

---

## Before You Start

**What you need:**
- Qubit fluorometric quantification data for all sections (RNA and DNA, ng/µL + volume)
- AllPrep eluate plate loaded on the OT-2 deck (slot 1)
- Two fresh NEST 96 PCR plates for RNA and DNA output (slots 2 and 3)
- Nuclease-free water in column A1 of a NEST 12-well reservoir (slot 4)
- p20 and p300 pipettes mounted (left and right)

**Do not use Nanodrop for input concentrations.** Qubit fluorometric quantification is required — Nanodrop overestimates yield due to free nucleotides and is not suitable for normalizing library prep inputs.

**Individual QC is mandatory for every section.** RNA yield cannot be reliably predicted from section mass alone (R = 0.468 in pilot data). Every section must have its own Qubit measurement before normalization.

---

## Deck Layout

```
[ Slot 7  p300 tips ] [ Slot 8  p300 tips ] [ Slot 9  empty     ]
[ Slot 4  Water res ] [ Slot 5  p20 tips  ] [ Slot 6  p20 tips  ]
[ Slot 1  Source    ] [ Slot 2  RNA plate ] [ Slot 3  DNA plate ]
                                              [ Slot 12 Trash     ]
```

| Slot | Labware | Notes |
|---|---|---|
| 1 | NEST 96 deep well (AllPrep eluate) | Source plate from QiaCube extraction |
| 2 | NEST 96 PCR full skirt | RNA normalized output — goes to Smart-seq3xpress |
| 3 | NEST 96 PCR full skirt | DNA normalized output — goes to amp-seq |
| 4 | NEST 12-well reservoir | Column A1 = nuclease-free water |
| 5–6 | p20 tipracks | For small-volume sample transfers |
| 7–8 | p300 tipracks | For water additions |
| 12 | Fixed trash | Built-in, do not place labware here |

---

## Qubit CSV Format

Export your Qubit data as a CSV with exactly these column headers:

```
Well, Sample Name, RNA Concentration (ng/uL), RNA Volume (uL), DNA Concentration (ng/uL), DNA Volume (uL)
```

- Concentration in **ng/µL**, volume in **µL**
- Total yield is calculated as concentration × volume
- Enter `0` for concentration if the sample is below detection
- Well names must match the source plate positions exactly (A1–H12)

See `qubit_data_example.csv` for a working template.

---

## Configurable Parameters

Open `normalization.py` and edit the config block at the top:

```python
RNA_TARGET_NG        = 20.0   # ng of RNA per normalized well (10–50 ng recommended)
DNA_TARGET_NG        = 50.0   # ng of DNA per normalized well (see DNA section below)
RNA_FINAL_VOL_UL     = 10.0   # final volume in RNA plate (match Smart-seq3xpress input)
DNA_FINAL_VOL_UL     = 10.0   # final volume in DNA plate (match amp-seq input)
RNA_QC_THRESHOLD_NG  = 200.0  # sections below this total RNA yield are excluded
```

---

## RNA Normalization — Context

Smart-seq3xpress requires a consistent RNA input for comparable library complexity across sections. The pipeline targets **10–50 ng total RNA** per well, with a recommended working target of **20 ng** for most runs.

Sections from plane 2 of a tumor commonly yield lower RNA (median 466 ng vs. 1,210 ng for plane 1) due to smaller cross-sectional area after 90° rotation — this is a biological effect, not a technical failure. RIN remains high across both planes and these sections are still usable if total yield meets the 200 ng threshold. The script will flag and exclude any section that falls below threshold and log the reason.

If a section has adequate total RNA but the concentration is too low to reach the target in the final volume (i.e., even transferring the full final volume would undershoot), the script flags it as a failure and logs the maximum achievable input. These sections should be reviewed — options include re-extraction, thicker sectioning on the next run (~150 µm for low-yield planes), or allocating them to amp-seq only (DNA-only use).

---

## DNA Normalization — Context

DNA from AllPrep co-extractions is used for amplicon sequencing (amp-seq), which requires deep sequencing of somatic mutations identified by WES to obtain precise variant allele frequencies (VAFs) across all sections for clonal phylogeny reconstruction.

**Why DNA normalization matters for amp-seq:**

Amp-seq targets >10,000× read depth per mutation per section across up to 50 amplicons. Unequal DNA input between sections directly causes unequal library complexity and unequal sequencing representation after pooling. Sections with higher DNA input will dominate the pool and deplete reads from lower-input sections, making VAF estimates unreliable in underrepresented sections. Normalizing DNA input before PCR is therefore critical for confident VAF estimation across all 96 sections.

**Recommended DNA input:** 50 ng per section. In Case 2, DNA yields were uniformly high (median 914 ng; only 2 of 86 sections had DNA <500 ng; none had <250 ng). The 50 ng target is conservative — most sections will have substantial DNA remaining after normalization, which can be stored at -80°C as backup.

**DNA QC threshold:** The script does not apply a minimum total yield threshold for DNA the way it does for RNA (no hard 200 ng cutoff), because DNA yield is almost never the limiting factor. However, it will flag wells where the concentration is too low to deliver 50 ng in the final volume and log the maximum achievable input. In practice this should be rare — if it occurs, check extraction efficiency and section thickness.

**Primer design dependency:** DNA normalization happens before amp-seq primer design is complete. Normalized DNA plates can be sealed and stored at -80°C for weeks to months while WES is processed, mutations are called, and amplicon primers are ordered and validated. Sections are stable at -80°C during this interval.

---

## How to Test Without a Robot

```bash
# Install opentrons if not already installed
pip install opentrons

# Navigate to your script folder
cd '/Users/sarahmughal/Desktop/oldham lab/opentrons scripts/normalization'

# Run the simulator
opentrons_simulate normalization.py
```

The simulator will print a full step-by-step runlog and save a timestamped log file to `normalization_logs/`. No robot connection required.

---

## What the Log File Contains

Each run produces a log file named:
```
normalization_<username>_<timestamp>.txt
```

The log includes:
- Run metadata (user, timestamp, targets, QC threshold)
- Per-section QC table with total yields, pass/fail status, and calculated volumes
- List of failed sections with specific failure reasons
- Step-by-step transfer log (water additions, then sample additions)
- Final summary of sections normalized

---

## Troubleshooting

| Issue | Likely cause | Fix |
|---|---|---|
| Many RNA failures | Plane 2 low-yield sections | Lower `RNA_QC_THRESHOLD_NG` or cut thicker sections (~150 µm) next run |
| Sample volume > final volume | Concentration too low to hit target | Lower `RNA_TARGET_NG` or accept max available input |
| Water volume is negative | Target concentration higher than sample concentration | Not possible — check Qubit values and target settings |
| Script errors on CSV read | Column header mismatch | Check headers match exactly, including units in parentheses |
