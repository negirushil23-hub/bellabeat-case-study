"""
Bellabeat Case Study — Combined 2-Month Smart Device Usage Analysis
=====================================================================
Author: [Your Name]
Dataset: FitBit Fitness Tracker Data (CC0: Public Domain), via Mobius on Kaggle
          https://www.kaggle.com/datasets/arashnic/fitbit

This dataset ships as TWO separate monthly exports (March 12 - April 12,
2016 and April 12 - May 12, 2016) with several files sharing IDENTICAL
NAMES across both exports (dailyActivity_merged.csv, hourlySteps_merged.csv,
heartrate_seconds_merged.csv, weightLogInfo_merged.csv, minuteSleep_merged.csv
all appear in both). Keep the two exports in SEPARATE folders when you
download them (see --mar-apr-dir / --apr-may-dir below) or one month's
files will silently overwrite the other's before you ever get to combine
them.

This script:
1. Loads both months' daily activity, reconciling the fact that the two
   exports OVERLAP on April 12 with conflicting values (the March-April
   file's April 12 is a partial/truncated day cut off by a device-sync
   boundary; the April-May file's April 12 is complete). The partial
   version is dropped.
2. Same boundary-day fix applied to hourly steps and heart rate, which
   show the identical truncation pattern.
3. Combines sleep from two different source formats: minute-level logs
   for March-April (no official rollup was included in that export) and
   the official sleepDay_merged file for April-May.
4. Combines weight logs, which have their own quirk: the March-April and
   April-May weightLogInfo files were both missing a header row - it had
   been relocated to the LAST line of the file instead of the first - and
   share 2 exact duplicate log entries (same LogId) on the boundary day.
5. Segments users, computes correlations, and generates all 8 report charts.

Run:
    python analysis_combined.py \
        --mar-apr-dir ./data/raw/mar_apr \
        --apr-may-dir ./data/raw/apr_may \
        --out-dir ./reports/combined_mar_may/images
"""

import argparse
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
COLORS = {
    "teal": "#1F7A6C", "coral": "#E76F51", "navy": "#264653",
    "gold": "#E9C46A", "grey": "#8D99AE",
}
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.spines.top": False,
    "axes.spines.right": False,
})
DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BOUNDARY_DATE = "2016-04-12"  # the day both monthly exports overlap on


# ---------------------------------------------------------------------------
# Loaders — each combines its two source files and resolves the boundary-day
# conflict / file-specific data quality issue documented in the module
# docstring above.
# ---------------------------------------------------------------------------

