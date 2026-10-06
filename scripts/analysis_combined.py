"""
Bellabeat case study: combined two-month analysis.
Data: FitBit Fitness Tracker Data (CC0), https://www.kaggle.com/datasets/arashnic/fitbit

The dataset comes as two exports (Mar 12 - Apr 12 and Apr 12 - May 12, 2016)
with identically named files, so keep them in separate folders or one will
overwrite the other.

What the script does:
1. Combines both months. April 12 is in both exports and the March-April
   version is cut off part way through the day, so that version is dropped
   (daily activity, hourly steps and heart rate).
2. Builds one sleep table from minute-level logs (Mar-Apr) and the official
   sleepDay file (Apr-May).
3. Segments users, calculates correlations and writes the 8 report charts.

Run:
    python analysis_combined.py --mar-apr-dir ./data/raw/mar_apr \
        --apr-may-dir ./data/raw/apr_may --out-dir ./reports/combined_mar_may/images
"""

import argparse
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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



def load_combined_daily_activity(mar_apr_dir, apr_may_dir):
    """Daily steps/calories/activity minutes, both months combined.

    Both months use a direct dailyActivity_merged.csv when present. If
    April-May's combined file isn't available, it's reconstructed from its
    three component files instead (dailySteps/dailyCalories/dailyIntensities
    _merged.csv). The fallback has no distance columns, so TotalDistance,
    TrackerDistance and LoggedActivitiesDistance are left as NA; every column
    it does contain matches the real file.
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
    sleepDay_merged file, which is preferred whenever both exist. It
    deduplicates overlapping sleep/nap sessions that a manual
    reconstruction can slightly over-count.
    """
    ms = pd.read_csv(os.path.join(mar_apr_dir, "minuteSleep_merged.csv"))
    ms["date_parsed"] = pd.to_datetime(ms["date"], format="%m/%d/%Y %I:%M:%S %p")
    # Date each sleep session (logId) by the day it ENDED (the wake date), as the
    # official sleepDay file does. Dating each minute separately would split any
    # night that crosses midnight into two partial days.
    ms["is_asleep"] = (ms["value"] == 1).astype(int)
    per_log = ms.groupby(["Id", "logId"]).agg(
        WakeTime=("date_parsed", "max"),
        TotalMinutesRecorded=("value", "count"),
        TotalMinutesAsleep=("is_asleep", "sum"),
    ).reset_index()
    per_log["SleepDate"] = per_log["WakeTime"].dt.normalize()
    month1 = per_log.groupby(["Id", "SleepDate"]).agg(
        TotalMinutesAsleep=("TotalMinutesAsleep", "sum"),
        TotalTimeInBed=("TotalMinutesRecorded", "sum"),
    ).reset_index()
    month1["SleepEfficiency"] = (month1["TotalMinutesAsleep"] / month1["TotalTimeInBed"] * 100).round(1)

    sd = pd.read_csv(os.path.join(apr_may_dir, "sleepDay_merged.csv"))
    sd["SleepDay"] = pd.to_datetime(sd["SleepDay"], format="%m/%d/%Y %I:%M:%S %p").dt.normalize()
    month2 = sd.groupby(["Id", "SleepDay"]).agg(
        TotalMinutesAsleep=("TotalMinutesAsleep", "sum"),
        TotalTimeInBed=("TotalTimeInBed", "sum"),
    ).reset_index().rename(columns={"SleepDay": "SleepDate"})
    month2["SleepEfficiency"] = (month2["TotalMinutesAsleep"] / month2["TotalTimeInBed"] * 100).round(1)

    # Same short-nap floor for both sources so they are comparable
    month1 = month1[month1["TotalTimeInBed"] > 60]
    month2 = month2[month2["TotalTimeInBed"] > 60]
    month1["SleepEfficiency"] = (month1["TotalMinutesAsleep"] / month1["TotalTimeInBed"] * 100).round(1)

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
    with open(path) as f:
        first_line = f.readline().strip()
    if first_line.replace(" ", "") == ",".join(expected_cols).replace(" ", ""):
        return pd.read_csv(path)
    # Header isn't on the first line. In this dataset it was found on the LAST
    # line, so read with explicit names and skip that final row.
    df = pd.read_csv(path, header=None, names=expected_cols, skipfooter=1, engine="python")
    return df


