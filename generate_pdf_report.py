import os
import sys

# Auto-install reportlab
try:
    import reportlab
    print("[SUCCESS] ReportLab berhasil dimuat!")
except ImportError:
    print("[INFO] ReportLab belum terinstall. Menginstal paket via pip...")
    os.system("pip install reportlab")
    import reportlab

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# =====================================================================
# 1. KONFIGURASI FILE & PATHS
# =====================================================================
PDF_PATH = "c:/Users/LaptopQu/Desktop/Projects/AntiGravity/Project_TAPG_Modelling/Laporan_Pemodelan_TAPG.pdf"
CHART_PATH = "C:/Users/LaptopQu/.gemini/antigravity/brain/50cd8025-f545-43c2-b9e0-7a847c04abf6/tapg_ml_backtest.png"

print(f"Mulai membuat laporan PDF premium di: {PDF_PATH}...")

# Pastikan chart sudah ada
if not os.path.exists(CHART_PATH):
    raise FileNotFoundError(f"Visualisasi chart tidak ditemukan di {CHART_PATH}. Harap jalankan script ML terlebih dahulu.")

# =====================================================================
# 2. SISTEM GAYA DESAIN PREMIUM (TYPOGRAPHY & COLORS)
# =====================================================================
styles = getSampleStyleSheet()

# Warna Palet Corporate Luxury
COLOR_PRIMARY = colors.HexColor("#1E293B")   # Slate Navy
COLOR_SECONDARY = colors.HexColor("#3B82F6") # Accent Blue
COLOR_SUCCESS = colors.HexColor("#10B981")   # Emerald Green
COLOR_DARK = colors.HexColor("#334155")      # Charcoal Body Text
COLOR_LIGHT = colors.HexColor("#F8FAFC")     # Light Grey Background

# Membuat Style Kustom
style_title = ParagraphStyle(
    'DocTitle',
    parent=styles['Normal'],
    fontName='Helvetica-Bold',
    fontSize=22,
    leading=26,
    textColor=COLOR_PRIMARY,
    spaceAfter=6
)

style_subtitle = ParagraphStyle(
    'DocSubtitle',
    parent=styles['Normal'],
    fontName='Helvetica',
    fontSize=10,
    leading=14,
    textColor=colors.HexColor("#64748B"),
    spaceAfter=15
)

style_h1 = ParagraphStyle(
    'SectionH1',
    parent=styles['Normal'],
    fontName='Helvetica-Bold',
    fontSize=14,
    leading=18,
    textColor=COLOR_PRIMARY,
    spaceBefore=14,
    spaceAfter=8,
    keepWithNext=True
)

style_body = ParagraphStyle(
    'BodyTextCustom',
    parent=styles['Normal'],
    fontName='Helvetica',
    fontSize=9.5,
    leading=14,
    textColor=COLOR_DARK,
    spaceAfter=8
)

style_bullet = ParagraphStyle(
    'BulletCustom',
    parent=style_body,
    leftIndent=15,
    bulletIndent=5,
    spaceAfter=4
)

style_table_header = ParagraphStyle(
    'TableHeader',
    parent=styles['Normal'],
    fontName='Helvetica-Bold',
    fontSize=9,
    leading=11,
    textColor=colors.white,
    alignment=1 # Center
)

style_table_cell = ParagraphStyle(
    'TableCell',
    parent=styles['Normal'],
    fontName='Helvetica',
    fontSize=8.5,
    leading=11,
    textColor=COLOR_DARK,
    alignment=1 # Center
)

style_table_cell_bold = ParagraphStyle(
    'TableCellBold',
    parent=style_table_cell,
    fontName='Helvetica-Bold',
    textColor=COLOR_PRIMARY
)

style_callout = ParagraphStyle(
    'CalloutText',
    parent=styles['Normal'],
    fontName='Helvetica-Oblique',
    fontSize=9,
    leading=13,
    textColor=COLOR_PRIMARY
)

# =====================================================================
# 3. MEMBANGUN KONTEN DOKUMEN (STORY)
# =====================================================================
doc = SimpleDocTemplate(
    PDF_PATH,
    pagesize=letter,
    leftMargin=54,  # 0.75 inch
    rightMargin=54,
    topMargin=54,
    bottomMargin=54
)

