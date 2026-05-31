import os
import sys
import time
import json
import datetime
import threading
import traceback
import pandas as pd
import numpy as np
import joblib

# Auto-installer untuk pustaka yang diperlukan
try:
    from flask import Flask, jsonify, render_template_string, request
except ImportError:
    print("[INFO] Flask belum terinstall. Menginstal paket via pip...")
    os.system("pip install flask")
    from flask import Flask, jsonify, render_template_string, request

try:
    import yfinance as yf
except ImportError:
    print("[INFO] yfinance belum terinstall. Menginstal paket via pip...")
    os.system("pip install yfinance")
    import yfinance as yf

try:
    import requests
except ImportError:
    print("[INFO] requests belum terinstall. Menginstal paket via pip...")
    os.system("pip install requests")
    import requests

# Inisialisasi Flask
app = Flask(__name__)

# Konfigurasi Path File
BASE_DIR = os.getcwd()
MODEL_PATH = os.path.join(BASE_DIR, 'tapg_logistic_regression.joblib')
SCALER_PATH = os.path.join(BASE_DIR, 'tapg_scaler.joblib')
CACHE_PATH = os.path.join(BASE_DIR, 'latest_prediction.json')
CONFIG_PATH = os.path.join(BASE_DIR, 'dashboard_config.json')
LOG_PATH = os.path.join(BASE_DIR, 'dashboard_logs.txt')

# State & Logs global
system_logs = []

def log_message(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted)
    system_logs.append(formatted)
    if len(system_logs) > 50:
        system_logs.pop(0)
    try:
        with open(LOG_PATH, 'a') as f:
            f.write(formatted + "\n")
    except:
        pass

# Buat file log baru saat startup
try:
    with open(LOG_PATH, 'w') as f:
        f.write("=== LOG STARTUP SYSTEM DASHBOARD TAPG ===\n")
except:
    pass

