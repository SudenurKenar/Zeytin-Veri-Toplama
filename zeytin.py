# Gerekli kütüphanelerin import edilmesi
import sys
import os
import cv2
import time
import shutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QComboBox,
    QVBoxLayout, QHBoxLayout, QMessageBox, QGroupBox,
    QFormLayout, QPlainTextEdit, QInputDialog, QLineEdit
)
from PyQt5.QtCore import QTimer, Qt, QStandardPaths
from PyQt5.QtGui import QImage, QPixmap

# =============================================================================
# UYGULAMA SABİTLERİ VE AYARLARI
# =============================================================================
CAMERA_INDEXES = {"RGB": 0, "IP": 1}
IMAGE_QUALITY = 95
DEFAULT_CATEGORIES = ["Sağlıklı", "Böcekli"]
DEFAULT_OLIVE_TYPES = ["Edremit"]

# =============================================================================
# YARDIMCI FONKSİYONLAR VE YOL TANIMLAMALARI
# =============================================================================
# <<< DEĞİŞTİRİLDİ >>>
# Doğrudan hedef klasör yolu belirtiliyor.
# Baştaki 'r' harfi, Windows yollarındaki '\' karakterlerinin sorun çıkarmasını engeller.
APP_DATA_ROOT = r"D:\Zeytin_Kayıtları\Zeytin_Veri_Toplama"

# Dataset klasörü, belirttiğiniz bu ana klasörün içinde oluşturulacak.
DATASET_ROOT = os.path.join(APP_DATA_ROOT, "dataset")
# <<< DEĞİŞİKLİK SONU >>>

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def safe_foldername(s: str) -> str:
    return s.replace(" ", "_").replace("/", "-")

def next_image_index(folder_path: str) -> int:
    if not os.path.exists(folder_path): return 1
    existing_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".jpg")]
    return len(existing_files) + 1

def save_jpeg(path: str, img, quality: int) -> bool:
    try:
        ensure_dir(os.path.dirname(path))
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        result, buffer = cv2.imencode('.jpg', img, encode_param)
        if not result:
            raise IOError("cv2.imencode metodu başarısız oldu.")
        with open(path, 'wb') as f:
            f.write(buffer)
        return True
    except Exception as e:
        print(f"[HATA] save_jpeg içinde kritik hata: {e}")
        return False

def initial_setup():
    if not os.path.exists(DATASET_ROOT):
        print(f"[SETUP] Dataset temel klasörleri '{DATASET_ROOT}' konumunda oluşturuluyor...")
        for cam in CAMERA_INDEXES.keys():
            for cat in DEFAULT_CATEGORIES:
                ensure_dir(os.path.join(DATASET_ROOT, cam, safe_foldername(cat)))
        print("[SETUP] Dataset temel klasör yapısı başarıyla oluşturuldu.")
    else:
        print(f"[SETUP] Dataset klasörü zaten mevcut: '{DATASET_ROOT}'")