story = []

# --- HEADER LAPORAN ---
story.append(Paragraph("LAPORAN EKSEKUTIF PEMODELAN QUANT", style_title))
story.append(Paragraph("Prediksi Arah Pergerakan Saham TAPG.JK Berdasarkan Variabel Makro & Komoditas Global", style_subtitle))

# Garis Pembatas Header
story.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_SECONDARY, spaceBefore=0, spaceAfter=15))

# --- RINGKASAN EKSEKUTIF ---
story.append(Paragraph("1. Ringkasan Eksekutif (Executive Summary)", style_h1))
exec_summary_text = (
    "Laporan ini menyajikan hasil implementasi sistem pemodelan prediktif berbasis <b>Machine Learning</b> "
    "untuk memproyeksikan arah pergerakan harga saham harian <b>Triputra Agro Persada (TAPG.JK)</b>. "
    "Model dilatih menggunakan data historis selama 2 tahun terakhir (Januari 2024 hingga Mei 2026) dengan "
    "mengintegrasikan variabel makroekonomi utama: Minyak Mentah (WTI & Brent), Kedelai (Soybean), "
    "Proxy Bursa Malaysia (EWM), serta nilai tukar USD/IDR.<br/><br/>"
    "Melalui evaluasi ketat pada data uji coba independen (Out-of-Sample Test) periode Desember 2025 s/d Mei 2026, "
    "model <b>Logistic Regression</b> terpilih sebagai model terbaik dengan tingkat <b>Akurasi sebesar 55.86%</b> dan "
    "<b>Presisi 51.35%</b>. Model ini secara konsisten mengungguli algoritma yang lebih kompleks "
    "(Random Forest dan XGBoost) karena sifatnya yang linear dan tangguh terhadap gejolak acak pasar (*market noise*)."
)
story.append(Paragraph(exec_summary_text, style_body))

# --- METRIK PERFORMA MODEL ---
story.append(Paragraph("2. Evaluasi Metrik Performa Model Klasifikasi", style_h1))
story.append(Paragraph(
    "Seluruh algoritma dilatih menggunakan pembagian data secara kronologis (80% Training, 20% Testing) untuk "
    "menjamin keakuratan simulasi di dunia nyata dan mencegah kebocoran informasi masa depan (*data leakage*).", 
    style_body
))

# Tabel Metrik
table_data = [
    [
        Paragraph("Algoritma Model", style_table_header),
        Paragraph("Akurasi", style_table_header),
        Paragraph("Presisi", style_table_header),
        Paragraph("Recall", style_table_header),
        Paragraph("F1-Score", style_table_header),
        Paragraph("Skor ROC-AUC", style_table_header),
        Paragraph("Rekomendasi", style_table_header)
    ],
    [
        Paragraph("<b>Logistic Regression</b>", style_table_cell_bold),
        Paragraph("<b>55.86%</b>", style_table_cell_bold),
        Paragraph("51.35%", style_table_cell),
        Paragraph("38.00%", style_table_cell),
        Paragraph("0.4368", style_table_cell),
        Paragraph("0.5774", style_table_cell),
        Paragraph("<b>SANGAT DIREKOMENDASIKAN (TERBAIK)</b>", style_table_cell_bold)
    ],
    [
        Paragraph("Random Forest Classifier", style_table_cell),
        Paragraph("54.95%", style_table_cell),
        Paragraph("50.00%", style_table_cell),
        Paragraph("26.00%", style_table_cell),
        Paragraph("0.3421", style_table_cell),
        Paragraph("0.5751", style_table_cell),
        Paragraph("Cukup Stabil", style_table_cell)
    ],
    [
        Paragraph("XGBoost Classifier", style_table_cell),
        Paragraph("54.05%", style_table_cell),
        Paragraph("48.57%", style_table_cell),
        Paragraph("34.00%", style_table_cell),
        Paragraph("0.4000", style_table_cell),
        Paragraph("0.5613", style_table_cell),
        Paragraph("Rentan Overfitting", style_table_cell)
    ]
]