# ==========================================
# CPO SCRAPER & SINKRONISASI GOOGLE SHEET
# ==========================================
def fetch_cpo_tradingeconomics():
    log_message("[CPO] Mencoba menarik harga CPO alternatif dari Trading Economics...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }
    url = "https://tradingeconomics.com/commodity/palm-oil"
    try:
        import re
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            html = r.text
            # Temukan market_val_box
            match = re.search(r'id="market_val_box"[^>]*>\s*([0-9,.]+)', html)
            if match:
                price_str = match.group(1).replace(',', '')
                price = float(price_str)
                log_message(f"[CPO] Sukses menarik harga dari Trading Economics: MYR {price}")
                return price
            
            # Fallback JSON search
            match = re.search(r'"price":\s*([0-9.]+)', html)
            if match:
                price = float(match.group(1))
                log_message(f"[CPO] Sukses menarik harga dari Trading Economics (Fallback): MYR {price}")
                return price
    except Exception as e:
        log_message(f"[CPO ERROR] Gagal scrape CPO dari Trading Economics: {str(e)}")
    return None

def sync_to_google_sheet(result):
    try:
        if not os.path.exists(CONFIG_PATH):
            log_message("[SHEETS] File konfigurasi belum ada. Lewati sinkronisasi.")
            return
            
        with open(CONFIG_PATH, 'r') as f:
            config_data = json.load(f)
            webhook_url = config_data.get('webhook_url', '')
            
        if not webhook_url:
            log_message("[SHEETS] Webhook URL tidak terkonfigurasi. Silakan isi di dashboard.")
            return
            
        log_message(f"[SHEETS] Mengirim data prediksi ke Google Sheet via Webhook...")
        response = requests.post(
            webhook_url, 
            json=result, 
            headers={"Content-Type": "application/json"}, 
            timeout=12
        )
        if response.status_code == 200:
            res_data = response.json()
            if res_data.get('status') == 'success':
                log_message("[SHEETS SUCCESS] Data sukses disinkronkan ke Google Sheet!")
            else:
                log_message(f"[SHEETS WARNING] Google Sheet menolak data: {res_data.get('message')}")
        else:
            log_message(f"[SHEETS ERROR] Koneksi gagal. HTTP Status: {response.status_code}")
    except Exception as e:
        log_message(f"[SHEETS ERROR] Gagal sinkronisasi ke Google Sheet: {str(e)}")

# ==========================================
# PIPELINE DATA & PREDIKSI
# ==========================================
def fetch_and_predict():
    log_message("Memulai proses penarikan data & prediksi...")
    
    # 1. Validasi Model & Scaler
    if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH):
        raise Exception("File model atau scaler (.joblib) belum tersedia. Harap jalankan 'python train_and_save_model.py' terlebih dahulu.")
        
    model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    log_message("Model & Scaler sukses dimuat.")
    
    # 2. Definisikan Tickers
    tickers = {
        'TAPG': 'TAPG.JK',
        'WTI': 'CL=F',
        'Brent': 'BZ=F',
        'Soybean': 'ZS=F',
        'EWM': 'EWM',
        'CPO': 'KPO=F',      # Ticker CPO Futures utama (CME USD Swap)
        'USDIDR': 'USDIDR=X'
    }
    
    # 3. Penarikan Data (60 Hari Kebelakang untuk Kebutuhan MA20/VWAP)
    raw_data = {}
    for key, ticker in tickers.items():
        log_message(f"Menarik data Yahoo Finance untuk {ticker}...")
        try:
            df_t = yf.download(ticker, period='60d', interval='1d', progress=False)
            if isinstance(df_t.columns, pd.MultiIndex):
                df_t.columns = df_t.columns.get_level_values(0)
            
            if df_t.empty:
                log_message(f"[WARNING] Data {ticker} kosong!")
                raw_data[key] = pd.DataFrame()
            else:
                raw_data[key] = df_t
        except Exception as ex:
            log_message(f"[ERROR] Gagal menarik {ticker}: {str(ex)}")
            raw_data[key] = pd.DataFrame()

    # Validasi TAPG
    tapg_df = raw_data['TAPG']
    if tapg_df.empty:
        raise Exception("Data utama TAPG.JK tidak tersedia di Yahoo Finance! Gagal melakukan sinkronisasi.")
        
    tapg_df = tapg_df.reset_index()
    log_message(f"Data TAPG berhasil didownload. Jumlah baris: {len(tapg_df)}")
    
    # Cek jika CPO (KPO=F) kosong di yfinance, pakai scraper Trading Economics!
    cpo_df = raw_data['CPO']
    if cpo_df.empty or len(cpo_df) < 5:
        log_message("[CPO] Data KPO=F kosong di yfinance. Mencoba alternatif Trading Economics...")
        te_price = fetch_cpo_tradingeconomics()
        if te_price is not None:
            # Buat dummy DataFrame CPO dengan index tanggal TAPG terakhir dan close = te_price
            cpo_dummy = pd.DataFrame(index=raw_data['TAPG'].index)
            cpo_dummy['Close'] = te_price
            raw_data['CPO'] = cpo_dummy
            log_message(f"[CPO] Sukses mengintegrasikan harga Trading Economics (MYR {te_price}) ke data pipeline.")
    
    # 4. Penyelarasan Waktu & Forward-Fill (IDX Sync)
    aligned = pd.DataFrame({'Date': tapg_df['Date']})
    aligned['TAPG_Close'] = tapg_df['Close'].values
    aligned['TAPG_Open'] = tapg_df['Open'].values
    aligned['TAPG_Volume'] = tapg_df['Volume'].values
    aligned['TAPG_High'] = tapg_df['High'].values
    aligned['TAPG_Low'] = tapg_df['Low'].values
    
    # Penggabungan data global makro berbasis tanggal TAPG
    for key in ['WTI', 'Brent', 'Soybean', 'EWM', 'CPO', 'USDIDR']:
        df_m = raw_data[key]
        if not df_m.empty:
            df_m = df_m.reset_index()
            # Hanya ambil Date dan Close
            df_m = df_m[['Date', 'Close']].rename(columns={'Close': f'{key}_Close'})
            aligned = pd.merge(aligned, df_m, on='Date', how='left')
        else:
            aligned[f'{key}_Close'] = np.nan
            
    # Forward-Fill data global yang kosong (libur pasar luar negeri)
    aligned = aligned.sort_values('Date').reset_index(drop=True)
    aligned = aligned.ffill().bfill()
    
    # 5. Fallback Handler Dinamis untuk CPO
    cpo_all_nan = aligned['CPO_Close'].isna().all() or 'CPO_Close' not in aligned.columns
    if cpo_all_nan:
        log_message("[WARNING] Data CPO tidak tersedia! Menerapkan mekanisme fallback dinamis (imputasi Return = 0.0).")
    
    # Hitung Return Harian
    for key in ['WTI', 'Brent', 'Soybean', 'EWM', 'CPO', 'USDIDR']:
        if key == 'CPO' and cpo_all_nan:
            aligned['CPO_Return'] = 0.0
        else:
            aligned[f'{key}_Return'] = aligned[f'{key}_Close'].pct_change().replace([np.inf, -np.inf], 0).fillna(0)
            
    # 6. Perhitungan Fitur Teknikal Sederhana (Persis Dashboard Contoh)
    # - MA20
    aligned['TAPG_MA20'] = aligned['TAPG_Close'].rolling(window=20).mean()
    # - VWAP 20D: sum(Close * Volume) / sum(Volume)
    aligned['TAPG_VWAP'] = (aligned['TAPG_Close'] * aligned['TAPG_Volume']).rolling(window=20).sum() / aligned['TAPG_Volume'].rolling(window=20).sum()
    # - Volume MA20 (AVG 20D)
    aligned['TAPG_Volume_MA20'] = aligned['TAPG_Volume'].rolling(window=20).mean()
    # - Return & Volume Change TAPG
    aligned['TAPG_Return'] = aligned['TAPG_Close'].pct_change().replace([np.inf, -np.inf], 0).fillna(0)
    aligned['TAPG_Volume_Change'] = aligned['TAPG_Volume'].pct_change().replace([np.inf, -np.inf], 0).fillna(0)
    
    # Handle NaN sisa di awal-awal baris rolling window
    aligned = aligned.ffill().bfill()
    
    # 7. Ambil Data Hari Terakhir untuk Prediksi
    latest_row = aligned.iloc[-1]
    latest_date = latest_row['Date'].strftime('%Y-%m-%d')
    log_message(f"Data terakhir yang digunakan untuk prediksi: {latest_date}")
    
    # 8. Ekstraksi Fitur untuk Model
    feature_cols = [
        'WTI_Return', 'Brent_Return', 'Soybean_Return', 'EWM_Return', 'CPO_Return', 'USDIDR_Return',
        'TAPG_MA20', 'TAPG_VWAP', 'TAPG_Volume', 'TAPG_Volume_MA20', 'TAPG_Return', 'TAPG_Volume_Change'
    ]
    
    X_latest = pd.DataFrame([latest_row[feature_cols]])
    
    # Standardisasi & Prediksi
    X_scaled = scaler.transform(X_latest)
    pred = model.predict(X_scaled)[0]
    proba = model.predict_proba(X_scaled)[0]
    
    decision = "BUY" if pred == 1 else "SELL"
    confidence = proba[1] if pred == 1 else proba[0]
    
    # 9. Format Hasil Prediksi & Data Pendukung
    result = {
        'last_sync': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'target_date': latest_date,
        'decision': decision,
        'signal_code': int(pred), # 1 untuk BUY, 0 untuk SELL
        'confidence': float(confidence),
        'tapg_price': {
            'close': float(latest_row['TAPG_Close']),
            'open': float(latest_row['TAPG_Open']),
            'volume': int(latest_row['TAPG_Volume']),
            'high': float(latest_row['TAPG_High']),
            'low': float(latest_row['TAPG_Low']),
            'change_pct': float(latest_row['TAPG_Return'] * 100)
        },
        'raw_prices': {
            'WTI': float(latest_row['WTI_Close']),
            'Brent': float(latest_row['Brent_Close']),
            'Soybean': float(latest_row['Soybean_Close']),
            'EWM': float(latest_row['EWM_Close']),
            'CPO': float(latest_row['CPO_Close']) if not pd.isna(latest_row['CPO_Close']) else 0.0,
            'USDIDR': float(latest_row['USDIDR_Close'])
        },
        'technical': {
            'ma20': float(latest_row['TAPG_MA20']),
            'vwap': float(latest_row['TAPG_VWAP']),
            'volume_ma20': float(latest_row['TAPG_Volume_MA20']),
            'change_pct': float(latest_row['TAPG_Return'] * 100),
            'volume_change_pct': float(latest_row['TAPG_Volume_Change'] * 100)
        },
        'global_sentiment': {
            'CPO': float(latest_row['CPO_Return'] * 100),
            'EWM': float(latest_row['EWM_Return'] * 100),
            'Soybean': float(latest_row['Soybean_Return'] * 100),
            'USDIDR': float(latest_row['USDIDR_Return'] * 100),
            'WTI': float(latest_row['WTI_Return'] * 100),
            'Brent': float(latest_row['Brent_Return'] * 100)
        }
    }
    
    # Simpan hasil ke cache JSON lokal
    with open(CACHE_PATH, 'w') as f:
        json.dump(result, f, indent=4)
        
    log_message(f"Prediksi sukses dihasilkan: {decision} ({confidence*100:.2f}%)")
    
    # 10. Kirim hasil otomatis ke Google Sheet (jika webhook aktif)
    sync_to_google_sheet(result)
    
    return result

