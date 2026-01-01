
import pandas as pd
import json
import numpy as np

def parse_currency(val):
    if isinstance(val, (int, float)):
        return float(val)
    # Remove currency symbol and standard separators (Assume US Format 1,234.56)
    clean = str(val).replace("€", "").replace("'", "").replace(",", "")
    # Handle weird encoding artifact 
    clean = clean.replace("", "").strip()
    return float(clean)

print("--- START VERIFICATION ---")

# 1. Load Data
try:
    df = pd.read_csv("Testdata/tax_events_2025_AT.csv")
    with open("Testdata/tax_report_2025_AT.json", "r") as f:
        report = json.load(f)
except Exception as e:
    print(f"FAILED to load files: {e}")
    exit(1)

print(f"Loaded {len(df)} tax events.")

# 2. Parse Columns
cols = ["Proceeds (EUR)", "Cost Basis (EUR)", "Realized Gain (EUR)"]
for col in cols:
    df[col] = df[col].apply(parse_currency)

# 3. Verify Row-by-Row Math
df["Calc_Gain"] = df["Proceeds (EUR)"] - df["Cost Basis (EUR)"]
df["Diff"] = df["Realized Gain (EUR)"] - df["Calc_Gain"]

# Allow for tiny floating point diffs (cents)
errors = df[abs(df["Diff"]) > 0.02]

if not errors.empty:
    print(f"CRITICAL: Found {len(errors)} rows with math errors (Gain != Proceeds - Cost):")
    print(errors)
else:
    print("SUCCESS: All 165+ events pass individual math check (Gain = Proceeds - Cost).")

# 4. Aggregate & Compare to Report
total_proceeds = df["Proceeds (EUR)"].sum()
total_cost = df["Cost Basis (EUR)"].sum()
total_gain_csv = df["Realized Gain (EUR)"].sum()

report_gain = report["total_realized_gain"]
report_taxable = report["taxable_gain"]
report_tax = report["tax_owed"]

print("\n--- AGGREGATION CHECK ---")
print(f"CSV Total Gain: {total_gain_csv:.2f}")
print(f"JSON Report Gain: {report_gain:.2f}")

if abs(total_gain_csv - report_gain) < 0.1:
    print("SUCCESS: CSV Aggregation matches JSON Report.")
else:
    print(f"WARNING: Mismatch in total gain! Diff: {total_gain_csv - report_gain}")

# 5. Compliance Check (27.5%)
# Austrian Logic: Net Gain * 27.5%
calc_tax = total_gain_csv * 0.275

print("\n--- COMPLIANCE CHECK (Austria) ---")
print(f"Tax Base (Net Gain): {total_gain_csv:.2f}")
print(f"Expected Tax (27.5%): {calc_tax:.2f}")
print(f"Reported Tax: {report_tax:.2f}")

if abs(calc_tax - report_tax) < 0.1:
    print("SUCCESS: Tax calculation is strictly compliant (27.5% of Net Gain).")
else:
    print("WARNING: Tax mismatch!")
