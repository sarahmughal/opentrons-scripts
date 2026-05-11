# OT-2 Cherrypicking Protocol

**Author:** Sarah Mughal — Oldham Lab  
**Robot:** Opentrons OT-2  
**API Level:** 2.13

---

## Files

| File | Purpose |
|---|---|
| `cherrypicking.py` | Main protocol script |
| `cherrypicking_test.csv` | Test transfer list |
| `simulation_logs/` | Auto-generated logs from each simulation run |

---

## How to Test the Script (Without a Robot)

### Step 1 — Install the Opentrons package
Open Terminal and run:
```bash
pip install opentrons
```

### Step 2 — Navigate to the script folder
```bash
cd '/Users/sarahmughal/Desktop/oldham lab/opentrons scripts/cherrypicking'
```

### Step 3 — Run the simulator
```bash
opentrons_simulate cherrypicking.py
```

### Step 4 — Check the output
The simulator will print to Terminal:
- A **pre-run volume check table** showing the minimum amount of liquid to load in each source well before starting
- A **deck setup summary** showing which labware and tipracks loaded into which slots
- A **step-by-step transfer log** of every aspiration and dispense

A timestamped log file will also be saved automatically to:
```
simulation_logs/simulation_<username>_<timestamp>.txt
```

### Step 5 — Upload to the Opentrons App for a visual preview
1. Download the Opentrons App from https://opentrons.com/ot-app
2. Click **Protocols** → **Import**
3. Select `cherrypicking.py`
4. The app will show a visual deck map with all labware in their slots and flag any errors

---

## How to Edit the Script for Your Own Experiment

Open `cherrypicking.py` and edit the config block at the top of the file. You should not need to touch anything else.

```python
# Path to your transfer CSV file
TRANSFER_CSV_PATH = '/path/to/your/transfers.csv'

# Pipette options: 'p20_single_gen2', 'p300_single_gen2', 'p1000_single_gen2'
PIPETTE_TYPE = 'p300_single_gen2'

# Which mount the pipette is on: 'left' or 'right'
PIPETTE_MOUNT = 'right'

# Tip type options: 'standard_20/300/1000' or 'filter_20/300/1000'
TIP_TYPE = 'standard_300'

# 'always' = new tip for every transfer
# 'never'  = reuse one tip throughout the entire run
TIP_REUSE = 'always'
```

---

## How to Format Your Transfer CSV

Save your transfer list as a `.csv` file with exactly these column headers:

```
Source Labware,Source Slot,Source Well,Source Aspiration Height Above Bottom (in mm),Dest Labware,Dest Slot,Dest Well,Volume (in ul)
```

Example rows:
```
nest_96_wellplate_200ul_flat,1,A1,1,nest_96_wellplate_100ul_pcr_full_skirt,4,B3,50
nest_12_reservoir_15ml,2,A1,3,nest_96_wellplate_2ml_deep,5,H12,100
```

### CSV Rules
- **Labware names** must exactly match Opentrons definitions (all lowercase)
- **Slot numbers** must be between 1 and 11
- **Each slot can only hold one labware** — slots not used by labware are auto-filled with tipracks
- **Volumes must be within your pipette's range:**

| Pipette | Min Volume | Max Volume |
|---|---|---|
| p20_single_gen2 | 1 µL | 20 µL |
| p300_single_gen2 | 20 µL | 300 µL |
| p1000_single_gen2 | 100 µL | 1000 µL |

### Aspiration Height Guide
| Labware | Recommended Height |
|---|---|
| Standard 96-well plate | 1 mm |
| Deep well plate | 2–5 mm |
| 12-well reservoir | 3–5 mm |
| 1-well reservoir | 5–10 mm |

### Common OT-2 Labware Names
| Labware | Definition Name |
|---|---|
| NEST 96 flat well plate | `nest_96_wellplate_200ul_flat` |
| NEST 96 PCR plate | `nest_96_wellplate_100ul_pcr_full_skirt` |
| NEST 96 deep well plate | `nest_96_wellplate_2ml_deep` |
| NEST 12-well reservoir | `nest_12_reservoir_15ml` |
| NEST 1-well reservoir | `nest_1_reservoir_195ml` |
| Agilent 1-well reservoir | `agilent_1_reservoir_290ml` |

---

## Important OT-2 Limitations to Know

**No liquid detection** — the robot cannot sense liquid levels. Always load more than the MINIMUM LOAD shown in the pre-run volume check. The script calculates minimum load as:

```
MINIMUM LOAD = total transfer volume + dead volume + 20% safety buffer
```

**No error recovery** — if the robot aspirates air because a well ran dry, it will not pause or warn you. Always visually check source wells are adequately filled before starting.

**Pipette volume range** — using a pipette outside its recommended range produces inaccurate transfers. Match your pipette to your volume range.

---

## Updating Dead Volume Values

If you are using different labware, you can update the dead volume estimates in `cherrypicking.py`:

```python
DEAD_VOLUME = {
    'nest_96_wellplate_200ul_flat':           5,
    'nest_96_wellplate_100ul_pcr_full_skirt': 5,
    'nest_96_wellplate_2ml_deep':             50,
    'nest_12_reservoir_15ml':                 200,
    'nest_1_reservoir_195ml':                 1000,
    'agilent_1_reservoir_290ml':              1000,
}

SAFETY_BUFFER_PCT = 0.20  # change to 0.10 for 10%, 0.25 for 25%, etc.
```