# ==========================================
# BACKGROUND SCHEDULER (SETIAP HARI 08:45 WIB)
# ==========================================
def run_scheduler_loop():
    log_message("Scheduler background aktif. Memantau jadwal sinkronisasi harian pukul 08:45 WIB...")
    last_run_date = None
    
    while True:
        try:
            now = datetime.datetime.now()
            current_time_str = now.strftime("%H:%M")
            current_date_str = now.strftime("%Y-%m-%d")
            
            # Jika tepat jam 08:45 WIB dan belum berjalan hari ini
            if current_time_str == "08:45" and last_run_date != current_date_str:
                log_message("--- MEMULAI JADWAL OTOMATIS HARIAN 08:45 WIB ---")
                fetch_and_predict()
                last_run_date = current_date_str
                log_message("Jadwal otomatis harian selesai disinkronisasikan.")
                
        except Exception as e:
            log_message(f"[SCHEDULER ERROR] Terjadi kesalahan: {str(e)}")
            
        time.sleep(30)  # Cek setiap 30 detik

# Jalankan Scheduler di Thread Terpisah
scheduler_thread = threading.Thread(target=run_scheduler_loop, daemon=True)
scheduler_thread.start()

# Load prediksi awal saat server pertama kali diaktifkan
try:
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, 'r') as f:
            log_message("Membaca data prediksi cache terakhir dari JSON.")
    else:
        fetch_and_predict()
except Exception as e:
    log_message(f"[STARTUP WARNING] Gagal sinkronisasi data awal: {str(e)}")

