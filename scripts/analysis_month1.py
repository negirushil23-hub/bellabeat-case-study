import os
import argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLORS = {"teal":"#1F7A6C","coral":"#E76F51","navy":"#264653","gold":"#E9C46A","grey":"#8D99AE"}
plt.rcParams.update({"font.family":"DejaVu Sans","axes.spines.top":False,"axes.spines.right":False})
DOW_ORDER = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

parser = argparse.ArgumentParser()
parser.add_argument("--data-dir", default="./data/raw/mar_apr", help="Folder with the March 12-April 12 export")
parser.add_argument("--out-dir", default="./reports/month1_mar_apr/images")
args = parser.parse_args()
DATA = args.data_dir
OUT = args.out_dir
os.makedirs(OUT, exist_ok=True)

def load_daily_activity(path):
    da = pd.read_csv(path)
    da["ActivityDate"] = pd.to_datetime(da["ActivityDate"], format="%m/%d/%Y")
    da["Weekday"] = da["ActivityDate"].dt.day_name()
    da["IsWeekend"] = da["ActivityDate"].dt.dayofweek >= 5
    da["TotalActiveMinutes"] = da["VeryActiveMinutes"]+da["FairlyActiveMinutes"]+da["LightlyActiveMinutes"]
    return da

def aggregate_sleep(path):
    ms = pd.read_csv(path)
    ms["date_parsed"] = pd.to_datetime(ms["date"], format="%m/%d/%Y %I:%M:%S %p")
    ms["SleepDate"] = ms["date_parsed"].dt.date
    per_log = ms.groupby(["Id","SleepDate","logId"]).agg(
        TotalMinutesRecorded=("value","count"),
        TotalMinutesAsleep=("value", lambda x: (x==1).sum())).reset_index()
    daily = per_log.groupby(["Id","SleepDate"]).agg(
        TotalMinutesAsleep=("TotalMinutesAsleep","sum"),
        TotalTimeInBed=("TotalMinutesRecorded","sum")).reset_index()
    daily["SleepEfficiency"] = (daily["TotalMinutesAsleep"]/daily["TotalTimeInBed"]*100).round(1)
    daily["SleepDate"] = pd.to_datetime(daily["SleepDate"])
    return daily

def classify_activity(avg_steps):
    if avg_steps < 5000: return "Sedentary"
    elif avg_steps < 7500: return "Lightly Active"
    elif avg_steps < 10000: return "Moderately Active"
    return "Very Active"

def user_segmentation(da):
    user_avg = da.groupby("Id").agg(
        AvgSteps=("TotalSteps","mean"),
        AvgSedentaryMin=("SedentaryMinutes","mean"),
        AvgCalories=("Calories","mean"),
        AvgVeryActiveMin=("VeryActiveMinutes","mean"),
        DaysLogged=("ActivityDate","count")).reset_index()
    user_avg["ActivityClass"] = user_avg["AvgSteps"].apply(classify_activity)
    total_days = da["ActivityDate"].nunique()
    user_avg["LoggingRate"] = (user_avg["DaysLogged"]/total_days*100).clip(upper=100)
    return user_avg

def hourly_patterns(path):
    hs = pd.read_csv(path)
    hs["ActivityHour"] = pd.to_datetime(hs["ActivityHour"], format="%m/%d/%Y %I:%M:%S %p")
    hs["Hour"] = hs["ActivityHour"].dt.hour
    hs["Date"] = hs["ActivityHour"].dt.date
    hourly_avg = hs.groupby("Hour")["StepTotal"].mean().reset_index()
    daily_from_hourly = hs.groupby(["Id","Date"])["StepTotal"].sum().reset_index()
    daily_from_hourly["Date"] = pd.to_datetime(daily_from_hourly["Date"])
    daily_from_hourly["Weekday"] = daily_from_hourly["Date"].dt.day_name()
    dow_avg = daily_from_hourly.groupby("Weekday")["StepTotal"].mean().reindex(DOW_ORDER)
    return hourly_avg, dow_avg

da = load_daily_activity(f"{DATA}/dailyActivity_merged.csv")
sleep = aggregate_sleep(f"{DATA}/minuteSleep_merged.csv")
def _read_headerless_or_normal(path, expected_cols):
    """Some source files in this dataset were found with their header row
    relocated to the LAST line instead of the first. Detect and handle
    both cases transparently."""
    with open(path) as f:
        first_line = f.readline().strip()
    if first_line.replace(" ", "") == ",".join(expected_cols).replace(" ", ""):
        return pd.read_csv(path)
    return pd.read_csv(path, header=None, names=expected_cols, skipfooter=1, engine="python")

