# Notes on This Project

A document providing a brief overview of my approach to the analysis, including the methodology, data integrity practices, reproducibility of the case study/analysis, and any subsequent issues which were resolved during the case study.

## Why this project has two reports

The original dataset was structured in two separate folders containing the data for two months (March–April & April–May). I made the decision to publish the isolated analysis of Month 1 along with the initially intended combined version to provide a more holistic view of the progression of trends in the data. We can observe the key findings of the study persist throughout the two months with this structure.

## Data integrity issues found and resolved

### Boundary day conflict

Due to the structure of the dataset and the April 12th crossover date, there were conflicting datapoints for the same day in datasets for both months. This issue was resolved by identifying a break pattern (same cutoff time across all datasets) and finding truncated data in the daily activity, hourly steps, and heart rate datasets for this day in one month, and a full day on the other. The device appeared to stop syncing on one dataset, while the other captured the full day.

### Duplicate weight entry

The overlap also prompted duplicate entries in the weight logs assigned to the same unique log ID, which was resolved by filtering by log IDs instead of the dates.

### Missing combined file & filename collisions

Due to the structure of the original dataset (divided into two separate folders for two months) and identical filenames, one month's merged file was overwritten during the cleaning and analysis. I verified every file's identity before trusting it, and that's how I caught the problem before it could contaminate any analysis. This was resolved by downloading the files again, and temporarily renaming them so that I could verify that both folders contained distinct datasets corresponding to the appropriate months — highlighting the importance of a more organised and clean approach to analysis with similar large datasets.

### Sparse metric coverage

There were some reliability issues with certain aspects of the analysis, as datasets for heart rate and weight weren't complete, with participants not consistently logging data points across the sample and time frame. Well under half the users had logged data for these observation metrics, most of which was captured inconsistently, leaving gaps in the analysis.

## Reproducing this analysis

```bash
pip install pandas matplotlib numpy
python scripts/analysis_month1.py
python scripts/analysis_combined.py
```

Raw data isn't included in this repo (see `data/README.md` for the required file layout and sourcing from Kaggle). Both scripts print their own summary statistics on completion — compare against the numbers in each report to confirm a clean run.

## Data source & license

[FitBit Fitness Tracker Data](https://www.kaggle.com/datasets/arashnic/fitbit), made available via Mobius under CC0: Public Domain. Not redistributed in this repository; see `data/README.md`.

This project's own code and written analysis are provided under the MIT License (see `LICENSE`).
