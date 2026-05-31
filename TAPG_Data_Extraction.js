/**
 * Google Apps Script - Yahoo Finance Data Extraction & Synchronization Pipeline
 * 
 * Deskripsi:
 * Skrip ini mengekstrak data historis harian dari Yahoo Finance untuk saham TAPG.JK 
 * dan instrumen global pendukung (WTI, Brent, Soybean, CPO, EWM, USD/IDR).
 * Data disinkronisasikan menggunakan tanggal perdagangan TAPG.JK sebagai jangkar utama (Master Date)
 * dan menerapkan mekanisme Forward-Fill untuk menyelaraskan hari libur pasar global.
 * 
 * Cara Penggunaan:
 * 1. Buka Google Sheets Anda.
 * 2. Klik menu 'Ekstensi' (Extensions) -> 'Apps Script'.
 * 3. Hapus kode bawaan di file `Code.gs` dan tempelkan (paste) seluruh kode ini.
 * 4. Simpan proyek dengan menekan ikon Disket (Ctrl + S).
 * 5. Pilih fungsi `runTAPGDataPipeline` di menu dropdown atas, lalu klik 'Jalankan' (Run).
 * 6. Berikan izin akses (authorization) jika diminta oleh Google.
 * 
 * @author Data Engineer Specialist
 * @version 1.0.0
 */

// ==========================================
// 1. KONFIGURASI PIPELINE DATA
// ==========================================
var CONFIG = {
  // Rentang Tanggal Target Penulisan (Format: YYYY-MM-DD)
  TARGET_START_DATE: "2024-01-01",
  TARGET_END_DATE: "2026-05-31",
  
  // Tanggal awal penarikan API (diberi buffer sejak Des 2023 agar Forward-Fill memiliki harga awal)
  FETCH_START_DATE: "2023-12-01",
  
  // Ticker Yahoo Finance yang akan diekstrak
  TICKERS: {
    TAPG: "TAPG.JK",       // Triputra Agro Persada (Anchor/Master Date)
    WTI: "CL=F",           // WTI Crude Oil Futures
    BRENT: "BZ=F",         // Brent Crude Oil Futures
    SOYBEAN: "ZS=F",       // Soybean Futures
    EWM: "EWM",            // iShares MSCI Malaysia ETF
    CPO: "FCPO=F",         // Crude Palm Oil Futures
    USDIDR: "USDIDR=X"     // Kurs USD/IDR
  },
  
  // URL spreadsheet cadangan jika dijalankan secara standalone (di luar spreadsheet aktif)
  GOOGLE_SHEET_URL: "https://docs.google.com/spreadsheets/d/1sqUGXsJbkZJ4PUviqjpUI-G0YetvZpTkZlexJbfmhm0/edit"
};