# =============================================================================
# ANA UYGULAMA SINIFI: ZeytinApp
# =============================================================================
class ZeytinApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zeytin Görüntü Toplama Aracı v2.4 (Gramaj Eklendi)")
        self.setMinimumSize(1000, 600)
        self.cap = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.grab_frame)
        self.current_frame = None
        self.categories = DEFAULT_CATEGORIES.copy()
        self.olive_types = DEFAULT_OLIVE_TYPES.copy()
        self.condition_codes = {"Sağlıklı": "S", "Böcekli": "B"}
        self.olive_type_codes = {"Edremit": "ED"}
        self.init_ui()
        initial_setup()
        self.cam_select.setCurrentIndex(0)
        self.on_camera_change()

    def init_ui(self):
        controls_group = QGroupBox("Kontroller")
        form_layout = QFormLayout()

        self.cam_select = QComboBox()
        self.cam_select.addItem("RGB Kamera (0)", "RGB")
        self.cam_select.addItem("IP Kamera (1)", "IP")
        self.cam_select.currentIndexChanged.connect(self.on_camera_change)
        form_layout.addRow("Kamera Türü:", self.cam_select)

        self.condition_select = QComboBox()
        self.condition_select.addItems(self.categories)
        form_layout.addRow("Zeytin Durumu:", self.condition_select)
        condition_btn_layout = self._create_add_del_buttons(self.add_condition, self.delete_condition)
        form_layout.addRow("Durum Yönetimi:", condition_btn_layout)

        self.olive_select = QComboBox()
        self.olive_select.addItems(self.olive_types)
        form_layout.addRow("Zeytin Türü/Yer:", self.olive_select)
        olive_btn_layout = self._create_add_del_buttons(self.add_olive_type, self.delete_olive_type)
        form_layout.addRow("Tür Yönetimi:", olive_btn_layout)
        
        ### YENİ EKLENDİ ###
        self.gram_input = QLineEdit()
        self.gram_input.setPlaceholderText("Örn: 125.5")
        form_layout.addRow("Gramaj (gr):", self.gram_input)
        ### YENİ EKLENDİ SONU ###

        snapshot_btn = QPushButton("📸 Fotoğraf Çek (Enter)")
        snapshot_btn.clicked.connect(self.on_snapshot)
        snapshot_btn.setStyleSheet("font-size: 16px; padding: 10px; background-color: #4CAF50; color: white;")
        form_layout.addRow(snapshot_btn)

        open_dataset_btn = QPushButton("📂 Dataset Klasörünü Aç")
        open_dataset_btn.clicked.connect(self.open_dataset_folder)
        form_layout.addRow(open_dataset_btn)

        controls_group.setLayout(form_layout)
        
        preview_group = QGroupBox("Canlı Önizleme")
        preview_layout = QVBoxLayout()
        self.preview_label = QLabel("Kamera bekleniyor...")
        self.preview_label.setFixedSize(640, 480)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #222; color: white; border: 1px solid #555;")
        preview_layout.addWidget(self.preview_label)
        self.info_label = QLabel("Kamera: - | Durum: - | Sıradaki No: -")
        preview_layout.addWidget(self.info_label)
        preview_group.setLayout(preview_layout)
        
        right_group = QGroupBox("Son Çekilen ve Sistem Logu")
        right_layout = QVBoxLayout()
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(240, 180)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet("background-color: #111; border: 1px solid #444;")
        right_layout.addWidget(self.thumb_label)
        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        right_layout.addWidget(self.log_widget)
        right_group.setLayout(right_layout)
        
        main_layout = QHBoxLayout()
        left_v_layout = QVBoxLayout()
        left_v_layout.addWidget(controls_group)
        left_v_layout.addStretch()
        main_layout.addLayout(left_v_layout, 1)
        main_layout.addWidget(preview_group, 2)
        main_layout.addWidget(right_group, 1)
        self.setLayout(main_layout)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self.log("Enter tuşuna basıldı, fotoğraf çekiliyor...", "info")
            self.on_snapshot()
        else:
            super().keyPressEvent(event)

    def _create_add_del_buttons(self, add_func, del_func):
        layout = QHBoxLayout()
        add_btn = QPushButton("+ Ekle")
        add_btn.clicked.connect(add_func)
        del_btn = QPushButton("- Sil")
        del_btn.clicked.connect(del_func)
        layout.addWidget(add_btn)
        layout.addWidget(del_btn)
        return layout

    def on_camera_change(self):
        cam_type = self.cam_select.currentData()
        if cam_type:
            self.start_camera(CAMERA_INDEXES[cam_type])

    def start_camera(self, index: int):
        if self.cap is not None and self.cap.isOpened():
            self.timer.stop()
            self.cap.release()
            time.sleep(0.1)
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW if sys.platform.startswith("win") else None)
        if not self.cap or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(index)
        if not self.cap or not self.cap.isOpened():
            QMessageBox.critical(self, "Kamera Hatası", f"Kamera (ID: {index}) açılamadı. Bağlantıyı kontrol edin.")
            self.preview_label.setText(f"Kamera {index} açılamadı")
            self.current_frame = None
            return
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.timer.start(33)
        self.log(f"Kamera {self.cam_select.currentData()} (ID: {index}) başarıyla bağlandı.")

    def grab_frame(self):
        if not self.cap or not self.cap.isOpened(): return
        ret, frame = self.cap.read()
        if ret:
            self.current_frame = frame.copy()
            self._show_frame_on_label(self.current_frame, self.preview_label)
            self._update_info_label()
        else:
            self.log("Kameradan görüntü alınamadı.", "warning")

    ### DEĞİŞTİRİLDİ ###
    def on_snapshot(self):
        if self.current_frame is None:
            self.log("Geçerli bir kare olmadığından fotoğraf çekilemedi.", "warning")
            return

        cond, olive, cam_type = self.condition_select.currentText(), self.olive_select.currentText(), self.cam_select.currentData()
        if not all([cond, olive, cam_type]):
            QMessageBox.warning(self, "Eksik Bilgi", "Devam etmek için lütfen tüm alanları seçin.")
            return
        
        # Gramaj bilgisini al ve doğrula
        gramaj_raw = self.gram_input.text().strip().replace(',', '.')
        gramaj_for_filename = "NA" # Varsayılan değer (Not Available)
        if gramaj_raw:
            try:
                # Sadece sayısal bir değer olup olmadığını kontrol et
                float(gramaj_raw)
                # Dosya adı için güvenli hale getir ve 'g' ekle
                safe_gramaj = gramaj_raw.replace('.', '-') 
                gramaj_for_filename = f"{safe_gramaj}g"
            except ValueError:
                QMessageBox.warning(self, "Geçersiz Giriş", "Gramaj alanına lütfen geçerli bir sayı girin (örn: 125.5).")
                self.log(f"Geçersiz gramaj girişi: '{gramaj_raw}'", "error")
                return

        folder_path = self._get_folder_path(cond, cam_type)
        idx = next_image_index(folder_path)
        filename = self._make_filename(cam_type, cond, olive, gramaj_for_filename, idx)
        filepath = os.path.join(folder_path, filename)
        
        if save_jpeg(filepath, self.current_frame, IMAGE_QUALITY):
            self.log(f"BAŞARILI: '{filename}' dosyası kaydedildi.", "success")
            self._show_frame_on_label(self.current_frame, self.thumb_label)
            self.gram_input.clear() # Başarılı çekimden sonra gramaj alanını temizle
            self.gram_input.setFocus() # Tekrar gramaj alanına odaklan
        else:
            error_msg = (f"HATA: Dosya diske yazılamadı!\n\nYol: {filepath}\n\n"
                         "Antivirüs veya Windows Güvenlik ayarlarınızı kontrol edin.")
            self.log(error_msg, "error")
            QMessageBox.critical(self, "Kayıt Hatası", error_msg)

    def _manage_category(self, name: str, action: str):
        safe_name = safe_foldername(name)
        for cam in CAMERA_INDEXES.keys():
            folder_path = os.path.join(DATASET_ROOT, cam, safe_name)
            if action == 'add': ensure_dir(folder_path)
            elif action == 'delete' and os.path.exists(folder_path):
                try: shutil.rmtree(folder_path)
                except OSError as e: self.log(f"'{folder_path}' silinemedi: {e}", "error")

    def add_condition(self):
        text, ok = QInputDialog.getText(self, "Yeni Durum Ekle", "Eklenecek durumun adı:")
        if ok and (name := text.strip()):
            if name in self.categories:
                QMessageBox.information(self, "Zaten Var", f"'{name}' durumu listede zaten mevcut.")
                return
            all_codes = list(self.condition_codes.values()) + list(self.olive_type_codes.values())
            new_code = self._generate_unique_code(name, all_codes)
            self.categories.append(name)
            self.condition_codes[name] = new_code
            self.condition_select.addItem(name)
            self._manage_category(name, 'add')
            self.log(f"Durum eklendi: '{name}' (Kod: {new_code})", "info")

    def delete_condition(self):
        current_cond = self.condition_select.currentText()
        if not current_cond: return
        if current_cond in DEFAULT_CATEGORIES:
            QMessageBox.warning(self, "Silinemez", f"'{current_cond}' varsayılan bir durumdur ve silinemez.")
            return
        reply = QMessageBox.question(self, "Onay", f"'{current_cond}' durumunu ve ilgili tüm resimleri kalıcı olarak silmek istediğinizden emin misiniz?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.categories.remove(current_cond)
            del self.condition_codes[current_cond]
            self.condition_select.removeItem(self.condition_select.findText(current_cond))
            self._manage_category(current_cond, 'delete')
            self.log(f"Durum silindi: '{current_cond}'", "info")

    def add_olive_type(self):
        text, ok = QInputDialog.getText(self, "Yeni Zeytin Türü Ekle", "Eklenecek türün adı:")
        if ok and (name := text.strip()):
            if name in self.olive_types:
                QMessageBox.information(self, "Zaten Var", f"'{name}' türü listede zaten mevcut.")
                return
            all_codes = list(self.condition_codes.values()) + list(self.olive_type_codes.values())
            new_code = self._generate_unique_code(name, all_codes)
            self.olive_types.append(name)
            self.olive_type_codes[name] = new_code
            self.olive_select.addItem(name)
            self.log(f"Zeytin türü eklendi: '{name}' (Kod: {new_code})", "info")

    def delete_olive_type(self):
        current_type = self.olive_select.currentText()
        if not current_type: return
        if current_type in DEFAULT_OLIVE_TYPES:
            QMessageBox.warning(self, "Silinemez", f"'{current_type}' varsayılan bir türdür ve silinemez.")
            return
        reply = QMessageBox.question(self, "Onay", f"'{current_type}' türünü silmek istediğinizden emin misiniz?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.olive_types.remove(current_type)
            del self.olive_type_codes[current_type]
            self.olive_select.removeItem(self.olive_select.findText(current_type))
            self.log(f"Zeytin türü silindi: '{current_type}'", "info")

    def _show_frame_on_label(self, frame, label: QLabel):
        try:
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
            label.setPixmap(QPixmap.fromImage(qt_image).scaled(label.width(), label.height(), Qt.KeepAspectRatio))
        except Exception: pass

    def _update_info_label(self):
        cam_type, cond = self.cam_select.currentData() or "-", self.condition_select.currentText() or "-"
        folder_path = self._get_folder_path(cond, cam_type)
        next_idx = next_image_index(folder_path)
        self.info_label.setText(f"Kamera: {cam_type} | Durum: {cond} | Sıradaki No: {next_idx}")

    def _get_folder_path(self, condition: str, cam_type: str) -> str:
        return os.path.join(DATASET_ROOT, cam_type, safe_foldername(condition))

    ### DEĞİŞTİRİLDİ ###
    def _make_filename(self, cam_type: str, condition: str, olive_type: str, gramaj: str, index: int) -> str:
        cam_code = cam_type
        olive_code = self.olive_type_codes.get(olive_type, "XX")
        cond_code = self.condition_codes.get(condition, "YY")
        return f"{cam_code}_{olive_code}_{cond_code}_{gramaj}_{index}.jpg"

    def _generate_unique_code(self, text: str, existing_codes: list) -> str:
        words = text.split()
        code = "".join([word[0].upper() for word in words])[:2]
        if code and code not in existing_codes: return code
        if words:
            code = words[0][:2].upper()
            if len(code) == 2 and code not in existing_codes: return code
        if text:
            first_char = text[0].upper()
            for i in range(1, 100):
                code = f"{first_char}{i}"
                if code not in existing_codes: return code
        return "XX"

    def open_dataset_folder(self):
        folder = os.path.abspath(DATASET_ROOT)
        ensure_dir(folder)
        try:
            if sys.platform.startswith("win"): os.startfile(folder)
            elif sys.platform.startswith("darwin"): os.system(f'open "{folder}"')
            else: os.system(f'xdg-open "{folder}"')
            self.log("Dataset klasörü dosya gezgininde açıldı.", "info")
        except Exception:
            self.log("Dosya gezgini otomatik olarak açılamadı.", "warning")

    def log(self, text: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        prefix_map = {"info": "[BİLGİ]", "success": "[BAŞARI]", "warning": "[UYARI]", "error": "[HATA]"}
        prefix = prefix_map.get(level, "[MESAJ]")
        full_message = f"{prefix} [{ts}] {text}"
        self.log_widget.appendPlainText(full_message)
        print(full_message)

    def closeEvent(self, event):
        self.log("Uygulama kapatılıyor...", "info")
        if self.cap is not None and self.cap.isOpened():
            self.timer.stop()
            self.cap.release()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ZeytinApp()
    window.show()
    sys.exit(app.exec_())