merged = da.merge(sleep, left_on=["Id","ActivityDate"], right_on=["Id","SleepDate"], how="left")
user_avg = user_segmentation(da)
hourly_avg, dow_avg = hourly_patterns(f"{DATA}/hourlySteps_merged.csv")
weight = _read_headerless_or_normal(f"{DATA}/weightLogInfo_merged.csv",
                                     ["Id","Date","WeightKg","WeightPounds","Fat","BMI","IsManualReport","LogId"])
hr = _read_headerless_or_normal(f"{DATA}/heartrate_seconds_merged.csv", ["Id","Time","Value"])

zero_days = (da["TotalSteps"]==0).sum()
print("=== BASIC ===")
print("daily rows:", len(da), "users:", da.Id.nunique(), "days:", da.ActivityDate.nunique())
print("dup daily rows:", da.duplicated().sum())
print("zero-step days:", zero_days, f"({zero_days/len(da)*100:.1f}%)")
print("sleep users:", sleep.Id.nunique(), "sleep-days:", len(sleep))
print("matched activity+sleep days:", merged.dropna(subset=['TotalMinutesAsleep']).shape[0])
print("weight users:", weight.Id.nunique(), "rows:", len(weight))
print("hr users:", hr.Id.nunique())

print("\n=== ACTIVITY MINUTES AVG ===")
for c in ["SedentaryMinutes","LightlyActiveMinutes","FairlyActiveMinutes","VeryActiveMinutes"]:
    print(c, da[c].mean())

print("\n=== USER SEGMENTATION ===")
print(user_avg["ActivityClass"].value_counts())
print("avg steps overall:", da["TotalSteps"].mean())

print("\n=== DOW ===")
print(dow_avg)

m = merged.dropna(subset=["TotalMinutesAsleep"])
m = m[m["TotalTimeInBed"]>60]
print("\n=== SLEEP ===")
print("valid sleep records (>60min inbed):", len(m))
print("mean sleep eff:", m["SleepEfficiency"].mean())
print("mean sleep hrs:", (m["TotalMinutesAsleep"]/60).mean())
print("median sleep hrs:", (m["TotalMinutesAsleep"]/60).median())
print("pct nights <7hr:", (m["TotalMinutesAsleep"]<420).mean()*100)

print("\n=== CORR ===")
print("steps vs calories:", da[["TotalSteps","Calories"]].corr().iloc[0,1])
print("sedentary vs sleep:", m[["SedentaryMinutes","TotalMinutesAsleep"]].corr().iloc[0,1])
print("steps vs sleep:", m[["TotalSteps","TotalMinutesAsleep"]].corr().iloc[0,1])

print("\n=== LOGGING CONSISTENCY ===")
bins=[0,50,75,90,100]; labels=["<50%","50-75%","75-90%","90-100%"]
user_avg["Bucket"]=pd.cut(user_avg["LoggingRate"],bins=bins,labels=labels,include_lowest=True)
print(user_avg["Bucket"].value_counts().reindex(labels))
print(user_avg.sort_values("LoggingRate").head(3)[["Id","DaysLogged","LoggingRate"]])

peak_hour = hourly_avg.loc[hourly_avg["StepTotal"].idxmax()]
print("\npeak hour:", peak_hour["Hour"], peak_hour["StepTotal"])

# ===== CHARTS =====
def savefig(fig,name):
    fig.tight_layout(); fig.savefig(f"{OUT}/{name}", dpi=160); plt.close(fig)

c=COLORS
fig,ax=plt.subplots(figsize=(9,4.5))
ax.plot(hourly_avg["Hour"],hourly_avg["StepTotal"],color=c["teal"],linewidth=2.5,marker="o",markersize=4)
ax.fill_between(hourly_avg["Hour"],hourly_avg["StepTotal"],color=c["teal"],alpha=0.12)
ax.set_xticks(range(0,24,2)); ax.set_xlabel("Hour of Day"); ax.set_ylabel("Average Steps")
ax.set_title("Average Steps by Hour of Day (All Users)",fontsize=13,fontweight="bold",loc="left")
savefig(fig,"01_hourly_steps.png")

fig,ax=plt.subplots(figsize=(8,4.5))
colors=[c["coral"] if d=="Sunday" else (c["gold"] if d in ["Tuesday","Saturday"] else c["teal"]) for d in dow_avg.index]
ax.bar(dow_avg.index,dow_avg.values,color=colors)
ax.axhline(7500,color=c["navy"],linestyle="--",linewidth=1,alpha=0.6)
ax.set_ylabel("Average Total Steps"); ax.set_title("Average Daily Steps by Day of Week",fontsize=13,fontweight="bold",loc="left")
plt.xticks(rotation=20)
savefig(fig,"02_dow_steps.png")