// ==========================================
// 2. FUNGSI UTAMA (MAIN ENTRY POINT)
// ==========================================
function runTAPGDataPipeline() {
  var startTime = new Date().getTime();
  Logger.log("=== MEMULAI EKSTRAKSI DATA YAHOO FINANCE ===");
  
  // A. Konversi tanggal konfigurasi ke Unix Timestamp (Detik)
  var period1 = dateToUnixTimestamp(CONFIG.FETCH_START_DATE);
  var period2 = dateToUnixTimestamp(CONFIG.TARGET_END_DATE);
  
  Logger.log("Rentang Penarikan API: " + CONFIG.FETCH_START_DATE + " sampai " + CONFIG.TARGET_END_DATE);
  Logger.log("Rentang Output Sheet : " + CONFIG.TARGET_START_DATE + " sampai " + CONFIG.TARGET_END_DATE);
  
  // B. Ekstraksi Data dari API Yahoo Finance
  Logger.log("1. Menarik data utama TAPG.JK (Anchor)...");
  var tapgData = fetchYahooFinanceData(CONFIG.TICKERS.TAPG, period1, period2);
  if (!tapgData || Object.keys(tapgData).length === 0) {
    throw new Error("Gagal mengambil data TAPG.JK. Proses dihentikan.");
  }
  
  Logger.log("2. Menarik data instrumen global pendukung...");
  var wtiData = fetchYahooFinanceData(CONFIG.TICKERS.WTI, period1, period2) || {};
  var brentData = fetchYahooFinanceData(CONFIG.TICKERS.BRENT, period1, period2) || {};
  var soybeanData = fetchYahooFinanceData(CONFIG.TICKERS.SOYBEAN, period1, period2) || {};
  var ewmData = fetchYahooFinanceData(CONFIG.TICKERS.EWM, period1, period2) || {};
  var cpoData = fetchYahooFinanceData(CONFIG.TICKERS.CPO, period1, period2) || {};
  var usdidrData = fetchYahooFinanceData(CONFIG.TICKERS.USDIDR, period1, period2) || {};
  
  // C. Sinkronisasi Data & Forward-Fill
  Logger.log("3. Menyelaraskan data berdasarkan tanggal TAPG.JK (Master Date) & Forward-Fill...");
  var sortedDates = Object.keys(tapgData).sort();
  var rowData = [];
  
  // State penyimpanan harga terakhir (untuk forward-fill)
  var state = {
    TAPG: { close: null, volume: null, high: null, low: null },
    WTI: null,
    Brent: null,
    Soybean: null,
    EWM: null,
    CPO: null,
    USDIDR: null
  };
  
  for (var i = 0; i < sortedDates.length; i++) {
    var dateStr = sortedDates[i];
    
    // Update State TAPG
    var tapg = tapgData[dateStr];
    if (tapg) {
      if (isValidNumber(tapg.close)) state.TAPG.close = cleanAndRoundValue(tapg.close);
      if (isValidNumber(tapg.volume)) state.TAPG.volume = cleanAndRoundValue(tapg.volume);
      if (isValidNumber(tapg.high)) state.TAPG.high = cleanAndRoundValue(tapg.high);
      if (isValidNumber(tapg.low)) state.TAPG.low = cleanAndRoundValue(tapg.low);
    }
    
    // Update State Instrumen Global (Forward-Fill jika data kosong/tutup)
    if (wtiData[dateStr] && isValidNumber(wtiData[dateStr].close)) state.WTI = cleanAndRoundValue(wtiData[dateStr].close);
    if (brentData[dateStr] && isValidNumber(brentData[dateStr].close)) state.Brent = cleanAndRoundValue(brentData[dateStr].close);
    if (soybeanData[dateStr] && isValidNumber(soybeanData[dateStr].close)) state.Soybean = cleanAndRoundValue(soybeanData[dateStr].close);
    if (ewmData[dateStr] && isValidNumber(ewmData[dateStr].close)) state.EWM = cleanAndRoundValue(ewmData[dateStr].close);
    if (cpoData[dateStr] && isValidNumber(cpoData[dateStr].close)) state.CPO = cleanAndRoundValue(cpoData[dateStr].close);
    if (usdidrData[dateStr] && isValidNumber(usdidrData[dateStr].close)) state.USDIDR = cleanAndRoundValue(usdidrData[dateStr].close);
    
    // Masukkan data jika masuk dalam rentang target output
    if (dateStr >= CONFIG.TARGET_START_DATE && dateStr <= CONFIG.TARGET_END_DATE) {
      rowData.push([
        dateStr,
        state.TAPG.close !== null ? state.TAPG.close : "",
        state.TAPG.volume !== null ? state.TAPG.volume : 0,
        state.TAPG.high !== null ? state.TAPG.high : "",
        state.TAPG.low !== null ? state.TAPG.low : "",
        state.WTI !== null ? state.WTI : "",
        state.Brent !== null ? state.Brent : "",
        state.Soybean !== null ? state.Soybean : "",
        state.EWM !== null ? state.EWM : "",
        state.CPO !== null ? state.CPO : "",
        state.USDIDR !== null ? state.USDIDR : ""
      ]);
    }
  }
  
  // D. Penulisan Bulk ke Google Sheets
  Logger.log("4. Menyambungkan ke Google Sheets...");
  var ss = getSpreadsheetConnection();
  var sheet = ss.getSheets()[0]; // Menggunakan Sheet pertama (index 0)
  
  Logger.log("5. Membersihkan data lama di Sheet...");
  sheet.clear(); // Menghapus seluruh isi & format sel agar fresh
  
  Logger.log("6. Melakukan Bulk Write...");
  var headers = [
    "Date", 
    "TAPG_Close", 
    "TAPG_Volume", 
    "TAPG_High", 
    "TAPG_Low", 
    "WTI_Close", 
    "Brent_Close", 
    "Soybean_Close", 
    "EWM_Close", 
    "CPO_Close", 
    "USDIDR_Close"
  ];
  
  var finalOutput = [headers].concat(rowData);
  
  if (rowData.length > 0) {
    // Tulis sekaligus menggunakan setValues() untuk performa kilat
    sheet.getRange(1, 1, finalOutput.length, headers.length).setValues(finalOutput);
    
    // Opsional: Memformat kolom tanggal dan mempercantik header
    sheet.getRange(1, 1, 1, headers.length)
         .setFontWeight("bold")
         .setBackground("#1e293b")
         .setFontColor("#ffffff")
         .setHorizontalAlignment("center");
    
    sheet.getRange(2, 1, rowData.length, 1).setHorizontalAlignment("center");
    
    // Auto-fit lebar kolom agar rapi
    for (var col = 1; col <= headers.length; col++) {
      sheet.autoResizeColumn(col);
    }
    
    var endTime = new Date().getTime();
    var duration = ((endTime - startTime) / 1000).toFixed(2);
    Logger.log("=== INTEGRASI SELESAI! ===");
    Logger.log("Total Baris Berhasil Ditulis: " + rowData.length);
    Logger.log("Durasi Eksekusi: " + duration + " detik");
  } else {
    Logger.log("[WARNING] Tidak ada baris data yang dihasilkan dalam rentang tanggal target.");
  }
}

