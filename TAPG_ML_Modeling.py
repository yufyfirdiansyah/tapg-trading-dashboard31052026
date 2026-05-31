import os
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
import matplotlib.pyplot as plt

# Impor atau install XGBoost secara otomatis
try:
    from xgboost import XGBClassifier
except ImportError:
    print("[INFO] XGBoost belum terinstall. Menginstal paket via pip...")
    os.system("pip install xgboost")
    from xgboost import XGBClassifier

# =====================================================================
# 1. KONFIGURASI & INGESTI DATA
# =====================================================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1DlWT2btmazXAGRXSVmdrEe2J4niKwJiNGGTs40xOgqE/export?format=csv"
print(f"Menghubungkan langsung ke Google Sheet: {SHEET_URL}...")

try:
    df = pd.read_csv(SHEET_URL)
    print("Berhasil mengunduh data dari Cloud!")
    print("Jumlah Baris:", df.shape[0])
    print("Kolom yang Tersedia:", df.columns.tolist())
except Exception as e:
    raise Exception(f"Gagal mengambil data dari Google Sheet: {e}")

# Pastikan data diurutkan secara kronologis berdasarkan Tanggal
df['Date'] = pd.to_datetime(df['Date'])
df = df.sort_values('Date').reset_index(drop=True)

# =====================================================================
# 2. FEATURE ENGINEERING & BURSA TIME-ALIGNMENT (IDX SYNC)
# =====================================================================
print("\n=== Melakukan Rekayasa Fitur & Penyelarasan Waktu Buka IDX ===")

# A. Persentase Return Harian untuk Variabel Makro & Komoditas
# Karena pasar global tutup pukul 04:00-05:00 WIB, semua return Hari t sudah diketahui sebelum IDX buka pukul 09:00 WIB Hari t+1.
macro_cols = ['WTI_Close', 'Brent_Close', 'Soybean_Close', 'EWM_Close', 'CPO_Close', 'USDIDR_Close']
for col in macro_cols:
    new_col_name = col.replace('_Close', '_Return')
    df[new_col_name] = df[col].pct_change().replace([np.inf, -np.inf], 0).fillna(0)

# B. Technical Indicators untuk TAPG.JK
# 1. Moving Averages
df['TAPG_MA5'] = df['TAPG_Close'].rolling(window=5).mean()
df['TAPG_MA20'] = df['TAPG_Close'].rolling(window=20).mean()

# 2. Relative Strength Index (RSI - 14)
delta = df['TAPG_Close'].diff()
gain = delta.where(delta > 0, 0.0)
loss = -delta.where(delta < 0, 0.0)
avg_gain = gain.rolling(window=14).mean()
avg_loss = loss.rolling(window=14).mean()
rs = avg_gain / (avg_loss + 1e-9)
df['TAPG_RSI'] = 100 - (100 / (1 + rs))

# 3. Average True Range (ATR - 14)
high_low = df['TAPG_High'] - df['TAPG_Low']
high_close = (df['TAPG_High'] - df['TAPG_Close'].shift(1)).abs()
low_close = (df['TAPG_Low'] - df['TAPG_Close'].shift(1)).abs()
true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
df['TAPG_ATR'] = true_range.rolling(window=14).mean()

# 4. MACD & Signal Line
exp12 = df['TAPG_Close'].ewm(span=12, adjust=False).mean()
exp26 = df['TAPG_Close'].ewm(span=26, adjust=False).mean()
df['TAPG_MACD'] = exp12 - exp26
df['TAPG_MACD_Signal'] = df['TAPG_MACD'].ewm(span=9, adjust=False).mean()

# C. Return & Volume Change TAPG (Ganti inf akibat pembagian 0 menjadi 0)
df['TAPG_Return'] = df['TAPG_Close'].pct_change().replace([np.inf, -np.inf], 0).fillna(0)
df['TAPG_Volume_Change'] = df['TAPG_Volume'].pct_change().replace([np.inf, -np.inf], 0).fillna(0)