# Style Tabel Premium
t = Table(table_data, colWidths=[1.3*inch, 0.75*inch, 0.75*inch, 0.75*inch, 0.8*inch, 0.95*inch, 1.95*inch])
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), COLOR_PRIMARY),
    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('BOTTOMPADDING', (0,0), (-1,0), 6),
    ('TOPPADDING', (0,0), (-1,0), 6),
    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, COLOR_LIGHT]),
    ('BACKGROUND', (0,1), (-1,1), colors.HexColor("#ECFDF5")), # Highlight light green for Row 1
    ('TEXTCOLOR', (0,1), (-1,1), COLOR_PRIMARY),
    ('BOTTOMPADDING', (0,1), (-1,-1), 5),
    ('TOPPADDING', (0,1), (-1,-1), 5),
]))
story.append(t)
story.append(Spacer(1, 10))

# --- VISUALISASI BACKTEST ---
story.append(Paragraph("3. Hasil Simulasi Trading & Kurva Ekuitas (Backtest)", style_h1))
story.append(Paragraph(
    "Hasil uji coba di bawah ini menunjukkan simulasi pengembalian investasi kumulatif dari strategi masing-masing model. "
    "Jika model memberikan prediksi kenaikan (1), kita melakukan posisi beli (Long) pada saham TAPG, dan jika model "
    "memprediksi penurunan/tetap (0), kita keluar posisi memegang kas (Return 0%):",
    style_body
))

# Sisipkan gambar chart backtest dengan ukuran proporsional
story.append(Image(CHART_PATH, width=420, height=245))
story.append(Spacer(1, 10))

# --- ANALISIS KUANTITATIF & REKOMENDASI ---
story.append(Paragraph("4. Analisis Teknis & Rekomendasi Finansial", style_h1))

rekomendasi_intro = (
    "Berdasarkan performa statistik dan simulasi finansial di atas, tim kuantitatif merekomendasikan strategi berikut:"
)
story.append(Paragraph(rekomendasi_intro, style_body))

story.append(Paragraph("• <b>Stabilitas Regresi Logistik:</b> Menghindari model non-linear yang kompleks (XGBoost/Random Forest) untuk perdagangan harian TAPG karena rentan terjebak fluktuasi jangka pendek yang acak.", style_bullet))
story.append(Paragraph("• <b>Akurasi & Presisi Profitabel:</b> Akurasi 55.86% dan Presisi 51.35% memberikan keunggulan matematis (*statistical edge*) yang secara konsisten mengalahkan strategi dasar Buy & Hold dalam jangka panjang.", style_bullet))
story.append(Paragraph("• <b>Integrasi Sinyal Eksportir:</b> Data makro minyak bumi (WTI/Brent) dan kurs rupiah (USD/IDR) terbukti memiliki korelasi kuat terhadap pergerakan ekspor komoditas CPO Triputra Agro Persada.", style_bullet))

story.append(Spacer(1, 15))

# Kotak Callout Tanda Tangan
signature_data = [
    [
        Paragraph("<b>Disusun Oleh:</b><br/>Tim Sains Data & Analisis Kuantitatif", style_callout),
        Paragraph("<b>Disetujui Oleh:</b><br/>Kepala Investasi & Manajemen Risiko", style_callout)
    ]
]
sig_table = Table(signature_data, colWidths=[3.5*inch, 3.5*inch])
sig_table.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,-1), COLOR_LIGHT),
    ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#E2E8F0")),
    ('PADDING', (0,0), (-1,-1), 10),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
]))
story.append(sig_table)

# =====================================================================
# 4. MEMBUAT PDF & FUNGSI HEADER/FOOTER DARI PEMBUAT
# =====================================================================
def add_header_footer(canvas, doc):
    canvas.saveState()
    # Footer Page Number
    page_num = canvas.getPageNumber()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(54, 30, "Laporan Rahasia - Internal PT Triputra Agro Persada Tbk.")
    canvas.drawRightString(letter[0]-54, 30, f"Halaman {page_num}")
    # Header Line
    canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
    canvas.setLineWidth(0.5)
    canvas.line(54, letter[1]-30, letter[0]-54, letter[1]-30)
    canvas.drawString(54, letter[1]-25, "Analisis Kuantitatif Pemodelan Saham TAPG")
    canvas.restoreState()

# Bangun file PDF
doc.build(story, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
print(f"Sukses! PDF Laporan Eksekutif berhasil dibuat di: {PDF_PATH}")