// ==========================================
// 3. FUNGSI LAYANAN PENDUKUNG (HELPERS)
// ==========================================

/**
 * Mengambil data historis instrumen dari API Yahoo Finance
 * @param {string} ticker - Simbol instrumen (misal: TAPG.JK)
 * @param {number} period1 - Timestamp awal (Unix)
 * @param {number} period2 - Timestamp akhir (Unix)
 * @returns {Object} Peta data yang diindeks berdasarkan tanggal ("YYYY-MM-DD")
 */
function fetchYahooFinanceData(ticker, period1, period2) {
  var url = "https://query1.finance.yahoo.com/v8/finance/chart/" + encodeURIComponent(ticker) + 
            "?period1=" + period1 + "&period2=" + period2 + "&interval=1d";
  
  var options = {
    "muteHttpExceptions": true,
    "headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
  };
  
  try {
    var response = UrlFetchApp.fetch(url, options);
    var responseCode = response.getResponseCode();
    
    if (responseCode !== 200) {
      Logger.log("[ERROR] HTTP " + responseCode + " saat menarik ticker: " + ticker);
      return null;
    }
    
    var json = JSON.parse(response.getContentText());
    if (!json.chart || !json.chart.result || json.chart.result.length === 0) {
      Logger.log("[ERROR] Format JSON tidak valid atau data kosong untuk ticker: " + ticker);
      return null;
    }
    
    var result = json.chart.result[0];
    var timestamps = result.timestamp;
    if (!timestamps || timestamps.length === 0) {
      Logger.log("[WARNING] Tidak ada timestamp data untuk ticker: " + ticker);
      return null;
    }
    
    var quotes = result.indicators.quote[0];
    var closeList = quotes.close || [];
    var volumeList = quotes.volume || [];
    var highList = quotes.high || [];
    var lowList = quotes.low || [];
    
    var dataMap = {};
    for (var i = 0; i < timestamps.length; i++) {
      var dateStr = unixTimestampToYYYYMMDD(timestamps[i]);
      dataMap[dateStr] = {
        close: closeList[i],
        volume: volumeList[i],
        high: highList[i],
        low: lowList[i]
      };
    }
    
    return dataMap;
  } catch (e) {
    Logger.log("[EXCEPTION] Error saat memproses ticker " + ticker + ": " + e.toString());
    return null;
  }
}