# D. Fitur Prediktor yang Digunakan
feature_cols = [
    'WTI_Return', 'Brent_Return', 'Soybean_Return', 'EWM_Return', 'CPO_Return', 'USDIDR_Return',
    'TAPG_MA5', 'TAPG_MA20', 'TAPG_RSI', 'TAPG_ATR', 'TAPG_MACD', 'TAPG_MACD_Signal',
    'TAPG_Return', 'TAPG_Volume_Change'
]

# E. DETEKSI FITUR KOSONG SECARA OTOMATIS (FAIL-SAFE DATA ENGINEERING)
nan_features = []
for col in feature_cols:
    if col in df.columns and df[col].isna().all():
        nan_features.append(col)

if len(nan_features) > 0:
    print(f"\n[WARNING] Mengeluarkan fitur yang 100% kosong (NaN) dari model: {nan_features}")
    feature_cols = [col for col in feature_cols if col not in nan_features]

# =====================================================================
# 3. TARGET LABELING (PREDIKSI ARAH HARI ESOK / T+1)
# =====================================================================
# KETENTUAN USER: Selisih return dikonversi ke 0 & 1.
# - Target = 1: jika Return TAPG esok hari positif (> 0) -> Sinyal BUY
# - Target = 0: jika Return TAPG esok hari negatif/netral (<= 0) -> Sinyal SELL
df['Target'] = (df['TAPG_Return'].shift(-1) > 0).astype(int)

# Bersihkan nilai NaN hasil kalkulasi teknikal & return historis di awal-awal baris
# Hanya baris dengan fitur dan target valid yang dipertahankan
df_clean = df.dropna(subset=feature_cols + ['Target']).copy().reset_index(drop=True)

# Pastikan tidak ada nilai infinity tersisa di dataset
df_clean = df_clean.replace([np.inf, -np.inf], 0).fillna(0)
print(f"\nData setelah pembersihan NaN & Infinity. Jumlah baris: {df_clean.shape[0]}")

# =====================================================================
# 4. CHRONOLOGICAL TIME-SERIES SPLIT (80% Train, 20% Test)
# =====================================================================
split_idx = int(len(df_clean) * 0.8)
train_df = df_clean.iloc[:split_idx].copy()
test_df = df_clean.iloc[split_idx:].copy()

X_train = train_df[feature_cols]
y_train = train_df['Target']
X_test = test_df[feature_cols]
y_test = test_df['Target']

print(f"\nProporsi Pembagian Data Secara Kronologis:")
print(f"- Training Data : {train_df['Date'].min().strftime('%Y-%m-%d')} s/d {train_df['Date'].max().strftime('%Y-%m-%d')} ({len(train_df)} baris)")
print(f"- Testing Data  : {test_df['Date'].min().strftime('%Y-%m-%d')} s/d {test_df['Date'].max().strftime('%Y-%m-%d')} ({len(test_df)} baris)")

# Standardisasi Fitur
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# =====================================================================
# 5. PELATIHAN & EVALUASI MODEL
# =====================================================================
models = {
    "Logistic Regression": LogisticRegression(random_state=42),
    "Random Forest": RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42),
    "XGBoost": XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42, eval_metric='logloss')
}

metrics_summary = {}

print("\n=== Melatih & Mengevaluasi Model Klasifikasi ===")
for name, model in models.items():
    print(f"\nTraining {name}...")
    model.fit(X_train_scaled, y_train)
    
    # Prediksi Arah Hari Esok (Test Set)
    y_pred = model.predict(X_test_scaled)
    y_pred_proba = model.predict_proba(X_test_scaled)[:, 1] if hasattr(model, "predict_proba") else [0]*len(y_test)
    
    # Penghitungan Metrik
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    auc = roc_auc_score(y_test, y_pred_proba)
    
    metrics_summary[name] = {
        "Accuracy": acc,
        "Precision": prec,
        "Recall": rec,
        "F1-Score": f1,
        "ROC-AUC": auc,
        "Predictions": y_pred
    }
    
    print(f"Performa {name} di Data Test:")
    print(f" - Accuracy  : {acc*100:.2f}%")
    print(f" - Precision : {prec*100:.2f}%")
    print(f" - Recall    : {rec*100:.2f}%")
    print(f" - F1-Score  : {f1:.4f}")
    print(f" - ROC-AUC   : {auc:.4f}")

