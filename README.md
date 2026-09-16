# Raw Data

Raw CSVs are not committed to this repo (large files, and best kept at the
source for licensing clarity).

**Source:** [FitBit Fitness Tracker Data](https://www.kaggle.com/datasets/arashnic/fitbit)
(CC0: Public Domain, via Mobius)

## Setup

The Kaggle download splits into two monthly exports with several
identically-named files (`dailyActivity_merged.csv`, `hourlySteps_merged.csv`,
`heartrate_seconds_merged.csv`, `weightLogInfo_merged.csv`,
`minuteSleep_merged.csv` all appear in both). Keep them in **separate
subfolders** as below, or one month's files will silently overwrite the
other's:

```
data/raw/
├── mar_apr/    ← March 12 - April 12, 2016 export
└── apr_may/    ← April 12 - May 12, 2016 export
```

## Required files per folder

**`data/raw/mar_apr/`** (5 files):
`dailyActivity_merged.csv`, `minuteSleep_merged.csv`, `hourlySteps_merged.csv`,
`heartrate_seconds_merged.csv`, `weightLogInfo_merged.csv`

**`data/raw/apr_may/`** (5 files):
`dailyActivity_merged.csv`, `sleepDay_merged.csv`, `hourlySteps_merged.csv`,
`heartrate_seconds_merged.csv`, `weightLogInfo_merged.csv`

Note: if downloading `dailyActivity_merged.csv` from Kaggle's in-browser
preview/table view rather than the main dataset download button, you may get
a partial-column export (filename often includes "-selected-columns"). Use
the main "Download" button instead to get the full 15-column file. If only
the partial version is available, the script falls back to reconstructing
the same data from `dailySteps_merged.csv` + `dailyCalories_merged.csv` +
`dailyIntensities_merged.csv` — verified byte-exact against the real file
on every column.

## Known data quality issues (already handled by the scripts)

- **April 12 boundary conflict**: both exports include April 12 with
  conflicting values — the March-April file's version is a partial/truncated
  day (device-sync cutoff), the April-May file's version is complete. Scripts
  drop the partial version.
- **Duplicate weight log entries**: 2 exact duplicate entries (same `LogId`)
  appear in both months' weight files on the boundary day. Deduplicated by
  `LogId`.
- **No combined April-May `dailyActivity_merged.csv`**: use the direct file if you
  have it (confirmed byte-exact match on every column against the reconstruction
  below). If unavailable, reconstruct from `dailySteps_merged.csv` +
  `dailyCalories_merged.csv` + `dailyIntensities_merged.csv` instead — the script
  handles both automatically depending on which file is present.