/**
 * Mengubah string tanggal YYYY-MM-DD ke Unix Timestamp (dalam detik UTC)
 * @param {string} dateString - Tanggal format "YYYY-MM-DD"
 * @returns {number} Unix Timestamp
 */
function dateToUnixTimestamp(dateString) {
  var parts = dateString.split("-");
  // Menggunakan Date.UTC agar konsisten di seluruh zona waktu server Google
  var date = new Date(Date.UTC(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10)));
  return Math.floor(date.getTime() / 1000);
}

/**
 * Mengubah Unix Timestamp (dalam detik) menjadi format tanggal YYYY-MM-DD UTC
 * @param {number} timestamp - Unix Timestamp
 * @returns {string} Tanggal terformat YYYY-MM-DD
 */
function unixTimestampToYYYYMMDD(timestamp) {
  var date = new Date(timestamp * 1000);
  var year = date.getUTCFullYear();
  var month = ("0" + (date.getUTCMonth() + 1)).slice(-2);
  var day = ("0" + date.getUTCDate()).slice(-2);
  return year + "-" + month + "-" + day;
}

/**
 * Memvalidasi apakah suatu nilai adalah angka yang valid atau string numerik yang valid (bukan null, undefined, atau NaN)
 * @param {*} value - Nilai yang akan dicek
 * @returns {boolean} True jika angka valid atau dapat dikonversi ke angka valid
 */
function isValidNumber(value) {
  if (value === null || value === undefined || value === "") return false;
  var num = Number(value);
  return !isNaN(num) && isFinite(num);
}

/**
 * Membersihkan nilai, memastikan bertipe numerik, dan membulatkan maksimal 3 digit desimal jika ada koma.
 * @param {*} value - Nilai mentah
 * @returns {number|string} Nilai numerik bersih terformat desimal maks 3 digit
 */
function cleanAndRoundValue(value) {
  if (value === null || value === undefined || value === "") return "";
  var num = Number(value);
  if (isNaN(num) || !isFinite(num)) return "";
  
  // Jika desimal, bulatkan maksimal ke 3 tempat desimal
  if (num % 1 !== 0) {
    return Math.round(num * 1000) / 1000;
  }
  return num;
}

/**
 * Mengambil koneksi Google Sheets baik secara container-bound maupun standalone
 * @returns {Spreadsheet} Objek Spreadsheet aktif atau dari URL
 */
function getSpreadsheetConnection() {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    if (ss) return ss;
  } catch (e) {
    // Abaikan jika tidak berjalan di script yang terikat dengan spreadsheet
  }
  
  if (CONFIG.GOOGLE_SHEET_URL) {
    return SpreadsheetApp.openByUrl(CONFIG.GOOGLE_SHEET_URL);
  }
  
  throw new Error("Koneksi Spreadsheet gagal. Harap jalankan kode langsung dari Google Sheet atau lengkapi CONFIG.GOOGLE_SHEET_URL.");
}

// ==========================================
// 8. WEBHOOK PENERIMA DATA PREDIKSI DARI PYTHON
// ==========================================
/**
 * Fungsi ini bertindak sebagai Webhook Web App untuk menerima data dari Python server.
 * Data yang masuk akan disimpan ke tiga sheet: Sheet1 (Raw), Sheet2 (Delta), Sheet3 (Prediction)
 */