# =====================================================================
# 6. BACKTESTING & SIMULASI KURVA EKUITAS (EQUITY CURVE)
# =====================================================================
print("\n=== Menjalankan Backtest Simulasi Trading ===")

# Target kita berada di hari t+1, return riil TAPG di hari t+1 adalah:
# test_df['TAPG_Return'].shift(-1). Kita sesuaikan untuk mendapatkan return trading aktual esok harinya.
tapg_tomorrow_return = test_df['TAPG_Close'].pct_change().shift(-1).fillna(0).values

# 1. Buy and Hold
bh_equity = np.cumprod(1 + tapg_tomorrow_return) - 1

# Hitung Ekuitas Kumulatif untuk masing-masing Model
model_equities = {}
for name, metrics in metrics_summary.items():
    preds = metrics["Predictions"]
    # Return trading harian = Prediksi model (0 atau 1) * Return Riil TAPG esok harinya
    # Jika 1 = BUY (ikut return positif/negatif TAPG esok), jika 0 = SELL (keluar posisi / return 0)
    strategy_returns = preds * tapg_tomorrow_return
    model_equity = np.cumprod(1 + strategy_returns) - 1
    model_equities[name] = model_equity

# =====================================================================
# 7. VISUALISASI HASIL BACKTEST & PENYIMPANAN GAMBAR
# =====================================================================
plt.figure(figsize=(12, 7))
plt.plot(test_df['Date'], bh_equity * 100, label='Buy & Hold TAPG.JK', color='gray', linestyle='--', linewidth=2)
colors = {"Logistic Regression": "#3b82f6", "Random Forest": "#10b981", "XGBoost": "#f59e0b"}

for name, equity in model_equities.items():
    plt.plot(test_df['Date'], equity * 100, label=f'Strategi {name} (Profit: {equity[-1]*100:.2f}%)', color=colors[name], linewidth=2.5)

plt.title('Simulasi Backtest Performa Model ML vs Buy & Hold TAPG.JK\n(Return Dikonversi ke 0 & 1 - BUY & SELL)', fontsize=14, fontweight='bold', pad=15)
plt.xlabel('Tanggal', fontsize=11, labelpad=10)
plt.ylabel('Kumulatif Return (%)', fontsize=11, labelpad=10)
plt.grid(True, linestyle=':', alpha=0.6)
plt.legend(fontsize=10, loc='upper left')
plt.gca().patch.set_facecolor('#fafafa')

# Tentukan folder penyimpanan gambar
output_dir = "C:/Users/LaptopQu/.gemini/antigravity/brain/50cd8025-f545-43c2-b9e0-7a847c04abf6"
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "tapg_ml_backtest.png")
plt.savefig(output_path, dpi=300, bbox_inches='tight')
plt.close()

print(f"\nVisualisasi kurva ekuitas berhasil disimpan ke: {output_path}")

# =====================================================================
# 8. REKOMENDASI MODEL TERBAIK
# =====================================================================
best_model_name = max(metrics_summary.keys(), key=lambda k: metrics_summary[k]["Accuracy"])
print(f"\n=== REKOMENDASI QUANT SPECIALIST ===")
print(f"Model Terbaik Berdasarkan Akurasi Out-of-Sample: **{best_model_name}**")
print(f"Akurasi: {metrics_summary[best_model_name]['Accuracy']*100:.2f}%")
print(f"ROC-AUC: {metrics_summary[best_model_name]['ROC-AUC']:.4f}")
print("=========================================")
