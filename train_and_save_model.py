import os
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import joblib

def main():
    print("=== MEMULAI PELATIHAN MODEL LOGISTIC REGRESSION SEDERHANA ===")
    
    # 1. Ingesti Data dari Google Sheet
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1DlWT2btmazXAGRXSVmdrEe2J4niKwJiNGGTs40xOgqE/export?format=csv"
    print(f"Menghubungkan ke Google Sheet: {SHEET_URL}...")
    try:
        df = pd.read_csv(SHEET_URL)
        print("Berhasil mengunduh data!")
        print("Jumlah Baris:", df.shape[0])
    except Exception as e:
        print(f"[ERROR] Gagal mengambil data: {e}")
        return

    # Urutkan secara kronologis
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date').reset_index(drop=True)

    # 2. Rekayasa Fitur Makro & Komoditas (Return Persentase)
    macro_cols = ['WTI_Close', 'Brent_Close', 'Soybean_Close', 'EWM_Close', 'CPO_Close', 'USDIDR_Close']
    for col in macro_cols:
        new_col_name = col.replace('_Close', '_Return')
        df[new_col_name] = df[col].pct_change().replace([np.inf, -np.inf], 0).fillna(0)

    # 3. Rekayasa Fitur Teknikal Sederhana (Sesuai Dashboard Contoh)
    # - Trend MA20
    df['TAPG_MA20'] = df['TAPG_Close'].rolling(window=20).mean()
    # - VWAP 20D: sum(Close * Volume) / sum(Volume) over 20 days
    df['TAPG_VWAP'] = (df['TAPG_Close'] * df['TAPG_Volume']).rolling(window=20).sum() / df['TAPG_Volume'].rolling(window=20).sum()
    # - Volume Harian & Volume MA20 (AVG 20D)
    df['TAPG_Volume_MA20'] = df['TAPG_Volume'].rolling(window=20).mean()
    
    # Tambahan fitur return internal untuk sinyal sensitif harga
    df['TAPG_Return'] = df['TAPG_Close'].pct_change().replace([np.inf, -np.inf], 0).fillna(0)
    df['TAPG_Volume_Change'] = df['TAPG_Volume'].pct_change().replace([np.inf, -np.inf], 0).fillna(0)

    # Prediktor yang digunakan oleh Model
    feature_cols = [
        'WTI_Return', 'Brent_Return', 'Soybean_Return', 'EWM_Return', 'CPO_Return', 'USDIDR_Return',
        'TAPG_MA20', 'TAPG_VWAP', 'TAPG_Volume', 'TAPG_Volume_MA20', 'TAPG_Return', 'TAPG_Volume_Change'
    ]

    # 4. Target Labeling (Prediksi Arah Harian Esok / T+1)
    df['Target'] = (df['TAPG_Return'].shift(-1) > 0).astype(int)

    # Bersihkan NaN hasil kalkulasi rolling window
    df_clean = df.dropna(subset=feature_cols + ['Target']).copy().reset_index(drop=True)
    df_clean = df_clean.replace([np.inf, -np.inf], 0).fillna(0)
    print(f"Data bersih setelah pembersihan: {df_clean.shape[0]} baris")

    # 5. Chronological Split (80% Train, 20% Test)
    split_idx = int(len(df_clean) * 0.8)
    train_df = df_clean.iloc[:split_idx].copy()
    test_df = df_clean.iloc[split_idx:].copy()

    X_train = train_df[feature_cols]
    y_train = train_df['Target']
    X_test = test_df[feature_cols]
    y_test = test_df['Target']

    print(f"- Training range: {train_df['Date'].min().strftime('%Y-%m-%d')} s/d {train_df['Date'].max().strftime('%Y-%m-%d')} ({len(train_df)} baris)")
    print(f"- Testing range: {test_df['Date'].min().strftime('%Y-%m-%d')} s/d {test_df['Date'].max().strftime('%Y-%m-%d')} ({len(test_df)} baris)")

    # 6. Standardisasi Fitur
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # 7. Pelatihan Model Logistic Regression
    model = LogisticRegression(random_state=42)
    model.fit(X_train_scaled, y_train)

    # 8. Evaluasi Performa
    train_acc = model.score(X_train_scaled, y_train)
    test_acc = model.score(X_test_scaled, y_test)
    print(f"Akurasi Data Train: {train_acc * 100:.2f}%")
    print(f"Akurasi Data Test : {test_acc * 100:.2f}%")

    # 9. Menyimpan Model & Scaler
    model_path = os.path.join(os.getcwd(), 'tapg_logistic_regression.joblib')
    scaler_path = os.path.join(os.getcwd(), 'tapg_scaler.joblib')
    
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    
    print(f"Model berhasil disimpan ke: {model_path}")
    print(f"Scaler berhasil disimpan ke: {scaler_path}")
    print("=== SELESAI ===")

if __name__ == '__main__':
    main()