# ==========================================
# ROUTE API & WEB INTERFACE
# ==========================================
@app.route('/api/prediction', methods=['GET'])
def get_prediction():
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, 'r') as f:
                data = json.load(f)
            return jsonify({'success': True, 'data': data, 'logs': system_logs})
        else:
            return jsonify({'success': False, 'message': 'Belum ada data prediksi. Lakukan Force Sync.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sync', methods=['POST'])
def force_sync():
    try:
        result = fetch_and_predict()
        return jsonify({'success': True, 'data': result, 'logs': system_logs})
    except Exception as e:
        log_message(f"[SYNC FAILED] Error manual sync: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e), 'logs': system_logs})

@app.route('/api/logs', methods=['GET'])
def get_logs():
    return jsonify({'logs': system_logs})

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'POST':
        try:
            data = request.json or {}
            webhook_url = data.get('webhook_url', '').strip()
            
            config_data = {}
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r') as f:
                    config_data = json.load(f)
            
            config_data['webhook_url'] = webhook_url
            with open(CONFIG_PATH, 'w') as f:
                json.dump(config_data, f, indent=4)
                
            log_message(f"Webhook Google Sheet berhasil diperbarui: {webhook_url}")
            return jsonify({'success': True, 'message': 'Webhook Google Sheet berhasil disimpan!'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
    else:
        try:
            webhook_url = ""
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r') as f:
                    config_data = json.load(f)
                    webhook_url = config_data.get('webhook_url', '')
            return jsonify({'success': True, 'webhook_url': webhook_url})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

# Single-file HTML/CSS/JS template premium (Switchable Dark/Light Mode + shadcn/ui styled font Inter)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Dashboard TAPG.JK</title>
    <!-- Google Fonts Inter & JetBrains Mono -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <!-- FontAwesome for Icons -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    
    <style>
        :root {
            --bg-app: #fafafa;
            --bg-card: #ffffff;
            --bg-card-hover: #f4f4f5;
            --border-color: #e4e4e7;
            --text-main: #09090b;
            --text-muted: #71717a;
            --accent: #18181b;
            --accent-hover: #27272a;
            --shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
            --header-gradient: linear-gradient(135deg, #18181b, #09090b);
            
            --color-buy: #10b981;
            --color-buy-bg: #ecfdf5;
            --color-sell: #ef4444;
            --color-sell-bg: #fef2f2;
            --color-neut: #6b7280;
            --color-neut-bg: #f3f4f6;
            
            --transition: all 0.2s ease-in-out;
        }
        
        body.dark {
            --bg-app: #09090b;
            --bg-card: #18181b;
            --bg-card-hover: #202024;
            --border-color: #27272a;
            --text-main: #f4f4f5;
            --text-muted: #a1a1aa;
            --accent: #f4f4f5;
            --accent-hover: #e4e4e7;
            --shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -4px rgba(0, 0, 0, 0.4);
            
            --color-buy: #10b981;
            --color-buy-bg: rgba(16, 185, 129, 0.12);
            --color-sell: #ef4444;
            --color-sell-bg: rgba(239, 68, 68, 0.12);
            --color-neut: #9ca3af;
            --color-neut-bg: rgba(156, 163, 175, 0.12);
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-app);
            color: var(--text-main);
            transition: var(--transition);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            padding-bottom: 2rem;
            letter-spacing: -0.01em;
        }
        
        /* HEADER */
        header {
            background: var(--header-gradient);
            color: #ffffff;
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }
        
        .header-title-container {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        
        .live-badge {
            background-color: var(--color-buy);
            color: #09090b;
            font-weight: 700;
            font-size: 0.65rem;
            padding: 0.15rem 0.45rem;
            border-radius: 4px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            display: flex;
            align-items: center;
            gap: 0.25rem;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.03); opacity: 0.85; }
            100% { transform: scale(1); opacity: 1; }
        }
        
        .header-title {
            font-size: 1.1rem;
            font-weight: 700;
            letter-spacing: -0.03em;
            text-transform: uppercase;
        }
        
        .header-title span {
            color: var(--color-buy);
        }
        
        .header-controls {
            display: flex;
            align-items: center;
            gap: 1.5rem;
        }
        
        .clock-container {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.85rem;
            color: rgba(255, 255, 255, 0.8);
            font-family: 'JetBrains Mono', monospace;
        }
        
        .theme-toggle {
            cursor: pointer;
            width: 38px;
            height: 38px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.15);
            background: rgba(255, 255, 255, 0.05);
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            transition: var(--transition);
        }
        
        .theme-toggle:hover {
            background: rgba(255, 255, 255, 0.12);
            transform: translateY(-1px);
        }
        
        /* MAIN DASHBOARD CONTAINER */
        .dashboard-container {
            max-width: 1300px;
            margin: 1.5rem auto;
            width: 100%;
            padding: 0 1.5rem;
            display: grid;
            grid-template-columns: 320px 1fr;
            gap: 1.5rem;
            flex-grow: 1;
        }
        
        @media (max-width: 1024px) {
            .dashboard-container {
                grid-template-columns: 1fr;
            }
        }
        
        /* PANEL LEFT (SENTIMEN GLOBAL) */
        .panel-left {
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
        }
        
        .card {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.25rem;
            box-shadow: var(--shadow);
            transition: var(--transition);
        }
        
        .card:hover {
            border-color: var(--text-muted);
        }
        
        .card-title {
            font-size: 0.75rem;
            text-transform: uppercase;
            font-weight: 700;
            color: var(--text-muted);
            letter-spacing: 0.05em;
            margin-bottom: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .global-grid {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }
        
        .global-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.65rem 0.85rem;
            border-radius: 8px;
            background-color: var(--bg-app);
            border: 1px solid var(--border-color);
            transition: var(--transition);
        }
        
        .global-item:hover {
            background-color: var(--bg-card-hover);
        }
        
        .global-name {
            font-weight: 600;
            font-size: 0.85rem;
        }
        
        .global-name span {
            font-size: 0.7rem;
            color: var(--text-muted);
            font-weight: 400;
            margin-left: 0.25rem;
            display: block;
        }
        
        .global-value {
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
            font-size: 0.85rem;
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
        }
        
        .value-up {
            color: #10b981;
            background-color: rgba(16, 185, 129, 0.08);
        }
        
        .value-down {
            color: #ef4444;
            background-color: rgba(239, 68, 68, 0.08);
        }
        
        /* PANEL RIGHT (MAIN CONTENT) */
        .panel-right {
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
        }
        
        /* SOP DECISION CARD (BUY/SELL) */
        .decision-card {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.75rem;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            position: relative;
            overflow: hidden;
            box-shadow: var(--shadow);
        }
        
        .decision-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 5px;
            height: 100%;
        }
        
        .decision-card.decision-buy {
            background-color: var(--color-buy-bg);
            border-color: rgba(16, 185, 129, 0.25);
        }
        
        .decision-card.decision-buy::before {
            background-color: var(--color-buy);
        }
        
        .decision-card.decision-sell {
            background-color: var(--color-sell-bg);
            border-color: rgba(239, 68, 68, 0.25);
        }
        
        .decision-card.decision-sell::before {
            background-color: var(--color-sell);
        }
        
        .decision-info h2 {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 0.4rem;
        }
        
        .decision-val {
            font-size: 3rem;
            font-weight: 800;
            letter-spacing: -0.04em;
            line-height: 1;
        }
        
        .decision-buy .decision-val {
            color: var(--color-buy);
            text-shadow: 0 0 20px rgba(16, 185, 129, 0.15);
        }
        
        .decision-sell .decision-val {
            color: var(--color-sell);
            text-shadow: 0 0 20px rgba(239, 68, 68, 0.15);
        }
        
        .decision-confidence {
            font-size: 0.85rem;
            font-weight: 600;
            margin-top: 0.5rem;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 0.4rem;
        }
        
        .decision-icon {
            font-size: 3.5rem;
            opacity: 0.12;
        }
        
        /* TAPG PRICE ACTION */
        .price-card {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            align-items: center;
        }
        
        @media (max-width: 640px) {
            .price-card {
                grid-template-columns: 1fr;
                gap: 1rem;
            }
        }
        
        .asset-info h1 {
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: -0.03em;
        }
        
        .asset-info p {
            color: var(--text-muted);
            font-size: 0.85rem;
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: 0.05em;
        }
        
        .price-metrics {
            display: flex;
            justify-content: flex-end;
            gap: 2rem;
            align-items: center;
        }
        
        @media (max-width: 640px) {
            .price-metrics {
                justify-content: flex-start;
            }
        }
        
        .metric-item {
            text-align: right;
        }
        
        @media (max-width: 640px) {
            .metric-item {
                text-align: left;
            }
        }
        
        .metric-label {
            font-size: 0.7rem;
            text-transform: uppercase;
            font-weight: 700;
            color: var(--text-muted);
            letter-spacing: 0.05em;
        }
        
        .metric-value {
            font-size: 2rem;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            letter-spacing: -0.02em;
        }
        
        .metric-subval {
            font-size: 0.8rem;
            font-weight: 600;
            margin-top: 0.15rem;
            display: inline-block;
            padding: 0.1rem 0.35rem;
            border-radius: 4px;
        }
        
        /* TECHNICAL INDICATORS GRID */
        .technical-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 1rem;
        }
        
        @media (max-width: 768px) {
            .technical-grid {
                grid-template-columns: 1fr;
            }
        }
        
        .tech-card {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.25rem;
            box-shadow: var(--shadow);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: 120px;
            transition: var(--transition);
        }
        
        .tech-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.5rem;
        }
        
        .tech-title {
            font-size: 0.7rem;
            text-transform: uppercase;
            font-weight: 700;
            color: var(--text-muted);
            letter-spacing: 0.05em;
        }
        
        .tech-badge {
            font-size: 0.65rem;
            font-weight: 800;
            padding: 0.1rem 0.35rem;
            border-radius: 4px;
            text-transform: uppercase;
        }
        
        .tech-val {
            font-size: 1.5rem;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            letter-spacing: -0.02em;
            margin: 0.2rem 0;
        }
        
        .tech-desc {
            font-size: 0.75rem;
            color: var(--text-muted);
        }
        
        /* SYSTEM LOGS & BUTTON */
        .control-panel {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }
        
        .action-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .sync-btn {
            background-color: var(--text-main);
            color: var(--bg-app);
            border: none;
            border-radius: 8px;
            padding: 0.6rem 1.25rem;
            font-weight: 600;
            font-size: 0.85rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            box-shadow: var(--shadow);
            transition: var(--transition);
        }
        
        .sync-btn:hover {
            opacity: 0.9;
            transform: translateY(-1px);
        }
        
        .sync-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .last-sync-lbl {
            font-size: 0.8rem;
            color: var(--text-muted);
            font-family: 'JetBrains Mono', monospace;
        }
        
        .log-console {
            background-color: #09090b;
            border: 1px solid #27272a;
            border-radius: 8px;
            padding: 0.85rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: #a1a1aa;
            height: 150px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 0.2rem;
        }
        
        .log-line {
            line-height: 1.4;
        }
        
        .log-line.error {
            color: #ef4444;
        }
        
        .log-line.warning {
            color: #fbbf24;
        }
        
        .log-line.success {
            color: #10b981;
        }
        
        /* WEBHOOK INTEGRATION BLOCK */
        .webhook-card {
            margin-top: 0.25rem;
        }
        
        .webhook-input {
            width: 100%;
            padding: 0.5rem 0.75rem;
            border-radius: 6px;
            border: 1px solid var(--border-color);
            background-color: var(--bg-app);
            color: var(--text-main);
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            outline: none;
            transition: var(--transition);
        }
        
        .webhook-input:focus {
            border-color: var(--text-main);
        }
    </style>