avg_min={"Sedentary":da["SedentaryMinutes"].mean(),"Lightly Active":da["LightlyActiveMinutes"].mean(),
         "Fairly Active":da["FairlyActiveMinutes"].mean(),"Very Active":da["VeryActiveMinutes"].mean()}
fig,ax=plt.subplots(figsize=(7,5))
ax.pie(list(avg_min.values()),colors=[c["grey"],c["teal"],c["gold"],c["coral"]],
       autopct=lambda p: f"{p:.0f}%" if p>3 else "",startangle=90,
       wedgeprops={"width":0.42,"edgecolor":"white","linewidth":2})
ax.set_title("Average Daily Minutes by Activity Level",fontsize=13,fontweight="bold",loc="left")
ax.legend([f"{k} ({v:.0f} min)" for k,v in avg_min.items()],loc="center",frameon=False,fontsize=9.5)
savefig(fig,"03_activity_minutes.png")

order=["Sedentary","Lightly Active","Moderately Active","Very Active"]
counts=user_avg["ActivityClass"].value_counts().reindex(order)
fig,ax=plt.subplots(figsize=(7.5,4.5))
ax.barh(order,counts.values,color=[c["grey"],c["gold"],c["teal"],c["coral"]])
ax.set_xlabel("Number of Users"); ax.set_title("User Segmentation by Average Daily Steps",fontsize=13,fontweight="bold",loc="left")
savefig(fig,"04_user_segments.png")

fig,ax=plt.subplots(figsize=(7.5,5))
ax.scatter(m["SedentaryMinutes"]/60,m["TotalMinutesAsleep"]/60,alpha=0.5,color=c["teal"],s=35)
z=np.polyfit(m["SedentaryMinutes"],m["TotalMinutesAsleep"],1)
xs=np.linspace(m["SedentaryMinutes"].min(),m["SedentaryMinutes"].max(),50)
ax.plot(xs/60,np.polyval(z,xs)/60,color=c["coral"],linewidth=2,linestyle="--")
ax.set_xlabel("Sedentary Hours (per day)"); ax.set_ylabel("Sleep Duration (hours)")
ax.set_title("Sedentary Time vs. Sleep Duration",fontsize=13,fontweight="bold",loc="left")
savefig(fig,"05_sedentary_sleep.png")

fig,ax=plt.subplots(figsize=(8,4.5))
ax.hist(m["TotalMinutesAsleep"]/60,bins=20,color=c["teal"],alpha=0.85,edgecolor="white")
ax.axvline(7,color=c["coral"],linestyle="--",linewidth=2)
ax.set_xlabel("Sleep Duration (hours)"); ax.set_ylabel("Number of Sleep Records")
ax.set_title("Distribution of Nightly Sleep Duration",fontsize=13,fontweight="bold",loc="left")
savefig(fig,"06_sleep_distribution.png")

fig,ax=plt.subplots(figsize=(7.5,5))
ax.scatter(da["TotalSteps"],da["Calories"],alpha=0.4,color=c["navy"],s=25)
z=np.polyfit(da["TotalSteps"],da["Calories"],1)
xs=np.linspace(0,da["TotalSteps"].max(),50)
ax.plot(xs,np.polyval(z,xs),color=c["coral"],linewidth=2,linestyle="--")
ax.set_xlabel("Total Steps"); ax.set_ylabel("Calories Burned")
ax.set_title("Steps vs. Calories Burned",fontsize=13,fontweight="bold",loc="left")
savefig(fig,"07_steps_calories.png")

bins=[0,50,75,90,100]; labels=["<50%","50-75%","75-90%","90-100%"]
ua=user_avg.copy()
ua["Bucket"]=pd.cut(ua["LoggingRate"],bins=bins,labels=labels,include_lowest=True)
counts=ua["Bucket"].value_counts().reindex(labels)
fig,ax=plt.subplots(figsize=(7.5,4.5))
ax.bar(labels,counts.values,color=[c["coral"],c["gold"],c["teal"],c["navy"]])
ax.set_ylabel("Number of Users"); ax.set_xlabel("% of Study Days with Logged Data")
ax.set_title("Device Engagement: Consistency of Daily Logging",fontsize=13,fontweight="bold",loc="left")
savefig(fig,"08_logging_consistency.png")

print("\nDONE - charts written")