def load_combined_heartrate(mar_apr_dir, apr_may_dir):
    """Second-level heart rate, both months combined. The March-April file's
    April 12 is truncated (device-sync cutoff), so that day is dropped."""
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
    """Manual/automatic weight logs, both months combined. The two exports share
    duplicate entries on the boundary day, so rows are de-duplicated by LogId."""
    cols = ["Id", "Date", "WeightKg", "WeightPounds", "Fat", "BMI", "IsManualReport", "LogId"]
    month1 = _read_headerless_or_normal(os.path.join(mar_apr_dir, "weightLogInfo_merged.csv"), cols)
    month2 = _read_headerless_or_normal(os.path.join(apr_may_dir, "weightLogInfo_merged.csv"), cols)
    for df in (month1, month2):
        df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y %I:%M:%S %p")

    combined = pd.concat([month1, month2], ignore_index=True).drop_duplicates(subset=["LogId"])
    combined = combined.sort_values(["Id", "Date"]).reset_index(drop=True)
    return combined



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
    top2 = set(dow_avg.nlargest(2).index)
    colors = [c["coral"] if d == dow_avg.idxmin() else (c["gold"] if d in top2 else c["teal"]) for d in dow_avg.index]
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



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mar-apr-dir", default="./data/raw/mar_apr", help="Folder with the March 12-April 12 export")
    parser.add_argument("--apr-may-dir", default="./data/raw/apr_may", help="Folder with the April 12-May 12 export")
    parser.add_argument("--out-dir", default="./reports/combined_mar_may/images")
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

    # --- Everything below is a number quoted in the report ---
    print("\n=== Report check ===")
    print(f"Zero-step days: {(da['TotalSteps']==0).sum()} of {len(da)} ({(da['TotalSteps']==0).mean()*100:.1f}%)")
    print("Avg minutes/day:", {k: round(da[k].mean()) for k in
          ["SedentaryMinutes", "LightlyActiveMinutes", "FairlyActiveMinutes", "VeryActiveMinutes"]})
    print("Segments:", user_avg["ActivityClass"].value_counts().to_dict())
    peak = hourly_avg.loc[hourly_avg["StepTotal"].idxmax()]
    print(f"Peak hour: {int(peak['Hour'])}:00 ({peak['StepTotal']:.0f} avg steps)")
    print("Day-of-week avg steps:\n", dow_avg.round(0).to_string())
    print(f"Sleep (all {len(sleep)} records): efficiency {sleep['SleepEfficiency'].mean():.1f}%, "
          f"median {sleep['TotalMinutesAsleep'].median()/60:.2f} h, "
          f"<7h {(sleep['TotalMinutesAsleep']<420).mean()*100:.1f}%")
    print(f"Matched activity+sleep days: {len(m)} of {len(da)}")
    print(f"Steps-Sleep correlation: {m[['TotalSteps','TotalMinutesAsleep']].corr().iloc[0,1]:.2f}")
    ua = user_avg.copy()
    ua["Bucket"] = pd.cut(ua["LoggingRate"], bins=[0, 50, 70, 90, 100],
                          labels=["<50%", "50-70%", "70-90%", "90-100%"], include_lowest=True)
    print("Logging buckets:", ua["Bucket"].value_counts().sort_index().to_dict())
    print(f"Weight: {len(weight)/weight['Id'].nunique():.1f} entries per logging user")
    print(f"Charts written to {args.out_dir}")


if __name__ == "__main__":
    main()