def load_combined_daily_activity(mar_apr_dir, apr_may_dir):
    """Daily steps/calories/activity minutes, both months combined.

    Both months use a direct dailyActivity_merged.csv when present. If
    April-May's combined file isn't available, it's reconstructed from its
    three component files instead (dailySteps/dailyCalories/dailyIntensities
    _merged.csv) -- verified byte-exact against the real combined file on
    every column (TotalSteps, Calories, all four activity-minute columns,
    all four distance columns) once both became available for comparison.
    """
    month1 = pd.read_csv(os.path.join(mar_apr_dir, "dailyActivity_merged.csv"))
    month1["ActivityDate"] = pd.to_datetime(month1["ActivityDate"], format="%m/%d/%Y")
    month1 = month1[month1["ActivityDate"] < pd.Timestamp(BOUNDARY_DATE)]  # drop partial boundary day

    direct_path = os.path.join(apr_may_dir, "dailyActivity_merged.csv")
    if os.path.exists(direct_path):
        month2 = pd.read_csv(direct_path)
        month2["ActivityDate"] = pd.to_datetime(month2["ActivityDate"], format="%m/%d/%Y")
    else:
        steps = pd.read_csv(os.path.join(apr_may_dir, "dailySteps_merged.csv"))
        cal = pd.read_csv(os.path.join(apr_may_dir, "dailyCalories_merged.csv"))
        inten = pd.read_csv(os.path.join(apr_may_dir, "dailyIntensities_merged.csv"))
        for df in (steps, cal, inten):
            df["ActivityDay"] = pd.to_datetime(df["ActivityDay"], format="%m/%d/%Y")
        month2 = steps.merge(cal, on=["Id", "ActivityDay"]).merge(inten, on=["Id", "ActivityDay"])
        month2 = month2.rename(columns={"StepTotal": "TotalSteps", "ActivityDay": "ActivityDate"})
        for col in ["TotalDistance", "TrackerDistance", "LoggedActivitiesDistance"]:
            month2[col] = pd.NA

    common_cols = [
        "Id", "ActivityDate", "TotalSteps", "TotalDistance", "TrackerDistance",
        "LoggedActivitiesDistance", "VeryActiveDistance", "ModeratelyActiveDistance",
        "LightActiveDistance", "SedentaryActiveDistance", "VeryActiveMinutes",
        "FairlyActiveMinutes", "LightlyActiveMinutes", "SedentaryMinutes", "Calories",
    ]
    combined = pd.concat([month1[common_cols], month2[common_cols]], ignore_index=True)
    combined = combined.sort_values(["Id", "ActivityDate"]).reset_index(drop=True)
    assert combined.duplicated(subset=["Id", "ActivityDate"]).sum() == 0, "Unresolved duplicate Id+Date pairs"

    combined["Weekday"] = combined["ActivityDate"].dt.day_name()
    combined["IsWeekend"] = combined["ActivityDate"].dt.dayofweek >= 5
    combined["TotalActiveMinutes"] = (
        combined["VeryActiveMinutes"] + combined["FairlyActiveMinutes"] + combined["LightlyActiveMinutes"]
    )
    return combined


def load_combined_sleep(mar_apr_dir, apr_may_dir):
    """Daily sleep summary, both months combined, from two different source formats.

    March-April only has minute-level sleep logs, so it's aggregated
    manually (session -> day). April-May has the official pre-aggregated
    sleepDay_merged file, which is preferred whenever both exist — it
    correctly deduplicates overlapping sleep/nap sessions that a manual
    reconstruction can slightly over-count. On the one overlapping
    boundary night, the official (month 2) version is kept.
    """
    ms = pd.read_csv(os.path.join(mar_apr_dir, "minuteSleep_merged.csv"))
    ms["date_parsed"] = pd.to_datetime(ms["date"], format="%m/%d/%Y %I:%M:%S %p")
    ms["SleepDate"] = ms["date_parsed"].dt.normalize()
    per_log = ms.groupby(["Id", "SleepDate", "logId"]).agg(
        TotalMinutesRecorded=("value", "count"),
        TotalMinutesAsleep=("value", lambda x: (x == 1).sum()),
    ).reset_index()
    month1 = per_log.groupby(["Id", "SleepDate"]).agg(
        TotalMinutesAsleep=("TotalMinutesAsleep", "sum"),
        TotalTimeInBed=("TotalMinutesRecorded", "sum"),
    ).reset_index()
    month1 = month1[month1["TotalTimeInBed"] > 60]  # drop short-nap noise
    month1["SleepEfficiency"] = (month1["TotalMinutesAsleep"] / month1["TotalTimeInBed"] * 100).round(1)

    sd = pd.read_csv(os.path.join(apr_may_dir, "sleepDay_merged.csv"))
    sd["SleepDay"] = pd.to_datetime(sd["SleepDay"], format="%m/%d/%Y %I:%M:%S %p").dt.normalize()
    month2 = sd.groupby(["Id", "SleepDay"]).agg(
        TotalMinutesAsleep=("TotalMinutesAsleep", "sum"),
        TotalTimeInBed=("TotalTimeInBed", "sum"),
    ).reset_index().rename(columns={"SleepDay": "SleepDate"})
    month2["SleepEfficiency"] = (month2["TotalMinutesAsleep"] / month2["TotalTimeInBed"] * 100).round(1)

    combined = pd.concat([month1, month2], ignore_index=True)
    # Boundary night: keep the official (month2, appears last) version
    combined = combined.drop_duplicates(subset=["Id", "SleepDate"], keep="last").reset_index(drop=True)
    return combined