</head>
<body class="dark">

    <header>
        <div class="header-title-container">
            <h1 class="header-title">TRADING DASHBOARD <span>TAPG.JK</span></h1>
            <div class="live-badge">
                <i class="fa-solid fa-circle" style="font-size: 5px;"></i> Palm Oil Live
            </div>
        </div>
        
        <div class="header-controls">
            <div class="clock-container">
                <i class="fa-regular fa-clock"></i>
                <span id="live-clock">00:00:00 WIB</span>
            </div>
            
            <div class="theme-toggle" id="theme-btn" title="Ubah Tema">
                <i class="fa-solid fa-sun" id="theme-icon"></i>
            </div>
        </div>
    </header>

    <main class="dashboard-container">
        
        <!-- PANEL KIRI: SENTIMEN GLOBAL -->
        <section class="panel-left">
            <div class="card" style="flex-grow: 1;">
                <div class="card-title">
                    <span>Global Sentiment</span>
                    <i class="fa-solid fa-globe" style="color: var(--text-muted);"></i>
                </div>
                
                <div class="global-grid" id="global-sentiment-list">
                    <div style="text-align: center; color: var(--text-muted); padding: 2rem 0;">
                        <i class="fa-solid fa-spinner fa-spin" style="font-size: 1.25rem; margin-bottom: 0.5rem;"></i>
                        <p>Mengambil Data Makro...</p>
                    </div>
                </div>
            </div>
            
            <!-- GOOGLE SHEETS WEBHOOK SETTINGS -->
            <div class="card webhook-card">
                <div class="card-title">
                    <span>Google Sheet Sync</span>
                    <i class="fa-solid fa-table" style="color: var(--text-muted);"></i>
                </div>
                <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                    <div style="font-size: 0.75rem; color: var(--text-muted); line-height: 1.4;">
                        Tempel URL Web App dari Google Apps Script Anda untuk sinkronisasi otomatis harian:
                    </div>
                    <input type="text" id="webhook-input" class="webhook-input" placeholder="https://script.google.com/macros/s/.../exec">
                    <button id="save-webhook-btn" class="sync-btn" style="width: 100%; justify-content: center; font-size: 0.75rem; padding: 0.45rem;">
                        <i class="fa-solid fa-floppy-disk"></i> Simpan Konfigurasi
                    </button>
                </div>
            </div>
        </section>
        
        <!-- PANEL KANAN: UTAMA -->
        <section class="panel-right">
            
            <!-- SOP DECISION -->
            <div class="decision-card decision-buy" id="sop-decision-card">
                <div class="decision-info">
                    <h2>SOP Decision</h2>
                    <div class="decision-val" id="sop-decision-val">BUY</div>
                    <div class="decision-confidence" id="sop-confidence">
                        <i class="fa-solid fa-shield-halved"></i> Confidence: 0.0%
                    </div>
                </div>
                <div class="decision-icon" id="sop-decision-icon">
                    <i class="fa-solid fa-arrow-trend-up" style="color: var(--color-buy);"></i>
                </div>
            </div>
            
            <!-- TAPG PRICE DISPLAY -->
            <div class="card price-card">
                <div class="asset-info">
                    <p>Palm Oil Sector • IDX</p>
                    <h1>TAPG</h1>
                    <p style="color: var(--text-muted); font-size: 0.75rem; margin-top: 0.2rem;">Triputra Agro Persada</p>
                </div>
                
                <div class="price-metrics">
                    <div class="metric-item">
                        <div class="metric-label">Close Price</div>
                        <div class="metric-value" id="price-close">Rp 0</div>
                        <div class="metric-subval" id="price-change">0.00%</div>
                    </div>
                    <div class="metric-item">
                        <div class="metric-label">Open Price</div>
                        <div class="metric-value" id="price-open" style="color: var(--text-muted); font-size: 1.5rem;">Rp 0</div>
                    </div>
                </div>
            </div>
            
            <!-- TECHNICALS GRID -->
            <div class="technical-grid">
                
                <!-- VOLUME FLOW -->
                <div class="tech-card" style="border-color: rgba(16, 185, 129, 0.2);">
                    <div class="tech-header">
                        <span class="tech-title">Volume Flow</span>
                        <span class="tech-badge" id="vol-flow-badge" style="background-color: var(--color-buy-bg); color: var(--color-buy);">BUY</span>
                    </div>
                    <div class="tech-val" id="vol-val">0</div>
                    <div class="tech-desc" id="vol-avg">AVG 20D: 0</div>
                </div>
                
                <!-- TREND MA20 -->
                <div class="tech-card" id="trend-card" style="border-color: rgba(239, 68, 68, 0.2);">
                    <div class="tech-header">
                        <span class="tech-title">Trend [MA20]</span>
                        <span class="tech-badge" id="trend-badge" style="background-color: var(--color-sell-bg); color: var(--color-sell);">SELL</span>
                    </div>
                    <div class="tech-val" id="trend-ma20">Rp 0</div>
                    <div class="tech-desc">Value Baseline</div>
                </div>
                
                <!-- VWAP 20D -->
                <div class="tech-card" id="vwap-card" style="border-color: rgba(239, 68, 68, 0.2);">
                    <div class="tech-header">
                        <span class="tech-title">VWAP (20D)</span>
                        <span class="tech-badge" id="vwap-badge" style="background-color: var(--color-sell-bg); color: var(--color-sell);">SELL</span>
                    </div>
                    <div class="tech-val" id="vwap-val">Rp 0</div>
                    <div class="tech-desc">Volume Weighted Baseline</div>
                </div>
                
            </div>
            
            <!-- LOGS & CONTROLS -->
            <div class="control-panel">
                <div class="action-bar">
                    <button class="sync-btn" id="sync-btn">
                        <i class="fa-solid fa-arrows-rotate" id="sync-icon"></i> Force Sync Now
                    </button>
                    <span class="last-sync-lbl" id="last-sync-time">LAST SYNC: -</span>
                </div>
                
                <div class="log-console" id="log-console">
                    <!-- Log harian diinput via JS -->
                </div>
            </div>
            
        </section>
        
    </main>

    <script>
        // DOM Elements
        const bodyEl = document.body;
        const themeBtn = document.getElementById('theme-btn');
        const themeIcon = document.getElementById('theme-icon');
        const liveClockEl = document.getElementById('live-clock');
        const syncBtn = document.getElementById('sync-btn');
        const syncIcon = document.getElementById('sync-icon');
        const logConsole = document.getElementById('log-console');
        const webhookInput = document.getElementById('webhook-input');
        const saveWebhookBtn = document.getElementById('save-webhook-btn');
        
        // Dark/Light Theme Handler
        themeBtn.addEventListener('click', () => {
            if (bodyEl.classList.contains('dark')) {
                bodyEl.classList.remove('dark');
                themeIcon.className = "fa-solid fa-moon";
            } else {
                bodyEl.classList.add('dark');
                themeIcon.className = "fa-solid fa-sun";
            }
        });
        
        // Real-Time Clock Jakarta (WIB)
        function updateClock() {
            const options = {
                timeZone: 'Asia/Jakarta',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false
            };
            const formatter = new Intl.DateTimeFormat('id-ID', options);
            liveClockEl.innerText = formatter.format(new Date()) + " WIB";
        }
        setInterval(updateClock, 1000);
        updateClock();
        
        // Membaca Prediksi
        async function fetchPrediction() {
            try {
                const response = await fetch('/api/prediction');
                const result = await response.json();
                if (result.success) {
                    updateUI(result.data);
                    updateLogs(result.logs);
                } else {
                    console.error("Gagal menarik data:", result.message);
                }
            } catch (err) {
                console.error("Koneksi gagal:", err);
            }
        }
        
        // Membaca Konfigurasi Webhook
        async function fetchConfig() {
            try {
                const response = await fetch('/api/config');
                const result = await response.json();
                if (result.success && result.webhook_url) {
                    webhookInput.value = result.webhook_url;
                }
            } catch (err) {
                console.error("Gagal menarik konfigurasi:", err);
            }
        }
        
        // Menyimpan Webhook Google Sheets
        saveWebhookBtn.addEventListener('click', async () => {
            saveWebhookBtn.disabled = true;
            const webhookUrl = webhookInput.value.trim();
            
            try {
                const response = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ webhook_url: webhookUrl })
                });
                const result = await response.json();
                if (result.success) {
                    alert("Sukses! " + result.message);
                } else {
                    alert("Gagal: " + result.message);
                }
            } catch (err) {
                alert("Gagal menyimpan konfigurasi.");
            } finally {
                saveWebhookBtn.disabled = false;
            }
        });
        
        // Manual Override Sync
        syncBtn.addEventListener('click', async () => {
            syncBtn.disabled = true;
            syncIcon.classList.add('fa-spin');
            
            const logLine = document.createElement('div');
            logLine.className = "log-line success";
            logLine.innerText = `[${new Date().toLocaleTimeString()}] Mengirim instruksi sinkronisasi paksa ke backend server...`;
            logConsole.appendChild(logLine);
            logConsole.scrollTop = logConsole.scrollHeight;
            
            try {
                const response = await fetch('/api/sync', { method: 'POST' });
                const result = await response.json();
                if (result.success) {
                    updateUI(result.data);
                    updateLogs(result.logs);
                } else {
                    alert("Error Sync: " + result.message);
                }
            } catch (err) {
                alert("Gagal melakukan sync, pastikan Python server sedang aktif.");
            } finally {
                syncBtn.disabled = false;
                syncIcon.classList.remove('fa-spin');
            }
        });
        
        // Update Logs di Console
        function updateLogs(logs) {
            logConsole.innerHTML = "";
            logs.forEach(log => {
                const line = document.createElement('div');
                line.className = "log-line";
                if (log.includes("[ERROR]")) line.classList.add("error");
                else if (log.includes("[WARNING]")) line.classList.add("warning");
                else if (log.includes("sukses") || log.includes("Berhasil") || log.includes("SUCCESS")) line.classList.add("success");
                
                line.innerText = log;
                logConsole.appendChild(line);
            });
            logConsole.scrollTop = logConsole.scrollHeight;
        }
        
        // Format Angka Ribuan
        function formatNumber(num) {
            return new Intl.NumberFormat('id-ID').format(num);
        }
        
        // Format Desimal Rupiah
        function formatRupiah(num) {
            return "Rp " + new Intl.NumberFormat('id-ID', { minimumFractionDigits: 1, maximumFractionDigits: 2 }).format(num);
        }
        
        // Update Elemen Tampilan UI
        function updateUI(data) {
            document.getElementById('last-sync-time').innerText = `LAST SYNC: ${data.last_sync}`;
            
            // SOP Decision Card
            const decCard = document.getElementById('sop-decision-card');
            const decVal = document.getElementById('sop-decision-val');
            const decConf = document.getElementById('sop-confidence');
            const decIcon = document.getElementById('sop-decision-icon');
            
            decVal.innerText = data.decision;
            decConf.innerHTML = `<i class="fa-solid fa-shield-halved"></i> Confidence: ${(data.confidence * 100).toFixed(1)}%`;
            
            if (data.decision === "BUY") {
                decCard.className = "decision-card decision-buy";
                decIcon.innerHTML = `<i class="fa-solid fa-arrow-trend-up" style="color: var(--color-buy);"></i>`;
            } else {
                decCard.className = "decision-card decision-sell";
                decIcon.innerHTML = `<i class="fa-solid fa-arrow-trend-down" style="color: var(--color-sell);"></i>`;
            }
            
            // TAPG Prices
            document.getElementById('price-close').innerText = "Rp " + formatNumber(data.tapg_price.close);
            document.getElementById('price-open').innerText = "Rp " + formatNumber(data.tapg_price.open);
            
            const pctChangeEl = document.getElementById('price-change');
            const changeVal = data.tapg_price.change_pct;
            pctChangeEl.innerText = (changeVal >= 0 ? "+" : "") + changeVal.toFixed(2) + "%";
            pctChangeEl.className = "metric-subval " + (changeVal >= 0 ? "value-up" : "value-down");
            
            // Global Sentiment List
            const sentimentList = document.getElementById('global-sentiment-list');
            sentimentList.innerHTML = "";
            
            const mappingNames = {
                'CPO': 'Crude Palm Oil (Futures)',
                'EWM': 'MSCI Malaysia (ETF)',
                'Soybean': 'Soybean (Futures)',
                'USDIDR': 'USD / IDR (Kurs)',
                'WTI': 'WTI Crude Oil (Futures)',
                'Brent': 'Brent Crude Oil (Futures)'
            };
            
            Object.keys(data.global_sentiment).forEach(key => {
                const item = document.createElement('div');
                item.className = "global-item";
                
                const returnVal = data.global_sentiment[key];
                const sign = returnVal >= 0 ? "+" : "";
                const valClass = returnVal >= 0 ? "value-up" : "value-down";
                
                item.innerHTML = `
                    <div class="global-name">
                        ${key} <span>${mappingNames[key] || ''}</span>
                    </div>
                    <div class="global-value ${valClass}">
                        ${sign}${returnVal.toFixed(2)}%
                    </div>
                `;
                sentimentList.appendChild(item);
            });
            
            // Volume Flow Tech Card
            document.getElementById('vol-val').innerText = formatNumber(data.tapg_price.volume);
            document.getElementById('vol-avg').innerText = `AVG 20D: ${formatNumber(Math.round(data.technical.volume_ma20))}`;
            
            const volBadge = document.getElementById('vol-flow-badge');
            if (data.tapg_price.volume > data.technical.volume_ma20) {
                volBadge.innerText = "BUY";
                volBadge.style.backgroundColor = "var(--color-buy-bg)";
                volBadge.style.color = "var(--color-buy)";
            } else {
                volBadge.innerText = "SELL";
                volBadge.style.backgroundColor = "var(--color-sell-bg)";
                volBadge.style.color = "var(--color-sell)";
            }
            
            // Trend MA20 Tech Card
            document.getElementById('trend-ma20').innerText = formatRupiah(data.technical.ma20);
            const trendBadge = document.getElementById('trend-badge');
            if (data.tapg_price.close > data.technical.ma20) {
                trendBadge.innerText = "BUY";
                trendBadge.style.backgroundColor = "var(--color-buy-bg)";
                trendBadge.style.color = "var(--color-buy)";
            } else {
                trendBadge.innerText = "SELL";
                trendBadge.style.backgroundColor = "var(--color-sell-bg)";
                trendBadge.style.color = "var(--color-sell)";
            }
            
            // VWAP Tech Card
            document.getElementById('vwap-val').innerText = formatRupiah(data.technical.vwap);
            const vwapBadge = document.getElementById('vwap-badge');
            if (data.tapg_price.close > data.technical.vwap) {
                vwapBadge.innerText = "BUY";
                vwapBadge.style.backgroundColor = "var(--color-buy-bg)";
                vwapBadge.style.color = "var(--color-buy)";
            } else {
                vwapBadge.innerText = "SELL";
                vwapBadge.style.backgroundColor = "var(--color-sell-bg)";
                vwapBadge.style.color = "var(--color-sell)";
            }
        }
        
        // Startup Fetch
        fetchPrediction();
        fetchConfig();
        
        // Auto Polling Logs & Cache setiap 15 detik
        setInterval(fetchPrediction, 15000);
        
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def index():
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    log_message("=== MEMULAI DASHBOARD TRADING SERVER ===")
    app.run(host='127.0.0.1', port=5000, debug=False)
