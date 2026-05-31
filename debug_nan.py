import pandas as pd

SHEET_URL = "https://docs.google.com/spreadsheets/d/1DlWT2btmazXAGRXSVmdrEe2J4niKwJiNGGTs40xOgqE/export?format=csv"
print("Loading data for analysis...")
df = pd.read_csv(SHEET_URL)

print("\n--- Jumlah Baris & Kolom ---")
print(df.shape)

print("\n--- Jumlah Nilai Kosong (NaN) per Kolom ---")
print(df.isna().sum())

print("\n--- Sampel 5 Baris Pertama ---")
print(df.head())

print("\n--- Sampel 5 Baris Terakhir ---")
print(df.tail())