def load_combined_hourly_steps(mar_apr_dir, apr_may_dir):
    """Hourly step totals, both months combined."""
    month1 = pd.read_csv(os.path.join(mar_apr_dir, "hourlySteps_merged.csv"))
    month1["ActivityHour"] = pd.to_datetime(month1["ActivityHour"], format="%m/%d/%Y %I:%M:%S %p")
    month1 = month1[month1["ActivityHour"].dt.date < pd.Timestamp(BOUNDARY_DATE).date()]  # drop partial day

    month2 = pd.read_csv(os.path.join(apr_may_dir, "hourlySteps_merged.csv"))
    month2["ActivityHour"] = pd.to_datetime(month2["ActivityHour"], format="%m/%d/%Y %I:%M:%S %p")

    combined = pd.concat([month1, month2], ignore_index=True)
    assert combined.duplicated(subset=["Id", "ActivityHour"]).sum() == 0
    return combined


def _read_headerless_or_normal(path, expected_cols):
    """Some source files in this dataset are missing their header row at
    the TOP — it was found relocated to the LAST line instead. Detect and
    handle both cases transparently."""
    with open(path) as f:
        first_line = f.readline().strip()
    if first_line.replace(" ", "") == ",".join(expected_cols).replace(" ", ""):
        return pd.read_csv(path)
    # header missing from top; assume it's a data row, and drop a
    # trailing header-as-data row if present at the end of the file
    df = pd.read_csv(path, header=None, names=expected_cols, skipfooter=1, engine="python")
    return df


def load_combined_heartrate(mar_apr_dir, apr_may_dir):
    """Second-level heart rate, both months combined.

    The March-April source file for this dataset was found with its
    header row relocated to the last line of the file instead of the
    first — handled transparently by _read_headerless_or_normal.
    """
    cols = ["Id", "Time", "Value"]
    month1 = _read_headerless_or_normal(os.path.join(mar_apr_dir, "heartrate_seconds_merged.csv"), cols)
    month1["Time"] = pd.to_datetime(month1["Time"], format="%m/%d/%Y %I:%M:%S %p")
    month1 = month1[month1["Time"].dt.date < pd.Timestamp(BOUNDARY_DATE).date()]  # drop partial day

    month2 = _read_headerless_or_normal(os.path.join(apr_may_dir, "heartrate_seconds_merged.csv"), cols)
    month2["Time"] = pd.to_datetime(month2["Time"], format="%m/%d/%Y %I:%M:%S %p")

    combined = pd.concat([month1, month2], ignore_index=True)
    assert combined.duplicated(subset=["Id", "Time"]).sum() == 0
    return combined


def load_combined_weight(mar_apr_dir, apr_may_dir):
    """Manual/automatic weight logs, both months combined.

    Same relocated-header issue as heart rate. Additionally: the two
    source files share 2 EXACT duplicate log entries (same LogId, not
    just the same date) on the boundary day — deduplicated by LogId.
    """
    cols = ["Id", "Date", "WeightKg", "WeightPounds", "Fat", "BMI", "IsManualReport", "LogId"]
    month1 = _read_headerless_or_normal(os.path.join(mar_apr_dir, "weightLogInfo_merged.csv"), cols)
    month2 = _read_headerless_or_normal(os.path.join(apr_may_dir, "weightLogInfo_merged.csv"), cols)
    for df in (month1, month2):
        df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y %I:%M:%S %p")

    combined = pd.concat([month1, month2], ignore_index=True).drop_duplicates(subset=["LogId"])
    combined = combined.sort_values(["Id", "Date"]).reset_index(drop=True)
    return combined


# ---------------------------------------------------------------------------
# Segmentation / classification
# ---------------------------------------------------------------------------

def classify_activity(avg_steps):
    if avg_steps < 5000:
        return "Sedentary"
    elif avg_steps < 7500:
        return "Lightly Active"
    elif avg_steps < 10000:
        return "Moderately Active"
    return "Very Active"