function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var ss = getSpreadsheetConnection();
    
    // ----------------------------------------------------
    // TAB 1: Sheet1 (Raw Data - Data Mentah)
    // ----------------------------------------------------
    var sheet1 = ss.getSheetByName("Sheet1");
    if (sheet1) {
      if (sheet1.getLastRow() === 0) {
        sheet1.appendRow([
          "Date", "TAPG_Close", "TAPG_Open", "TAPG_Volume", "TAPG_High", "TAPG_Low", 
          "WTI_Close", "Brent_Close", "Soybean_Close", "EWM_Close", "CPO_Close", "USDIDR_Close"
        ]);
        formatHeaderRow(sheet1, 12);
      }
      
      sheet1.appendRow([
        data.target_date,
        data.tapg_price.close,
        data.tapg_price.open,
        data.tapg_price.volume,
        data.tapg_price.high,
        data.tapg_price.low,
        data.raw_prices.WTI,
        data.raw_prices.Brent,
        data.raw_prices.Soybean,
        data.raw_prices.EWM,
        data.raw_prices.CPO,
        data.raw_prices.USDIDR
      ]);
    }
    
    // ----------------------------------------------------
    // TAB 2: Sheet2 (Delta Calculations - Return & Indikator)
    // ----------------------------------------------------
    var sheet2 = ss.getSheetByName("Sheet2");
    if (sheet2) {
      if (sheet2.getLastRow() === 0) {
        sheet2.appendRow([
          "Date", "WTI_Return", "Brent_Return", "Soybean_Return", "EWM_Return", "CPO_Return", "USDIDR_Return",
          "TAPG_MA20", "TAPG_VWAP", "TAPG_Volume_MA20", "TAPG_Return", "TAPG_Volume_Change"
        ]);
        formatHeaderRow(sheet2, 12);
      }
      
      sheet2.appendRow([
        data.target_date,
        cleanAndRoundValue(data.global_sentiment.WTI / 100),
        cleanAndRoundValue(data.global_sentiment.Brent / 100),
        cleanAndRoundValue(data.global_sentiment.Soybean / 100),
        cleanAndRoundValue(data.global_sentiment.EWM / 100),
        cleanAndRoundValue(data.global_sentiment.CPO / 100),
        cleanAndRoundValue(data.global_sentiment.USDIDR / 100),
        cleanAndRoundValue(data.technical.ma20),
        cleanAndRoundValue(data.technical.vwap),
        cleanAndRoundValue(data.technical.volume_ma20),
        cleanAndRoundValue(data.technical.change_pct / 100),
        cleanAndRoundValue(data.technical.volume_change_pct / 100)
      ]);
      
      // Auto-format Kolom Persentase di Sheet2 (Kolom B s/d G, dan Kolom K s/d L)
      var lastRow2 = sheet2.getLastRow();
      sheet2.getRange(lastRow2, 2, 1, 6).setNumberFormat("0.00%");
      sheet2.getRange(lastRow2, 11, 1, 2).setNumberFormat("0.00%");
    }
    
    // ----------------------------------------------------
    // TAB 3: Sheet3 (Prediction Signals - Sinyal & Keputusan)
    // ----------------------------------------------------
    var sheet3 = ss.getSheetByName("Sheet3");
    if (sheet3) {
      if (sheet3.getLastRow() === 0) {
        sheet3.appendRow([
          "Date", "Signal_Code", "Decision", "Confidence", "Last_Sync"
        ]);
        formatHeaderRow(sheet3, 5);
      }
      
      sheet3.appendRow([
        data.target_date,
        data.signal_code, // 1 untuk BUY, 0 untuk SELL
        data.decision,    // "BUY" atau "SELL"
        cleanAndRoundValue(data.confidence),
        data.last_sync
      ]);
      
      var lastRow3 = sheet3.getLastRow();
      sheet3.getRange(lastRow3, 4).setNumberFormat("0.0%");
    }
    
    return ContentService.createTextOutput(JSON.stringify({ status: "success" }))
                         .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: err.toString() }))
                         .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * Fungsi pembantu untuk memformat header baris pertama ala shadcn/ui
 */
function formatHeaderRow(sheet, numColumns) {
  var headerRange = sheet.getRange(1, 1, 1, numColumns);
  headerRange.setFontWeight("bold")
             .setBackground("#18181b")
             .setFontColor("#ffffff")
             .setFontFamily("Inter")
             .setHorizontalAlignment("center");
  sheet.setFrozenRows(1);
}