def user_segmentation(da):
    user_avg = da.groupby("Id").agg(
        AvgSteps=("TotalSteps", "mean"),
        AvgSedentaryMin=("SedentaryMinutes", "mean"),
        AvgCalories=("Calories", "mean"),
        AvgVeryActiveMin=("VeryActiveMinutes", "mean"),
        DaysLogged=("ActivityDate", "count"),
    ).reset_index()
    user_avg["ActivityClass"] = user_avg["AvgSteps"].apply(classify_activity)
    total_days = da["ActivityDate"].nunique()
    user_avg["LoggingRate"] = (user_avg["DaysLogged"] / total_days * 100).clip(upper=100)
    return user_avg


def hourly_patterns(hourly_df):
    hourly_df = hourly_df.copy()
    hourly_df["Hour"] = hourly_df["ActivityHour"].dt.hour
    hourly_df["Date"] = hourly_df["ActivityHour"].dt.date
    hourly_avg = hourly_df.groupby("Hour")["StepTotal"].mean().reset_index()

    daily_from_hourly = hourly_df.groupby(["Id", "Date"])["StepTotal"].sum().reset_index()
    daily_from_hourly["Date"] = pd.to_datetime(daily_from_hourly["Date"])
    daily_from_hourly["Weekday"] = daily_from_hourly["Date"].dt.day_name()
    dow_avg = daily_from_hourly.groupby("Weekday")["StepTotal"].mean().reindex(DOW_ORDER)
    return hourly_avg, dow_avg


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def chart_hourly_steps(hourly_avg, out_dir):
    c = COLORS
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(hourly_avg["Hour"], hourly_avg["StepTotal"], color=c["teal"], linewidth=2.5, marker="o", markersize=4)
    ax.fill_between(hourly_avg["Hour"], hourly_avg["StepTotal"], color=c["teal"], alpha=0.12)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlabel("Hour of Day"); ax.set_ylabel("Average Steps")
    ax.set_title("Average Steps by Hour of Day (Combined 2-Month Data)", fontsize=12.5, fontweight="bold", loc="left")
    plt.tight_layout(); fig.savefig(os.path.join(out_dir, "01_hourly_steps.png"), dpi=160); plt.close(fig)


def chart_dow_steps(dow_avg, out_dir):
    c = COLORS
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = [c["coral"] if d == dow_avg.idxmin() else (c["gold"] if d == dow_avg.idxmax() else c["teal"]) for d in dow_avg.index]
    ax.bar(dow_avg.index, dow_avg.values, color=colors)
    ax.axhline(7500, color=c["navy"], linestyle="--", linewidth=1, alpha=0.6)
    ax.set_ylabel("Average Total Steps")
    ax.set_title("Average Daily Steps by Day of Week (Combined 2-Month Data)", fontsize=12.5, fontweight="bold", loc="left")
    plt.xticks(rotation=20)
    plt.tight_layout(); fig.savefig(os.path.join(out_dir, "02_dow_steps.png"), dpi=160); plt.close(fig)


def chart_activity_minutes(da, out_dir):
    c = COLORS
    avg_min = {
        "Sedentary": da["SedentaryMinutes"].mean(), "Lightly Active": da["LightlyActiveMinutes"].mean(),
        "Fairly Active": da["FairlyActiveMinutes"].mean(), "Very Active": da["VeryActiveMinutes"].mean(),
    }
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.pie(list(avg_min.values()), colors=[c["grey"], c["teal"], c["gold"], c["coral"]],
           autopct=lambda p: f"{p:.0f}%" if p > 3 else "", startangle=90,
           wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 2})
    ax.set_title("Average Daily Minutes by Activity Level (Combined 2-Month Data)", fontsize=12.5, fontweight="bold", loc="left")
    ax.legend([f"{k} ({v:.0f} min)" for k, v in avg_min.items()], loc="center", frameon=False, fontsize=9.5)
    plt.tight_layout(); fig.savefig(os.path.join(out_dir, "03_activity_minutes.png"), dpi=160); plt.close(fig)


def chart_user_segments(user_avg, out_dir):
    c = COLORS
    order = ["Sedentary", "Lightly Active", "Moderately Active", "Very Active"]
    counts = user_avg["ActivityClass"].value_counts().reindex(order)
    n = len(user_avg)
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    bars = ax.barh(order, counts.values, color=[c["grey"], c["gold"], c["teal"], c["coral"]])
    for i, v in enumerate(counts.values):
        ax.text(v + 0.3, i, f"{v} users ({v/n*100:.0f}%)", va="center", fontsize=9.5)
    ax.set_xlabel("Number of Users"); ax.set_xlim(0, max(counts.values) + 5)
    ax.set_title(f"User Segmentation by Average Daily Steps ({n} users, 2 months)", fontsize=12.5, fontweight="bold", loc="left")
    plt.tight_layout(); fig.savefig(os.path.join(out_dir, "04_user_segments.png"), dpi=160); plt.close(fig)


def chart_sedentary_vs_sleep(merged, out_dir):
    c = COLORS
    m = merged.dropna(subset=["TotalMinutesAsleep"])
    fig, ax = plt.subplots(figsize=(7.5, 5))
    ax.scatter(m["SedentaryMinutes"] / 60, m["TotalMinutesAsleep"] / 60, alpha=0.4, color=c["teal"], s=30)
    z = np.polyfit(m["SedentaryMinutes"], m["TotalMinutesAsleep"], 1)
    xs = np.linspace(m["SedentaryMinutes"].min(), m["SedentaryMinutes"].max(), 50)
    ax.plot(xs / 60, np.polyval(z, xs) / 60, color=c["coral"], linewidth=2, linestyle="--")
    r = m[["SedentaryMinutes", "TotalMinutesAsleep"]].corr().iloc[0, 1]
    ax.set_xlabel("Sedentary Hours (per day)"); ax.set_ylabel("Sleep Duration (hours)")
    ax.set_title("Sedentary Time vs. Sleep Duration (Combined 2-Month Data)", fontsize=12.5, fontweight="bold", loc="left")
    ax.text(0.03, 0.05, f"r = {r:.2f}  (n={len(m)})", transform=ax.transAxes, fontsize=10, color=c["navy"], fontweight="bold")
    plt.tight_layout(); fig.savefig(os.path.join(out_dir, "05_sedentary_sleep.png"), dpi=160); plt.close(fig)


def chart_sleep_distribution(sleep, out_dir):
    c = COLORS
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(sleep["TotalMinutesAsleep"] / 60, bins=24, color=c["teal"], alpha=0.85, edgecolor="white")
    ax.axvline(7, color=c["coral"], linestyle="--", linewidth=2)
    ax.text(7.1, ax.get_ylim()[1] * 0.9, "Recommended\nminimum (7h)", color=c["coral"], fontsize=9)
    ax.set_xlabel("Sleep Duration (hours)"); ax.set_ylabel("Number of Sleep Records")
    ax.set_title(f"Distribution of Nightly Sleep Duration (n={len(sleep)}, 2 months)", fontsize=12.5, fontweight="bold", loc="left")
    plt.tight_layout(); fig.savefig(os.path.join(out_dir, "06_sleep_distribution.png"), dpi=160); plt.close(fig)


def chart_steps_vs_calories(da, out_dir):
    c = COLORS
    fig, ax = plt.subplots(figsize=(7.5, 5))
    ax.scatter(da["TotalSteps"], da["Calories"], alpha=0.3, color=c["navy"], s=20)
    z = np.polyfit(da["TotalSteps"], da["Calories"], 1)
    xs = np.linspace(0, da["TotalSteps"].max(), 50)
    ax.plot(xs, np.polyval(z, xs), color=c["coral"], linewidth=2, linestyle="--")
    r = da[["TotalSteps", "Calories"]].corr().iloc[0, 1]
    ax.set_xlabel("Total Steps"); ax.set_ylabel("Calories Burned")
    ax.set_title(f"Steps vs. Calories Burned (n={len(da)}, 2 months)", fontsize=12.5, fontweight="bold", loc="left")
    ax.text(0.03, 0.9, f"r = {r:.2f}", transform=ax.transAxes, fontsize=10, fontweight="bold", color=c["navy"])
    plt.tight_layout(); fig.savefig(os.path.join(out_dir, "07_steps_calories.png"), dpi=160); plt.close(fig)


def chart_logging_consistency(user_avg, out_dir):
    c = COLORS
    bins = [0, 50, 70, 90, 100]
    labels = ["<50%", "50-70%", "70-90%", "90-100%"]
    ua = user_avg.copy()
    ua["Bucket"] = pd.cut(ua["LoggingRate"], bins=bins, labels=labels, include_lowest=True)
    counts = ua["Bucket"].value_counts().reindex(labels)
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.bar(labels, counts.values, color=[c["coral"], c["gold"], c["teal"], c["navy"]])
    for i, v in enumerate(counts.values):
        ax.text(i, v + 0.3, str(v), ha="center", fontsize=10, fontweight="bold")
    ax.set_ylabel("Number of Users"); ax.set_xlabel("% of 62-Day Combined Window with Logged Data")
    ax.set_title("Device Engagement Across Combined 2-Month Window", fontsize=12.5, fontweight="bold", loc="left")
    plt.tight_layout(); fig.savefig(os.path.join(out_dir, "08_logging_consistency.png"), dpi=160); plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mar-apr-dir", default="./data/raw/mar_apr", help="Folder with the March 12-April 12 export")
    parser.add_argument("--apr-may-dir", default="./data/raw/apr_may", help="Folder with the April 12-May 12 export")
    parser.add_argument("--out-dir", default="./images")
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    print("Loading and combining daily activity...")
    da = load_combined_daily_activity(args.mar_apr_dir, args.apr_may_dir)

    print("Loading and combining sleep...")
    sleep = load_combined_sleep(args.mar_apr_dir, args.apr_may_dir)
    merged = da.merge(sleep, left_on=["Id", "ActivityDate"], right_on=["Id", "SleepDate"], how="left")

    print("Loading and combining hourly steps...")
    hourly_df = load_combined_hourly_steps(args.mar_apr_dir, args.apr_may_dir)
    hourly_avg, dow_avg = hourly_patterns(hourly_df)

    print("Loading and combining heart rate...")
    hr = load_combined_heartrate(args.mar_apr_dir, args.apr_may_dir)

    print("Loading and combining weight...")
    weight = load_combined_weight(args.mar_apr_dir, args.apr_may_dir)

    print("Segmenting users...")
    user_avg = user_segmentation(da)

    print("Generating charts...")
    chart_hourly_steps(hourly_avg, args.out_dir)
    chart_dow_steps(dow_avg, args.out_dir)
    chart_activity_minutes(da, args.out_dir)
    chart_user_segments(user_avg, args.out_dir)
    chart_sedentary_vs_sleep(merged, args.out_dir)
    chart_sleep_distribution(sleep, args.out_dir)
    chart_steps_vs_calories(da, args.out_dir)
    chart_logging_consistency(user_avg, args.out_dir)

    print("\n=== Summary ===")
    print(f"Daily activity: {da['Id'].nunique()} users, {da['ActivityDate'].nunique()} days, {len(da)} rows")
    print(f"Sleep: {sleep['Id'].nunique()} users, {len(sleep)} records")
    print(f"Hourly: {hourly_df['Id'].nunique()} users, {len(hourly_df)} rows")
    print(f"Heart rate: {hr['Id'].nunique()} users, {len(hr)} readings")
    print(f"Weight: {weight['Id'].nunique()} users, {len(weight)} records")
    print(f"Avg sedentary min/day: {da['SedentaryMinutes'].mean():.0f}")
    m = merged.dropna(subset=["TotalMinutesAsleep"])
    print(f"Sedentary-Sleep correlation: {m[['SedentaryMinutes','TotalMinutesAsleep']].corr().iloc[0,1]:.2f}")
    print(f"Steps-Calories correlation: {da[['TotalSteps','Calories']].corr().iloc[0,1]:.2f}")
    print(f"Charts written to {args.out_dir}")


if __name__ == "__main__":
    main()
