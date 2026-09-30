from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle
from kivy.properties import StringProperty, NumericProperty
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import Metrics
from datetime import datetime, timedelta
import mimetypes
import shutil
import tempfile
from urllib.parse import unquote, urlparse

from cashflow_db import CashflowDB

import os


# --------------------------------------------------------------------------- #
# Android media bridge
# --------------------------------------------------------------------------- #
# Plyer memakai dialog native Android, jadi pengguna dapat memilih file dari
# aplikasi Files/Galeri dan kamera sistem. Import dibuat lokal agar aplikasi
# tetap bisa diuji di Linux tanpa Android atau paket plyer terpasang.
def _is_android():
    return "ANDROID_ARGUMENT" in os.environ or "ANDROID_STORAGE" in os.environ


def _android_sdk_int():
    """Tingkat API Android, atau 0 bila aplikasi berjalan di luar Android."""
    if not _is_android():
        return 0
    try:
        from jnius import autoclass
        return int(autoclass("android.os.Build$VERSION").SDK_INT)
    except Exception:
        return 0


def _android_missing_permissions(names):
    """Izin dari daftar nama (``Permission.CAMERA`` dan sejenisnya) yang belum diberikan.

    Pemilih Files/Galeri memakai Storage Access Framework yang memberi akses
    per-file tanpa izin penyimpanan, jadi biasanya daftar ini kosong.
    """
    if not _is_android() or not names:
        return []
    try:
        from android.permissions import Permission, check_permission
    except Exception:
        return []
    missing = []
    for name in names:
        permission = getattr(Permission, name, None)
        if permission is None:
            continue
        try:
            if not check_permission(permission):
                missing.append(permission)
        except Exception:
            continue
    return missing


def _app_data_dir():
    """Folder data aplikasi yang writable di Android maupun desktop."""
    try:
        path = App.get_running_app().user_data_dir
    except Exception:
        path = tempfile.gettempdir()
    os.makedirs(path, exist_ok=True)
    return path


def _downloads_buku_kas_dir():
    """Buat folder publik Downloads/Buku Kas di Android atau ~/Downloads di Linux."""
    base = os.path.join(os.path.expanduser("~"), "Downloads")
    if _is_android():
        try:
            from jnius import autoclass
            Environment = autoclass("android.os.Environment")
            base = Environment.getExternalStoragePublicDirectory(
                Environment.DIRECTORY_DOWNLOADS
            ).getAbsolutePath()
        except Exception:
            # Path app-private tetap dapat digunakan sebagai fallback ketika
            # OEM membatasi folder publik atau izin penyimpanan tidak diberikan.
            base = os.path.join(_app_data_dir(), "Downloads")
    folder = os.path.join(base, "Buku Kas")
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        # Folder publik tidak bisa dibuat (scoped storage / OEM membatasi).
        # Fallback ke folder data aplikasi supaya unduhan tetap berhasil.
        folder = os.path.join(_app_data_dir(), "Downloads", "Buku Kas")
        os.makedirs(folder, exist_ok=True)
    return folder


def _android_save_download(source, name, mime_type):
    """Simpan file ke Downloads/Buku Kas lewat MediaStore untuk Android 10+."""
    if not _is_android():
        return None
    try:
        from jnius import autoclass
        Activity = autoclass("org.kivy.android.PythonActivity")
        ContentValues = autoclass("android.content.ContentValues")
        MediaStore = autoclass("android.provider.MediaStore")
        Environment = autoclass("android.os.Environment")
        context = Activity.mActivity
        values = ContentValues()
        values.put(MediaStore.MediaColumns.DISPLAY_NAME, name)
        values.put(MediaStore.MediaColumns.MIME_TYPE, mime_type or "application/octet-stream")
        values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Buku Kas")
        collection = MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        uri = context.getContentResolver().insert(collection, values)
        if not uri:
            return None
        output = context.getContentResolver().openOutputStream(uri)
        with open(source, "rb") as src, output:
            shutil.copyfileobj(src, output)
        return f"Downloads/Buku Kas/{name}"
    except Exception:
        return None


def _safe_filename(name, fallback="lampiran"):
    name = os.path.basename(str(name or fallback)).strip() or fallback
    return "".join(c for c in name if c.isalnum() or c in " ._-()")


def _android_uri_metadata(source):
    """Ambil nama dan MIME asli dari content URI Android."""
    source_text = str(source)
    if source_text.startswith("file://"):
        parsed = urlparse(source_text)
        return os.path.basename(unquote(parsed.path)), None
    if not _is_android():
        return os.path.basename(source_text), None
    try:
        from jnius import autoclass
        Activity = autoclass("org.kivy.android.PythonActivity")
        Uri = autoclass("android.net.Uri")
        OpenableColumns = autoclass("android.provider.OpenableColumns")
        cursor = Activity.mActivity.getContentResolver().query(
            Uri.parse(str(source)), None, None, None, None
        )
        if cursor is None:
            return os.path.basename(str(source)), None
        name, mime = os.path.basename(str(source)), None
        if cursor.moveToFirst():
            name_index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            mime_index = cursor.getColumnIndex(OpenableColumns.MIME_TYPE)
            if name_index >= 0:
                name = cursor.getString(name_index) or name
            if mime_index >= 0:
                mime = cursor.getString(mime_index)
        cursor.close()
        return name, mime
    except Exception:
        return os.path.basename(str(source)), None


def _copy_android_uri(source, target):
    """Salin content:// dari Android Storage Access Framework ke file lokal."""
    if not _is_android() or not str(source).startswith("content://"):
        return False
    try:
        from jnius import autoclass
        Activity = autoclass("org.kivy.android.PythonActivity")
        Uri = autoclass("android.net.Uri")
        resolver = Activity.mActivity.getContentResolver()
        stream = resolver.openInputStream(Uri.parse(str(source)))
        if stream is None:
            return False
        with open(target, "wb") as output:
            buffer = bytearray(64 * 1024)
            while True:
                try:
                    count = stream.read(buffer)
                except Exception:
                    count = stream.readBytes(buffer, 0, len(buffer))
                if not count or (isinstance(count, int) and count <= 0):
                    break
                output.write(buffer[:count] if isinstance(count, int) else count)
        stream.close()
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Intent Android: Files/Galeri (Storage Access Framework) dan kamera
# --------------------------------------------------------------------------- #
# Hasil activity Android masuk ke Python dari thread Java, sedangkan widget Kivy
# hanya aman disentuh di thread utama Kivy. Karena itu semua hasil intent
# diteruskan lewat Clock.schedule_once sebelum menyentuh UI.
def _android_request_code():
    from random import randint
    return randint(1000, 60000)


def _android_start_activity(intent, request_code, handler):
    """Jalankan intent, lalu panggil handler(berhasil, data) di thread utama Kivy."""
    from android import activity
    from jnius import autoclass
    Activity = autoclass("android.app.Activity")

    def on_activity_result(code, result_code, data):
        if code != request_code:
            return
        try:
            activity.unbind(on_activity_result=on_activity_result)
        except Exception:
            pass
        granted = result_code == Activity.RESULT_OK
        Clock.schedule_once(lambda _dt: handler(granted, data), 0.05)

    activity.bind(on_activity_result=on_activity_result)
    autoclass("org.kivy.android.PythonActivity").mActivity.startActivityForResult(
        intent, request_code
    )


def _android_open_documents(mime_type, multiple, on_selection, on_cancel):
    """Buka Files/Galeri Android lalu kirim daftar ``content://`` ke on_selection.

    Dipakai langsung, bukan lewat plyer, karena plyer menerjemahkan content://
    jadi path filesystem yang tidak selalu ada (misalnya foto dari Google Photos),
    sehingga file terpilih hilang begitu saja.
    """
    try:
        from jnius import autoclass, cast
        Intent = autoclass("android.content.Intent")
        String = autoclass("java.lang.String")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
    except Exception as exc:
        Clock.schedule_once(lambda _dt: on_cancel(f"Files Android tidak tersedia: {exc}"), 0.05)
        return

    intent = Intent(Intent.ACTION_GET_CONTENT)
    intent.addCategory(Intent.CATEGORY_OPENABLE)
    intent.setType(mime_type or "*/*")
    if multiple:
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, True)
    chooser = Intent.createChooser(
        intent, cast("java.lang.CharSequence", String("Pilih foto atau PDF"))
    )
    request_code = _android_request_code()

    def handle(granted, data):
        if not granted or data is None:
            on_cancel()
            return
        uris = []
        try:
            clip = data.getClipData()
            if clip is not None:
                for index in range(clip.getItemCount()):
                    uris.append(str(clip.getItemAt(index).getUri()))
        except Exception:
            uris = []
        if not uris:
            try:
                uri = data.getData()
                if uri is not None:
                    uris.append(str(uri))
            except Exception:
                pass
        if not uris:
            on_cancel()
            return
        on_selection(uris)

    try:
        _android_start_activity(chooser, request_code, handle)
    except Exception as exc:
        Clock.schedule_once(
            lambda _dt: on_cancel(f"Gagal membuka Files Android: {exc}"), 0.05
        )


def _android_delete_media(uri):
    try:
        from jnius import autoclass
        autoclass("org.kivy.android.PythonActivity").mActivity \
            .getContentResolver().delete(uri, None, None)
    except Exception:
        pass


def _android_camera_output_uri(name):
    """Buat uri MediaStore sementara untuk menampung hasil foto kamera."""
    from jnius import autoclass
    context = autoclass("org.kivy.android.PythonActivity").mActivity
    ContentValues = autoclass("android.content.ContentValues")
    MediaStore = autoclass("android.provider.MediaStore")
    Environment = autoclass("android.os.Environment")

    values = ContentValues()
    values.put(MediaStore.MediaColumns.DISPLAY_NAME, name)
    values.put(MediaStore.MediaColumns.MIME_TYPE, "image/jpeg")
    collection = MediaStore.Images.Media.EXTERNAL_CONTENT_URI
    if _android_sdk_int() >= 29:
        values.put(MediaStore.MediaColumns.RELATIVE_PATH,
                   Environment.DIRECTORY_PICTURES + "/Buku Kas")
        try:
            values.put(MediaStore.MediaColumns.IS_PENDING, 1)
        except Exception:
            # Placeholder IS_PENDING opsional: barisnya tetap dihapus setelah
            # foto disalin ke folder aplikasi.
            pass
        collection = MediaStore.Images.Media.getContentUri(
            MediaStore.VOLUME_EXTERNAL_PRIMARY)
    else:
        folder = os.path.join(
            Environment.getExternalStoragePublicDirectory(
                Environment.DIRECTORY_PICTURES).getAbsolutePath(),
            "Buku Kas",
        )
        os.makedirs(folder, exist_ok=True)
        values.put(MediaStore.MediaColumns.DATA, os.path.join(folder, name))
    return context.getContentResolver().insert(collection, values)


def _android_take_photo(on_complete, on_error):
    """Ambil foto dengan kamera sistem lalu kirim path lokal ke on_complete.

    Hasil kamera ditulis ke MediaStore, bukan ``file://`` di folder aplikasi,
    karena Android 7.0+ menutup aplikasi yang meneruskan ``file://`` ke aplikasi
    lain (FileUriExposedException).
    """
    name = f"kas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    try:
        output_uri = _android_camera_output_uri(name)
    except Exception as exc:
        on_error(f"Tidak bisa menyiapkan file foto: {exc}")
        return
    if not output_uri:
        on_error("Kamera gagal menyiapkan file tujuan.")
        return

    from jnius import autoclass, cast
    MediaStore = autoclass("android.provider.MediaStore")
    Intent = autoclass("android.content.Intent")
    intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
    intent.putExtra(MediaStore.EXTRA_OUTPUT, cast("android.os.Parcelable", output_uri))
    request_code = _android_request_code()

    def handle(granted, _data):
        if not granted:
            _android_delete_media(output_uri)
            on_error("Kamera dibatalkan atau tidak menghasilkan foto.")
            return
        target = os.path.join(_app_data_dir(), "camera", name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        stored = _copy_android_uri(str(output_uri), target)
        _android_delete_media(output_uri)
        if not stored or not os.path.isfile(target):
            on_error("Foto dari kamera gagal dibaca.")
            return
        on_complete(target)

    try:
        _android_start_activity(intent, request_code, handle)
    except Exception as exc:
        _android_delete_media(output_uri)
        on_error(f"Kamera gagal dibuka: {exc}")


def _copy_to_app_storage(source, display_name=None):
    """Salin file pilihan pengguna ke folder data aplikasi supaya persisten."""
    if not source:
        return None
    folder = os.path.join(_app_data_dir(), "attachments")
    os.makedirs(folder, exist_ok=True)
    source_text = str(source)
    if source_text.startswith("file://"):
        source_text = unquote(urlparse(source_text).path)
    display_name = _safe_filename(display_name or os.path.basename(source_text))
    stem, ext = os.path.splitext(display_name)
    target = os.path.join(folder, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{stem}{ext}")
    try:
        if _copy_android_uri(source, target):
            return target
        shutil.copyfile(source_text, target)
        return target
    except (OSError, TypeError):
        return None


def _guess_mime(path):
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"

# --------------------------------------------------------------------------- #
# Ikon & Font
# --------------------------------------------------------------------------- #
# Ikon di header memakai file PNG (assets/icons), karena ikon emoji (ðŸ“„, ðŸ”,
# ðŸŒ™, â˜€ ...) tidak ada di font default Kivy (Roboto). Kalau dipakai sebagai
# teks tombol, emoji tampil sebagai kotak kosong / tidak terlihat sama sekali.
ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icons")


def dejavu_font():
    """Font yang punya karakter âœ“ âœ â† â‹® â–¾ â˜€ (tidak ada di font Roboto bawaan)."""
    # 1) Font DejaVu yang disalin ke dalam folder proyek (agar self-contained)
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "DejaVuSans.ttf")
    if os.path.exists(local):
        return local
    # 2) Font DejaVu yang ikut dibundel oleh Kivy (jika ada)
    try:
        import kivy
        bundled = os.path.join(kivy.__path__[0], "data", "fonts", "DejaVuSans.ttf")
        if os.path.exists(bundled):
            return bundled
    except Exception:
        pass
    return "Roboto"


def _layout_icon_in_button(btn, icon, icon_ratio, right_anchor=False):
    """Tata ukuran & posisi ikon di dalam tombol.

    Button bukan Layout, jadi posisi anaknya ditulis dalam koordinat absolut
    jendela (bukan relatif ke tombol). Fungsi ini memusatkan ikon persegi di
    tengah tombol (atau di sisi kanan untuk panah pemilih buku kas).
    """
    icon.size_hint = (None, None)

    def relayout(*_):
        side = max(1.0, min(btn.width, btn.height) * icon_ratio)
        icon.size = (side, side)
        if right_anchor:
            right_pad = btn.height * 0.12
            offset_x = btn.width - side - right_pad
        else:
            offset_x = (btn.width - side) / 2.0
        offset_y = (btn.height - side) / 2.0
        icon.pos = (btn.x + offset_x, btn.y + offset_y)

    btn.bind(size=relayout, pos=relayout)
    relayout()


def icon_button(icon_file, on_release=None, size_hint_x=None, size_hint_y=1.0,
                width_dp=None, icon_ratio=0.72):
    """Buat tombol berisi ikon PNG di tengah (terlihat di semua sistem)."""
    kwargs = {
        "background_normal": '',
        "background_color": (0, 0, 0, 0),
        "size_hint_x": size_hint_x,
        "size_hint_y": size_hint_y,
    }
    if width_dp:
        kwargs["width"] = dpw(width_dp)
    btn = Button(**kwargs)
    btn.icon_widget = Image(
        source=os.path.join(ICON_DIR, icon_file),
        allow_stretch=True,
        keep_ratio=True,
    )
    _layout_icon_in_button(btn, btn.icon_widget, icon_ratio)
    btn.add_widget(btn.icon_widget)
    if on_release is not None:
        btn.bind(on_release=on_release)
    return btn

# --------------------------------------------------------------------------- #
# Sistem Skala Responsif
# --------------------------------------------------------------------------- #
# Aplikasi ini dulu terkunci di bingkai ponsel (360dp x 720dp). Sekarang seluruh
# layout mengisi jendela/layar dan semua ukuran (font, tinggi, padding, popup)
# ikut diskalakan terhadap lebar & tinggi jendela. Di layar lebar konten dibatasi
# lebarnya supaya tetap nyaman dibaca dan dirapikan di tengah.
DESIGN_WIDTH = 360.0       # lebar acuan desain (dp) -> skala 1.0
DESIGN_HEIGHT = 720.0      # tinggi acuan desain (dp) -> skala 1.0
MAX_CONTENT_WIDTH = 620.0  # lebar maksimum konten di layar lebar (dp)
MIN_SCALE = 0.7
MAX_SCALE = 1.5

_ui_scale = 1.0


def get_ui_scale():
    return _ui_scale


def set_ui_scale(value):
    global _ui_scale
    _ui_scale = float(value)


def dpv(value):
    """Nilai dp yang sudah diskalakan (angka, bukan teks)."""
    return value * get_ui_scale()


def dpw(value):
    """Ubah nilai dp menjadi teks 'dp' yang ikut skala jendela."""
    return f"{dpv(value):g}dp"


def spw(value):
    """Ubah nilai sp menjadi teks 'sp' yang ikut skala jendela."""
    return f"{dpv(value):g}sp"


def window_dp_size():
    """Ukuran jendela dalam satuan dp: (lebar, tinggi)."""
    try:
        density = max(float(Metrics.density), 0.25)
        return float(Window.width) / density, float(Window.height) / density
    except Exception:
        return DESIGN_WIDTH, DESIGN_WIDTH * 2.0


def update_ui_scale():
    """Hitung skala UI dari lebar DAN tinggi jendela saat ini.

    Memakai nilai terkecil dari keduanya supaya pada jendela pendek/landscape
    batang-batang tetap (header, form, tombol) tidak pernah lebih tinggi dari
    layar dan terpotong di bagian atas.
    """
    w_dp, h_dp = window_dp_size()
    if w_dp <= 0 or h_dp <= 0:
        w_dp, h_dp = DESIGN_WIDTH, DESIGN_HEIGHT
    scale_w = w_dp / DESIGN_WIDTH
    scale_h = h_dp / DESIGN_HEIGHT
    set_ui_scale(max(MIN_SCALE, min(MAX_SCALE, min(scale_w, scale_h))))


def popup_size(width_dp, height_dp):
    """Ukuran popup (dalam satuan dp) yang tidak pernah lebih besar dari layar."""
    w_dp, h_dp = window_dp_size()
    return (
        f"{min(dpv(width_dp), max(200.0, w_dp * 0.94)):g}dp",
        f"{min(dpv(height_dp), max(200.0, h_dp * 0.9)):g}dp",
    )


# --- Palet Warna Tema (Terang & Gelap) ---
THEMES = {
    "light": {
        "app_bg": (0.12, 0.12, 0.12, 1),
        "phone_bg": (0.95, 0.96, 0.97, 1),
        "header_bg": (0.1, 0.5, 0.88, 1),
        "tab_bg": (0.1, 0.5, 0.88, 1),
        "tab_active": (1, 1, 1, 0.4),
        "tab_inactive": (1, 1, 1, 0.2),
        "subheader_bg": (0.15, 0.45, 0.75, 1),
        "table_header_bg": (0.9, 0.91, 0.93, 1),
        "row_bg": (1, 1, 1, 1),
        "footer_bg": (1, 1, 1, 1),
        "card_bg": (1, 1, 1, 1),
        "input_bg": (1, 1, 1, 1),
        "input_text": (0.1, 0.1, 0.1, 1),
        "text_primary": (0.1, 0.1, 0.1, 1),
        "text_secondary": (0.5, 0.5, 0.5, 1),
        "text_muted": (0.4, 0.4, 0.4, 1),
    },
    "dark": {
        "app_bg": (0.05, 0.05, 0.06, 1),
        "phone_bg": (0.13, 0.13, 0.15, 1),
        "header_bg": (0.08, 0.32, 0.58, 1),
        "tab_bg": (0.08, 0.32, 0.58, 1),
        "tab_active": (1, 1, 1, 0.35),
        "tab_inactive": (1, 1, 1, 0.12),
        "subheader_bg": (0.1, 0.28, 0.45, 1),
        "table_header_bg": (0.2, 0.2, 0.23, 1),
        "row_bg": (0.19, 0.19, 0.22, 1),
        "footer_bg": (0.19, 0.19, 0.22, 1),
        "card_bg": (0.17, 0.17, 0.2, 1),
        "input_bg": (0.24, 0.24, 0.28, 1),
        "input_text": (0.92, 0.92, 0.94, 1),
        "text_primary": (0.92, 0.92, 0.94, 1),
        "text_secondary": (0.65, 0.65, 0.68, 1),
        "text_muted": (0.6, 0.6, 0.63, 1),
    },
}


# Helper Canvas Background (sekarang bisa ganti warna secara dinamis lewat set_bg_color)
class ColorBoxLayout(BoxLayout):
    def __init__(self, bg_color=(1, 1, 1, 1), **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            self._color_instr = Color(*bg_color)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)

    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

    def set_bg_color(self, color):
        self._color_instr.rgba = color


class ColorFloatLayout(FloatLayout):
    def __init__(self, bg_color=(0.12, 0.12, 0.12, 1), **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            self._color_instr = Color(*bg_color)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)

    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

    def set_bg_color(self, color):
        self._color_instr.rgba = color


class ResponsiveLayout(ColorFloatLayout):
    """Latar aplikasi yang mengisi seluruh jendela.

    Konten di dalamnya ikut lebar layar (mengisi penuh di layar kecil/ponsel)
    tapi dibatasi MAX_CONTENT_WIDTH dan di tengah saat layarnya lebar.
    Posisi dan ukuran konten otomatis menyesuaikan saat jendela diubah ukurannya.
    """

    def __init__(self, bg_color=(0.12, 0.12, 0.12, 1), **kwargs):
        super().__init__(bg_color=bg_color, **kwargs)
        self._content = None
        self._max_width = MAX_CONTENT_WIDTH
        self.bind(size=self._refit, pos=self._refit)

    def set_content(self, content, max_width=MAX_CONTENT_WIDTH):
        self._content = content
        self._max_width = max_width
        content.size_hint = (None, None)
        self.add_widget(content)
        self._refit()

    def _refit(self, *args):
        if self._content is None:
            return
        try:
            density = max(float(Metrics.density), 0.25)
        except Exception:
            density = 1.0
        dp_w = float(self.width) / density
        target_w = max(1.0, min(self._max_width, dp_w))
        px_w = target_w * density
        self._content.width = px_w
        self._content.height = self.height
        self._content.x = self.x + (self.width - px_w) / 2.0
        self._content.y = self.y


# --- Widget Custom Baris Transaksi ---
class TransactionRow(ColorBoxLayout):
    def __init__(self, tx_data, palette=None, **kwargs):
        palette = palette or THEMES["light"]
        has_edit_note = bool(tx_data.get('edited_at'))
        row_height = dpw(66) if has_edit_note else dpw(52)

        super().__init__(bg_color=palette["row_bg"], size_hint_y=None, height=row_height, padding=[dpw(8), dpw(4)], **kwargs)
        self.tx_data = tx_data

        # Tanggal & Jam + Catatan (+ info edit kalau pernah diedit)
        col_date = BoxLayout(orientation='vertical', size_hint_x=0.36)

        date_time_text = tx_data['date_str']
        if tx_data.get('time_str'):
            date_time_text += f"  {tx_data['time_str']}"
        lbl_date = Label(text=date_time_text, color=palette["text_primary"], font_size=spw(13), halign="left", valign="middle")
        lbl_note = Label(text=tx_data['note'] if tx_data['note'] else "-", color=palette["text_secondary"], font_size=spw(12), halign="left", valign="middle")
        lbl_date.bind(size=lbl_date.setter('text_size'))
        lbl_note.bind(size=lbl_note.setter('text_size'))
        col_date.add_widget(lbl_date)
        col_date.add_widget(lbl_note)

        if has_edit_note:
            lbl_edited = Label(
                text=f"Diedit pada {tx_data['edited_at']}",
                color=(0.85, 0.55, 0.1, 1), font_size=spw(11), italic=True,
                halign="left", valign="middle"
            )
            lbl_edited.bind(size=lbl_edited.setter('text_size'))
            col_date.add_widget(lbl_edited)

        formatted_amount = f"{int(tx_data['amount']):,}"

        # Kolom Menerima (Center)
        lbl_in = Label(
            text=formatted_amount if tx_data['tx_type'] == "Menerima" else "-",
            color=(0.1, 0.6, 0.2, 1), bold=True, size_hint_x=0.32,
            halign="center", valign="middle", font_size=spw(13)
        )
        lbl_in.bind(size=lbl_in.setter('text_size'))

        # Kolom Membayar (Center)
        lbl_out = Label(
            text=formatted_amount if tx_data['tx_type'] == "Membayar" else "-",
            color=(0.85, 0.25, 0.2, 1), bold=True, size_hint_x=0.32,
            halign="center", valign="middle", font_size=spw(13)
        )
        lbl_out.bind(size=lbl_out.setter('text_size'))

        self.add_widget(col_date)
        self.add_widget(lbl_in)
        self.add_widget(lbl_out)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            app = App.get_running_app()
            app.tx_screen.set_theme(app.home_screen.theme)
            app.tx_screen.set_mode_edit(self.tx_data)
            app.sm.current = "transaction"
            return True
        return super().on_touch_down(touch)


# --- 1. HALAMAN UTAMA (BUKU KAS) ---
class HomeScreen(Screen):
    total_in = NumericProperty(0)
    total_out = NumericProperty(0)

    FILTER_LABELS = ["Semua", "Harian", "Mingguan", "Bulanan", "Tahunan"]
    BULAN_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
                "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Koneksi ke database SQLite (file terpisah: cashflow.db)
        self.db = CashflowDB()

        # Struktur Data Multi Buku Kas dimuat dari database:
        # {'nama_kas': [list_transaksi]}
        book_names = self.db.get_books() or ["Buku Kas Utama"]
        self.books = {name: self._load_transactions(name) for name in book_names}
        self.current_book_name = book_names[0]

        # State tema & filter
        self.theme = "light"
        self.current_filter = "Semua"
        self.sort_order = "desc"   # urutan tanggal: desc = terbaru dulu, asc = terlama dulu
        self.search_query = ""     # teks pencarian berdasarkan catatan
        self.themed_bg = {}    # widget -> nama key warna di THEMES
        self.themed_text = {}  # label -> nama key warna di THEMES
        self.tab_buttons = {}  # nama_tab -> tombol

        self.rebuild()

    def rebuild(self):
        """Bangun ulang seluruh tampilan (dipakai saat skala/ukuran jendela berubah)."""
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        palette = THEMES[self.theme]
        self.themed_bg = {}
        self.themed_text = {}
        self.tab_buttons = {}

        # Base Container Gelap yang mengisi seluruh jendela (responsive)
        outer_layout = ResponsiveLayout(bg_color=palette["app_bg"])
        self.themed_bg[outer_layout] = "app_bg"

        # Konten utama: mengisi layar, dibatasi & di tengah di layar lebar
        phone_frame = ColorBoxLayout(
            bg_color=palette["phone_bg"],
            orientation='vertical',
            size_hint=(None, None)
        )
        self.themed_bg[phone_frame] = "phone_bg"
        outer_layout.set_content(phone_frame)

        # Header Top Bar dengan Tombol Pemilih Buku Kas
        header = ColorBoxLayout(bg_color=palette["header_bg"], size_hint_y=None, height=dpw(50), padding=[dpw(8), "0dp"])
        self.themed_bg[header] = "header_bg"

        # Tombol ganti tema: matahari saat tema terang, bulan sabit saat tema gelap
        self.btn_theme = icon_button(
            "icon_sun.png" if self.theme == "light" else "icon_moon.png",
            on_release=self.toggle_theme, size_hint_x=0.12,
        )
        header.add_widget(self.btn_theme)

        # Tombol Judul Kas (bisa diklik untuk ganti / buat / edit nama kas)
        self.btn_book_selector = Button(
            text=self.current_book_name, font_size=spw(16), bold=True,
            size_hint_x=0.6, background_color=(0, 0, 0, 0), halign="left", valign="middle",
            padding=[dpw(8), 0, dpw(24), 0],
        )
        self.btn_book_selector.bind(size=self.btn_book_selector.setter('text_size'))
        self.btn_book_selector.bind(on_release=self.open_book_manager_popup)
        self.book_arrow = Image(
            source=os.path.join(ICON_DIR, "icon_down.png"),
            allow_stretch=True, keep_ratio=True,
        )
        _layout_icon_in_button(self.btn_book_selector, self.book_arrow, 0.36, right_anchor=True)
        self.btn_book_selector.add_widget(self.book_arrow)
        header.add_widget(self.btn_book_selector)

        # Tiga ikon interaktif di kanan atas: ekspor Excel, cari catatan, urutkan tanggal
        right_icons = BoxLayout(size_hint_x=0.28, spacing=dpw(2))

        self.btn_export = icon_button(
            "icon_export.png", on_release=self.export_to_excel,
            size_hint_x=None, width_dp=30,
        )
        right_icons.add_widget(self.btn_export)

        self.btn_search = icon_button(
            "icon_search.png", on_release=self.open_search_popup,
            size_hint_x=None, width_dp=30,
        )
        right_icons.add_widget(self.btn_search)

        self.btn_sort = icon_button(
            "icon_sort.png", on_release=self.open_sort_menu,
            size_hint_x=None, width_dp=30,
        )
        right_icons.add_widget(self.btn_sort)

        header.add_widget(right_icons)
        phone_frame.add_widget(header)

        # Tab Filter (kini benar-benar berfungsi)
        tab_layout = ColorBoxLayout(bg_color=palette["tab_bg"], size_hint_y=None, height=dpw(40), padding=[dpw(4), dpw(4)], spacing=dpw(4))
        self.themed_bg[tab_layout] = "tab_bg"
        for tab in self.FILTER_LABELS:
            is_active = (tab == self.current_filter)
            btn = Button(
                text=tab,
                background_color=palette["tab_active"] if is_active else palette["tab_inactive"],
                bold=is_active, font_size=spw(12)
            )
            btn.bind(on_release=lambda x, t=tab: self.set_filter(t))
            tab_layout.add_widget(btn)
            self.tab_buttons[tab] = btn
        phone_frame.add_widget(tab_layout)

        # Sub Header -> jadi indikator filter yang sedang aktif
        sub_header = ColorBoxLayout(bg_color=palette["subheader_bg"], size_hint_y=None, height=dpw(24))
        self.themed_bg[sub_header] = "subheader_bg"
        self.lbl_subheader = Label(text="Semua Transaksi", font_size=spw(13), halign="center", valign="middle")
        sub_header.add_widget(self.lbl_subheader)
        phone_frame.add_widget(sub_header)

        # Table Header
        table_header = ColorBoxLayout(bg_color=palette["table_header_bg"], size_hint_y=None, height=dpw(36), padding=[dpw(8), "0dp"])
        self.themed_bg[table_header] = "table_header_bg"

        th_date = Label(text="Tanggal", color=palette["text_primary"], bold=True, font_size=spw(13), size_hint_x=0.36, halign="left", valign="middle")
        th_date.bind(size=th_date.setter('text_size'))
        self.themed_text[th_date] = "text_primary"

        th_in = Label(text="Kamu Menerima", color=(0.1, 0.6, 0.2, 1), bold=True, font_size=spw(13), size_hint_x=0.32, halign="center", valign="middle")
        th_in.bind(size=th_in.setter('text_size'))

        th_out = Label(text="Kamu Membayar", color=(0.85, 0.25, 0.2, 1), bold=True, font_size=spw(13), size_hint_x=0.32, halign="center", valign="middle")
        th_out.bind(size=th_out.setter('text_size'))

        table_header.add_widget(th_date)
        table_header.add_widget(th_in)
        table_header.add_widget(th_out)
        phone_frame.add_widget(table_header)

        # Scroll Area Daftar Transaksi
        self.scroll_view = ScrollView(size_hint=(1, 1))
        self.tx_container = GridLayout(cols=1, spacing=dpw(1), size_hint_y=None)
        self.tx_container.bind(minimum_height=self.tx_container.setter('height'))
        self.scroll_view.add_widget(self.tx_container)
        phone_frame.add_widget(self.scroll_view)

        # Tombol Aksi Input
        btn_layout = ColorBoxLayout(bg_color=palette["phone_bg"], size_hint_y=None, height=dpw(52), padding=dpw(6), spacing=dpw(6))
        self.themed_bg[btn_layout] = "phone_bg"

        btn_in = Button(
            text="Kamu Menerima", background_normal='', background_color=(0.2, 0.65, 0.3, 1),
            bold=True, font_size=spw(14), halign="center", valign="middle"
        )
        btn_in.bind(on_release=lambda x: self.open_tx_screen("Menerima"))

        btn_out = Button(
            text="Kamu Membayar", background_normal='', background_color=(0.85, 0.25, 0.2, 1),
            bold=True, font_size=spw(14), halign="center", valign="middle"
        )
        btn_out.bind(on_release=lambda x: self.open_tx_screen("Membayar"))

        btn_layout.add_widget(btn_in)
        btn_layout.add_widget(btn_out)
        phone_frame.add_widget(btn_layout)

        # Footer Saldo
        footer = ColorBoxLayout(bg_color=palette["footer_bg"], size_hint_y=None, height=dpw(46))
        self.themed_bg[footer] = "footer_bg"

        box_in = BoxLayout(orientation='vertical')
        lbl_in_title = Label(text="Total Menerima", color=palette["text_muted"], font_size=spw(12), halign="center")
        self.themed_text[lbl_in_title] = "text_muted"
        box_in.add_widget(lbl_in_title)
        self.lbl_total_in = Label(text="0", color=(0.1, 0.6, 0.2, 1), bold=True, font_size=spw(13), halign="center")
        box_in.add_widget(self.lbl_total_in)

        box_out = BoxLayout(orientation='vertical')
        lbl_out_title = Label(text="Total Membayar", color=palette["text_muted"], font_size=spw(12), halign="center")
        self.themed_text[lbl_out_title] = "text_muted"
        box_out.add_widget(lbl_out_title)
        self.lbl_total_out = Label(text="0", color=(0.85, 0.25, 0.2, 1), bold=True, font_size=spw(13), halign="center")
        box_out.add_widget(self.lbl_total_out)

        box_balance = BoxLayout(orientation='vertical')
        lbl_balance_title = Label(text="Saldo", color=palette["text_muted"], font_size=spw(12), halign="center")
        self.themed_text[lbl_balance_title] = "text_muted"
        box_balance.add_widget(lbl_balance_title)
        self.lbl_balance = Label(text="0", color=(0.1, 0.4, 0.8, 1), bold=True, font_size=spw(13), halign="center")
        box_balance.add_widget(self.lbl_balance)

        footer.add_widget(box_in)
        footer.add_widget(box_out)
        footer.add_widget(box_balance)
        phone_frame.add_widget(footer)

        self.add_widget(outer_layout)

        # Tampilkan data yang sudah dimuat dari database saat aplikasi dibuka
        self.refresh_ui()

    def _load_transactions(self, book_name):
        """Ambil transaksi milik satu buku kas dari database, siap dipakai UI."""
        rows = self.db.get_transactions(book_name)
        for r in rows:
            r["amount"] = float(r["amount"])
            r["note"] = r["note"] or ""
            r["time_str"] = r.get("time_str") or ""
            r["edited_at"] = r.get("edited_at")
        return rows

    # --- FITUR TEMA ---
    def toggle_theme(self, instance=None):
        self.theme = "dark" if self.theme == "light" else "light"
        palette = THEMES[self.theme]
        self.btn_theme.icon_widget.source = os.path.join(
            ICON_DIR, "icon_sun.png" if self.theme == "light" else "icon_moon.png"
        )

        for widget, key in self.themed_bg.items():
            widget.set_bg_color(palette[key])
        for label, key in self.themed_text.items():
            label.color = palette[key]

        for tab, btn in self.tab_buttons.items():
            is_active = (tab == self.current_filter)
            btn.background_color = palette["tab_active"] if is_active else palette["tab_inactive"]

        self.refresh_ui()

    # --- FITUR FILTER PERIODE (Semua / Harian / Mingguan / Bulanan / Tahunan) ---
    def set_filter(self, filter_name):
        self.current_filter = filter_name
        palette = THEMES[self.theme]
        for tab, btn in self.tab_buttons.items():
            is_active = (tab == filter_name)
            btn.background_color = palette["tab_active"] if is_active else palette["tab_inactive"]
            btn.bold = is_active
        self.refresh_ui()

    def _matches_filter(self, tx, today=None):
        if self.current_filter == "Semua":
            return True
        today = today or datetime.now().date()
        try:
            tx_date = datetime.strptime(tx['date_str'], "%d-%b-%Y").date()
        except (ValueError, TypeError):
            return True

        if self.current_filter == "Harian":
            return tx_date == today
        if self.current_filter == "Mingguan":
            start_week = today - timedelta(days=today.weekday())
            end_week = start_week + timedelta(days=6)
            return start_week <= tx_date <= end_week
        if self.current_filter == "Bulanan":
            return tx_date.year == today.year and tx_date.month == today.month
        if self.current_filter == "Tahunan":
            return tx_date.year == today.year
        return True

    def _matches_search(self, tx):
        """Cocokkan catatan transaksi dengan kata kunci pencarian (abaikan kapital)."""
        q = self.search_query.strip().lower()
        if not q:
            return True
        return q in (tx.get('note') or "").lower()

    def _sort_key(self, tx):
        """Kunci urut: tanggal lalu jam, ditambah id sebagai penentu akhir."""
        try:
            day = datetime.strptime(tx['date_str'], "%d-%b-%Y")
        except (ValueError, TypeError):
            day = datetime.min
        time_s = tx.get('time_str') or "00:00"
        try:
            hm = datetime.strptime(time_s, "%H:%M")
        except (ValueError, TypeError):
            hm = datetime.min
        return (day.date(), hm.time(), tx.get('id') or 0)

    def _subheader_text(self):
        today = datetime.now()
        if self.current_filter == "Semua":
            return "Semua Transaksi"
        if self.current_filter == "Harian":
            return f"Hari ini, {today.strftime('%d %b %Y')}"
        if self.current_filter == "Mingguan":
            start_week = today.date() - timedelta(days=today.weekday())
            end_week = start_week + timedelta(days=6)
            return f"Minggu ini, {start_week.strftime('%d %b')} - {end_week.strftime('%d %b %Y')}"
        if self.current_filter == "Bulanan":
            return f"{self.BULAN_ID[today.month - 1]} {today.year}"
        if self.current_filter == "Tahunan":
            return f"Tahun {today.year}"
        return "Semua Transaksi"

    # --- FITUR PENGELOLAAN MULTI BUKU KAS ---
    def open_book_manager_popup(self, instance):
        content = BoxLayout(orientation='vertical', spacing=dpw(10), padding=dpw(10))

        lbl_info = Label(text="Pilih atau Buat Buku Kas:", size_hint_y=None, height=dpw(24), font_size=spw(13))
        content.add_widget(lbl_info)

        # Scroll Daftar Buku Kas
        scroll = ScrollView(size_hint=(1, 1))
        book_list_layout = GridLayout(cols=1, spacing=dpw(6), size_hint_y=None)
        book_list_layout.bind(minimum_height=book_list_layout.setter('height'))

        popup = Popup(title="Kelola Buku Kas", content=content, size_hint=(None, None), size=popup_size(320, 440))

        for book_name in self.books.keys():
            row = BoxLayout(size_hint_y=None, height=dpw(40), spacing=dpw(4))

            # Tombol Pilih Buku
            is_active = (book_name == self.current_book_name)
            btn_select = Button(
                text=f"{'âœ“ ' if is_active else ''}{book_name}",
                background_color=(0.1, 0.5, 0.88, 1) if is_active else (0.8, 0.8, 0.8, 1),
                font_size=spw(13), font_name=dejavu_font()
            )
            btn_select.bind(on_release=lambda x, name=book_name: self.switch_book(name, popup))

            # Tombol Edit Nama Kas
            btn_edit = Button(text="âœ", size_hint_x=None, width=dpw(40), font_size=spw(13), font_name=dejavu_font())
            btn_edit.bind(on_release=lambda x, name=book_name: self.open_rename_popup(name, popup))

            row.add_widget(btn_select)
            row.add_widget(btn_edit)
            book_list_layout.add_widget(row)

        scroll.add_widget(book_list_layout)
        content.add_widget(scroll)

        # Tombol Tambah Buku Kas Baru
        btn_add_new = Button(
            text="+ Buat Buku Kas Baru", size_hint_y=None, height=dpw(40),
            background_normal='', background_color=(0.2, 0.65, 0.3, 1), bold=True, font_size=spw(13)
        )
        btn_add_new.bind(on_release=lambda x: self.open_create_book_popup(popup))
        content.add_widget(btn_add_new)

        popup.open()

    def switch_book(self, book_name, parent_popup):
        self.current_book_name = book_name
        self.btn_book_selector.text = self.current_book_name
        self.refresh_ui()
        parent_popup.dismiss()

    def open_create_book_popup(self, parent_popup):
        parent_popup.dismiss()

        content = BoxLayout(orientation='vertical', spacing=dpw(10), padding=dpw(10))
        txt_input = TextInput(hint_text="Nama Buku Kas Baru", multiline=False, size_hint_y=None, height=dpw(40), font_size=spw(14))

        btn_box = BoxLayout(size_hint_y=None, height=dpw(40), spacing=dpw(6))
        btn_save = Button(text="Simpan", background_color=(0.1, 0.5, 0.88, 1))

        popup = Popup(title="Buat Buku Kas Baru", content=content, size_hint=(None, None), size=popup_size(300, 200))

        def save_new_book(instance):
            new_name = txt_input.text.strip()
            if new_name and new_name not in self.books:
                if self.db.add_book(new_name):
                    self.books[new_name] = []
                    self.current_book_name = new_name
                    self.btn_book_selector.text = self.current_book_name
                    self.refresh_ui()
                    popup.dismiss()

        btn_save.bind(on_release=save_new_book)
        btn_box.add_widget(btn_save)

        content.add_widget(txt_input)
        content.add_widget(btn_box)
        popup.open()

    def open_rename_popup(self, old_name, parent_popup):
        parent_popup.dismiss()

        content = BoxLayout(orientation='vertical', spacing=dpw(10), padding=dpw(10))
        txt_input = TextInput(text=old_name, multiline=False, size_hint_y=None, height=dpw(40), font_size=spw(14))

        btn_box = BoxLayout(size_hint_y=None, height=dpw(40), spacing=dpw(6))
        btn_save = Button(text="Ubah Nama", background_color=(0.1, 0.5, 0.88, 1))

        popup = Popup(title="Kustom Nama Buku Kas", content=content, size_hint=(None, None), size=popup_size(300, 200))

        def rename_book(instance):
            new_name = txt_input.text.strip()
            if new_name and new_name != old_name:
                if self.db.rename_book(old_name, new_name):
                    self.books[new_name] = self.books.pop(old_name)
                    if self.current_book_name == old_name:
                        self.current_book_name = new_name
                        self.btn_book_selector.text = self.current_book_name
                    self.refresh_ui()
                    popup.dismiss()

        btn_save.bind(on_release=rename_book)
        btn_box.add_widget(btn_save)

        content.add_widget(txt_input)
        content.add_widget(btn_box)
        popup.open()

    # --- LOGIKA TRANSAKSI BUKU KAS ---
    def open_tx_screen(self, tx_type):
        app = App.get_running_app()
        app.tx_screen.set_theme(self.theme)
        app.tx_screen.set_mode_add(tx_type)
        app.sm.current = "transaction"

    def save_or_update_transaction(self, tx_data):
        current_tx_list = self.books[self.current_book_name]

        if tx_data['id'] is None:
            # Transaksi baru -> simpan ke database, ambil id hasil auto-increment
            new_id = self.db.add_transaction(
                self.current_book_name,
                tx_data['tx_type'],
                tx_data['date_str'],
                tx_data.get('time_str', ''),
                tx_data['amount'],
                tx_data['note'],
            )
            tx_data['id'] = new_id
            tx_data['edited_at'] = None
            current_tx_list.append(tx_data)
        else:
            # Transaksi lama -> update di database, dan catat kapan diedit
            edited_at = self.db.update_transaction(
                tx_data['id'],
                tx_data['tx_type'],
                tx_data['date_str'],
                tx_data.get('time_str', ''),
                tx_data['amount'],
                tx_data['note'],
            )
            tx_data['edited_at'] = edited_at
            for idx, item in enumerate(current_tx_list):
                if item['id'] == tx_data['id']:
                    current_tx_list[idx] = tx_data
                    break
        self.refresh_ui()
        return tx_data['id']

    def delete_transaction(self, tx_id):
        self.db.delete_transaction(tx_id)
        self.books[self.current_book_name] = [t for t in self.books[self.current_book_name] if t['id'] != tx_id]
        self.refresh_ui()

    # --- FITUR EKSPOR (Excel / Dokumen Word / PDF) ---
    def export_to_excel(self, instance):
        """Verifikasi dulu sebelum ekspor, sekaligus pilih format file."""
        rows = list(self.books.get(self.current_book_name, []))
        if not rows:
            self._show_info_popup("Tidak ada data", "Belum ada transaksi untuk diekspor.")
            return

        content = BoxLayout(orientation='vertical', spacing=dpw(10), padding=dpw(12))
        info = Label(
            text=f"Ekspor {len(rows)} transaksi dari buku kas\n'{self.current_book_name}'\nke folder Downloads?",
            font_size=spw(13), halign="center", valign="middle"
        )
        info.bind(size=info.setter('text_size'))
        content.add_widget(info)

        popup = Popup(title="Konfirmasi Ekspor", content=content, size_hint=(None, None), size=popup_size(340, 320))

        def do_export(kind):
            self._do_export(rows, kind)
            popup.dismiss()

        btn_row1 = BoxLayout(size_hint_y=None, height=dpw(44), spacing=dpw(6))
        btn_xlsx = Button(text="Excel (.xlsx)", background_color=(0.1, 0.5, 0.88, 1), bold=True)
        btn_xlsx.bind(on_release=lambda x, k="xlsx": do_export(k))
        btn_row1.add_widget(btn_xlsx)
        content.add_widget(btn_row1)

        btn_row2 = BoxLayout(size_hint_y=None, height=dpw(44), spacing=dpw(6))
        btn_docx = Button(text="Dokumen (.docx)", background_color=(0.1, 0.5, 0.88, 1))
        btn_docx.bind(on_release=lambda x, k="docx": do_export(k))
        btn_row2.add_widget(btn_docx)
        btn_pdf = Button(text="PDF (.pdf)", background_color=(0.1, 0.5, 0.88, 1))
        btn_pdf.bind(on_release=lambda x, k="pdf": do_export(k))
        btn_row2.add_widget(btn_pdf)
        content.add_widget(btn_row2)

        btn_cancel = Button(text="Batal", size_hint_y=None, height=dpw(40), background_color=(0.85, 0.25, 0.2, 1))
        btn_cancel.bind(on_release=popup.dismiss)
        content.add_widget(btn_cancel)

        popup.open()

    def _do_export(self, rows, kind):
        """Tulis file sesuai format (xlsx / docx / pdf) ke folder Downloads."""
        base_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.isdir(base_dir):
            base_dir = os.getcwd()

        safe_name = "".join(c for c in self.current_book_name if c.isalnum() or c in " _-").strip() or "Buku_Kas"
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        ext = {"xlsx": ".xlsx", "docx": ".docx", "pdf": ".pdf"}[kind]
        path = os.path.join(base_dir, f"{safe_name}_{stamp}{ext}")
        ordered = sorted(rows, key=self._sort_key, reverse=(self.sort_order != "asc"))

        try:
            if kind == "xlsx":
                path = self._export_xlsx(ordered, path)
            elif kind == "docx":
                path = self._export_docx(ordered, path)
            else:
                path = self._export_pdf(ordered, path)
        except ImportError as e:
            self._show_info_popup("Ekspor gagal", f"Modul '{e.name}' belum terpasang. Jalankan di terminal:\npip install {e.name}")
            return

        self._show_info_popup("Ekspor berhasil", f"File disimpan di:\n{path}\n\n{len(rows)} transaksi.")

    @staticmethod
    def _export_xlsx(ordered, path):
        import openpyxl
        from openpyxl.styles import Font

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Transaksi"
        headers = ["Tanggal", "Jam", "Tipe", "Nominal", "Catatan", "Diedit"]
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for tx in ordered:
            ws.append([
                tx.get('date_str', ""),
                tx.get('time_str', "") or "",
                tx['tx_type'],
                int(tx['amount']),
                tx.get('note', "") or "",
                tx.get('edited_at') or "",
            ])
        wb.save(path)
        return path

    def _export_docx(self, ordered, path):
        import docx

        doc = docx.Document()
        doc.add_heading(f"Buku Kas: {self.current_book_name}", level=0)
        doc.add_heading(f"Daftar Transaksi ({len(ordered)})", level=1)

        table = doc.add_table(rows=1, cols=6)
        table.style = "Table Grid"
        headers = ["Tanggal", "Jam", "Tipe", "Nominal", "Catatan", "Diedit"]
        for i, h in enumerate(headers):
            table.rows[0].cells[i].text = h
        for cell in table.rows[0].cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.bold = True

        for tx in ordered:
            cells = table.add_row().cells
            cells[0].text = tx.get('date_str', "")
            cells[1].text = tx.get('time_str', "") or ""
            cells[2].text = tx['tx_type']
            cells[3].text = f"{int(tx['amount']):,}"
            cells[4].text = tx.get('note', "") or ""
            cells[5].text = tx.get('edited_at') or ""

        total_in = sum(tx['amount'] for tx in ordered if tx['tx_type'] == "Menerima")
        total_out = sum(tx['amount'] for tx in ordered if tx['tx_type'] != "Menerima")
        doc.add_paragraph()
        for label, value in [("Total Masuk", int(total_in)), ("Total Keluar", int(total_out)), ("Saldo", int(total_in - total_out))]:
            para = doc.add_paragraph()
            para.add_run(f"{label}:  ").bold = True
            para.add_run(f"{value:,}")

        doc.save(path)
        return path

    def _export_pdf(self, ordered, path):
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph

        def esc(text):
            return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm,
                                topMargin=15*mm, bottomMargin=15*mm)
        story = [
            Paragraph(f"<b>Buku Kas: {esc(self.current_book_name)}</b>", styles["Title"]),
            Paragraph(f"<b>Daftar Transaksi ({len(ordered)})</b>", styles["Heading2"]),
        ]

        data = [["Tanggal", "Jam", "Tipe", "Nominal", "Catatan", "Diedit"]]
        for tx in ordered:
            data.append([
                tx.get('date_str', ""),
                tx.get('time_str', "") or "",
                tx['tx_type'],
                f"{int(tx['amount']):,}",
                Paragraph(esc(tx.get('note') or ""), styles["Normal"]),
                tx.get('edited_at') or "",
            ])
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f6db3")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef3fa")]),
        ]))
        story.append(table)

        total_in = sum(tx['amount'] for tx in ordered if tx['tx_type'] == "Menerima")
        total_out = sum(tx['amount'] for tx in ordered if tx['tx_type'] != "Menerima")
        for label, value in [("Total Masuk", int(total_in)), ("Total Keluar", int(total_out)), ("Saldo", int(total_in - total_out))]:
            story.append(Paragraph(f"<b>{label}:</b> {value:,}", styles["Normal"]))

        doc.build(story)
        return path

    def _show_info_popup(self, title, message):
        content = BoxLayout(orientation='vertical', spacing=dpw(10), padding=dpw(12))
        lbl = Label(text=message, font_size=spw(13), halign="center", valign="middle")
        lbl.bind(size=lbl.setter('text_size'))
        content.add_widget(lbl)
        btn = Button(text="Tutup", size_hint_y=None, height=dpw(40), background_color=(0.1, 0.5, 0.88, 1))
        content.add_widget(btn)
        popup = Popup(title=title, content=content, size_hint=(None, None), size=popup_size(360, 240))
        btn.bind(on_release=popup.dismiss)
        popup.open()

    # --- FITUR CARI BERDASARKAN CATATAN ---
    def open_search_popup(self, instance):
        content = BoxLayout(orientation='vertical', spacing=dpw(10), padding=dpw(12))
        lbl = Label(text="Cari transaksi berdasarkan catatan:", size_hint_y=None, height=dpw(24), font_size=spw(13))
        content.add_widget(lbl)

        txt_search = TextInput(
            text=self.search_query, hint_text="Ketik sebagian kata di catatan...",
            multiline=False, size_hint_y=None, height=dpw(40), font_size=spw(14),
            background_color=THEMES[self.theme]["input_bg"],
            foreground_color=THEMES[self.theme]["input_text"]
        )
        content.add_widget(txt_search)

        count_lbl = Label(text="", size_hint_y=None, height=dpw(20), font_size=spw(12))
        content.add_widget(count_lbl)

        popup = Popup(title="Cari Catatan", content=content, size_hint=(None, None), size=popup_size(340, 320))

        def apply_search(instance=None):
            self.search_query = txt_search.text.strip()
            self.refresh_ui()
            popup.dismiss()

        def clear_search(instance=None):
            self.search_query = ""
            txt_search.text = ""
            self.refresh_ui()
            popup.dismiss()

        def live_count(*args):
            q = txt_search.text.strip().lower()
            total = sum(1 for tx in self.books.get(self.current_book_name, [])
                        if self._matches_filter(tx) and (not q or q in (tx.get('note') or "").lower()))
            count_lbl.text = (f"{total} transaksi ditemukan" if q else "Tampilkan semua transaksi")

        txt_search.bind(text=live_count, on_text_validate=apply_search)
        txt_search.focus = True

        btn_box = BoxLayout(size_hint_y=None, height=dpw(40), spacing=dpw(6))
        btn_clear = Button(text="Hapus", background_color=(0.85, 0.25, 0.2, 1))
        btn_clear.bind(on_release=clear_search)
        btn_apply = Button(text="Cari", background_color=(0.1, 0.5, 0.88, 1), bold=True)
        btn_apply.bind(on_release=apply_search)
        btn_box.add_widget(btn_clear)
        btn_box.add_widget(btn_apply)
        content.add_widget(btn_box)

        live_count()
        popup.open()

    # --- FITUR URUTKAN BERDASARKAN TANGGAL ---
    def open_sort_menu(self, instance):
        content = BoxLayout(orientation='vertical', spacing=dpw(8), padding=dpw(12))

        def pick(order):
            self.sort_order = order
            self.refresh_ui()
            menu.dismiss()

        btn_desc = Button(
            text="âœ“ Tanggal Menurun (terbaru dulu)" if self.sort_order == "desc" else "Tanggal Menurun (terbaru dulu)",
            size_hint_y=None, height=dpw(44), font_size=spw(13), font_name=dejavu_font(),
            background_color=(0.1, 0.5, 0.88, 1) if self.sort_order == "desc" else (0.8, 0.8, 0.8, 1),
            color=(1, 1, 1, 1) if self.sort_order == "desc" else (0.1, 0.1, 0.1, 1),
            bold=(self.sort_order == "desc")
        )
        btn_desc.bind(on_release=lambda x: pick("desc"))

        btn_asc = Button(
            text="âœ“ Tanggal Naik (terlama dulu)" if self.sort_order == "asc" else "Tanggal Naik (terlama dulu)",
            size_hint_y=None, height=dpw(44), font_size=spw(13), font_name=dejavu_font(),
            background_color=(0.1, 0.5, 0.88, 1) if self.sort_order == "asc" else (0.8, 0.8, 0.8, 1),
            color=(1, 1, 1, 1) if self.sort_order == "asc" else (0.1, 0.1, 0.1, 1),
            bold=(self.sort_order == "asc")
        )
        btn_asc.bind(on_release=lambda x: pick("asc"))

        content.add_widget(btn_desc)
        content.add_widget(btn_asc)

        menu = Popup(title="Urutkan berdasarkan tanggal", content=content, size_hint=(None, None), size=popup_size(340, 200))
        menu.open()

    def refresh_ui(self):
        self.tx_container.clear_widgets()
        self.total_in = 0
        self.total_out = 0
        palette = THEMES[self.theme]

        q = self.search_query.strip()
        self.lbl_subheader.text = self._subheader_text() + (f" Â· Cari: '{q}'" if q else "")

        active_transactions = self.books.get(self.current_book_name, [])
        filtered_transactions = [tx for tx in active_transactions
                                 if self._matches_filter(tx) and self._matches_search(tx)]

        ordered = sorted(filtered_transactions, key=self._sort_key, reverse=(self.sort_order != "asc"))

        for tx in ordered:
            row = TransactionRow(tx_data=tx, palette=palette)
            self.tx_container.add_widget(row)

            if tx['tx_type'] == "Menerima":
                self.total_in += tx['amount']
            else:
                self.total_out += tx['amount']

        self.lbl_total_in.text = f"{int(self.total_in):,}"
        self.lbl_total_out.text = f"{int(self.total_out):,}"
        self.lbl_balance.text = f"{int(self.total_in - self.total_out):,}"


# --- 2. HALAMAN INPUT / EDIT TRANSAKSI ---
class TransactionScreen(Screen):
    tx_type = StringProperty("Menerima")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_tx_id = None
        self.pending_attachments = []
        self.persisted_attachment_paths = set()
        self.today_date = datetime.now().strftime("%d-%b-%Y")
        self.today_time = datetime.now().strftime("%I:%M %p")
        self.theme = "light"
        self.build_ui()

    def set_theme(self, theme):
        """Terapkan tema saat masuk layar transaksi tanpa kehilangan isian."""
        if getattr(self, "theme", None) == theme and hasattr(self, "outer_layout"):
            return
        self.theme = theme
        self.rebuild()
        if hasattr(self, "btn_attachments"):
            self.btn_attachments.icon_widget.color = (
                (0, 0, 0, 1) if self.theme == "light" else (1, 1, 1, 1)
            )

    def rebuild(self):
        """Bangun ulang halaman (saat skala/ukuran jendela berubah) tanpa
        menghilangkan teks yang sedang diketik / mode edit yang aktif."""
        saved = {}
        if hasattr(self, 'amount_input'):
            saved = {
                'amount': self.amount_input.text,
                'note': self.note_input.text,
                'id': self.current_tx_id,
                'date': self.today_date,
                'time': self.today_time,
                'type': self.tx_type,
                'attachments': list(self.pending_attachments),
                'persisted': set(self.persisted_attachment_paths),
            }
        self.build_ui()
        if saved:
            self.amount_input.text = saved['amount']
            self.note_input.text = saved['note']
            self.current_tx_id = saved['id']
            self.today_date = saved['date']
            self.today_time = saved['time']
            self.date_input.text = f" <  {saved['date']}  > "
            self.time_input.text = saved['time']
            self.set_type(saved['type'])
            self.pending_attachments = saved.get('attachments', [])
            self.persisted_attachment_paths = saved.get('persisted', set())
            self._update_attachment_label()
            if saved['id'] is not None:
                self.btn_delete.opacity = 1
                self.btn_delete.disabled = False

    def build_ui(self):
        self.clear_widgets()
        palette = THEMES[self.theme]

        outer_layout = ResponsiveLayout(bg_color=palette["app_bg"])
        self.outer_layout = outer_layout

        # Frame Konten Utama: mengisi layar (responsive)
        phone_frame = ColorBoxLayout(
            bg_color=palette["phone_bg"],
            orientation='vertical',
            size_hint=(None, None)
        )
        outer_layout.set_content(phone_frame)

        # Header Transaksi
        self.header = ColorBoxLayout(bg_color=palette["header_bg"], size_hint_y=None, height=dpw(50), padding=[dpw(12), "0dp"])
        btn_back = Button(text="â†", size_hint_x=0.15, background_color=(0, 0, 0, 0), color=(1, 1, 1, 1), font_size=spw(20), font_name=dejavu_font())
        btn_back.bind(on_release=self.go_back)

        self.lbl_title = Label(text="Kamu Menerima", font_size=spw(18), bold=True, color=(1, 1, 1, 1), size_hint_x=0.7, halign="left", valign="middle")
        self.lbl_title.bind(size=self.lbl_title.setter('text_size'))

        self.header.add_widget(btn_back)
        self.header.add_widget(self.lbl_title)
        self.header.add_widget(Label(text="â‹®", size_hint_x=0.15, font_size=spw(20), halign="right", color=(1, 1, 1, 1), font_name=dejavu_font()))
        phone_frame.add_widget(self.header)

        # Form Card
        form_card = ColorBoxLayout(bg_color=palette["card_bg"], orientation='vertical', padding=dpw(14), spacing=dpw(12), size_hint_y=None, height=dpw(260))

        # Toggle Button Menerima / Membayar
        toggle_box = BoxLayout(size_hint_y=None, height=dpw(38), spacing=dpw(8))

        self.btn_type_in = Button(
            text="Kamu Menerima", background_normal='', font_size=spw(14),
            halign="center", valign="middle", color=(1, 1, 1, 1)
        )
        self.btn_type_in.bind(on_release=lambda x: self.set_type("Menerima"))

        self.btn_type_out = Button(
            text="Kamu Membayar", background_normal='', font_size=spw(14),
            halign="center", valign="middle", color=(1, 1, 1, 1)
        )
        self.btn_type_out.bind(on_release=lambda x: self.set_type("Membayar"))

        toggle_box.add_widget(self.btn_type_in)
        toggle_box.add_widget(self.btn_type_out)
        form_card.add_widget(toggle_box)

        # Date & Time (waktu ikut tersimpan bersama tanggal)
        dt_box = BoxLayout(size_hint_y=None, height=dpw(36), spacing=dpw(6))

        self.date_input = TextInput(
            text=f" <  {self.today_date}  > ", multiline=False, readonly=True,
            font_size=spw(13), background_color=palette["input_bg"],
            foreground_color=palette["input_text"], hint_text_color=palette["text_secondary"]
        )
        self.time_input = TextInput(
            text=self.today_time, multiline=False, readonly=True,
            font_size=spw(13), background_color=palette["input_bg"],
            foreground_color=palette["input_text"], hint_text_color=palette["text_secondary"]
        )
        dt_box.add_widget(self.date_input)
        dt_box.add_widget(self.time_input)
        form_card.add_widget(dt_box)

        # Ikon lampiran di bawah jam. Ikon ekspor dipakai sebagai ikon clip
        # karena sudah berupa PNG yang kompatibel dengan semua Android.
        attachment_row = BoxLayout(size_hint_y=None, height=dpw(38), spacing=dpw(6))
        self.btn_attachments = icon_button(
            "icon_clip.png", on_release=self.open_attachments_menu,
            size_hint_x=None, width_dp=38, icon_ratio=0.72,
        )
        self.btn_attachments.icon_widget.color = (
            (0, 0, 0, 1) if self.theme == "light" else (1, 1, 1, 1)
        )
        attachment_row.add_widget(self.btn_attachments)
        self.lbl_attachments = Label(
            text="Tambahkan tagihan", size_hint_x=1, halign="left",
            valign="middle", font_size=spw(13), color=palette["text_secondary"],
        )
        self.lbl_attachments.bind(size=self.lbl_attachments.setter("text_size"))
        attachment_row.add_widget(self.lbl_attachments)
        form_card.add_widget(attachment_row)

        # Input Nominal
        self.amount_input = TextInput(
            hint_text="Kamu Menerima", input_filter='int', multiline=False,
            size_hint_y=None, height=dpw(42), font_size=spw(16),
            background_color=palette["input_bg"], foreground_color=palette["input_text"],
            hint_text_color=palette["text_secondary"]
        )
        form_card.add_widget(self.amount_input)

        # Input Catatan
        self.note_input = TextInput(
            hint_text="Catatan", multiline=False,
            size_hint_y=None, height=dpw(42), font_size=spw(15),
            background_color=palette["input_bg"], foreground_color=palette["input_text"],
            hint_text_color=palette["text_secondary"]
        )
        form_card.add_widget(self.note_input)

        phone_frame.add_widget(form_card)
        phone_frame.add_widget(BoxLayout())  # Spacer

        # Tombol Bawah (Hapus, Simpan & Keluar, Simpan & Lanjutkan)
        bottom_box = ColorBoxLayout(bg_color=palette["phone_bg"], size_hint_y=None, height=dpw(56), padding=dpw(4), spacing=dpw(4))

        self.btn_delete = Button(
            text="Hapus", background_normal='',
            background_color=(0.85, 0.25, 0.2, 1), bold=True, font_size=spw(13), size_hint_x=0.25
        )
        self.btn_delete.bind(on_release=self.delete_current_data)

        btn_save_exit = Button(
            text="Simpan &\nKeluar", background_normal='',
            background_color=(0.7, 0.85, 1, 1), color=(0, 0, 0, 1), font_size=spw(12), halign="center", size_hint_x=0.375
        )
        btn_save_exit.bind(on_release=lambda x: self.save_data(close=True))

        btn_save_cont = Button(
            text="Simpan &\nLanjutkan", background_normal='',
            background_color=(0.1, 0.5, 0.88, 1), bold=True, font_size=spw(12), halign="center", size_hint_x=0.375
        )
        btn_save_cont.bind(on_release=lambda x: self.save_data(close=False))

        bottom_box.add_widget(self.btn_delete)
        bottom_box.add_widget(btn_save_exit)
        bottom_box.add_widget(btn_save_cont)
        phone_frame.add_widget(bottom_box)

        self.add_widget(outer_layout)

        # State awal: mode tambah (hapus disembunyikan) kecuali sedang edit
        self.btn_delete.opacity = 0
        self.btn_delete.disabled = True
        if self.current_tx_id is not None:
            self.btn_delete.opacity = 1
            self.btn_delete.disabled = False

    # --- LAMPIRAN FOTO / PDF ---
    def _update_attachment_label(self):
        if not hasattr(self, "lbl_attachments"):
            return
        count = len(self.pending_attachments)
        self.lbl_attachments.text = (
            f"{count} foto/PDF dipilih" if count else "Tambahkan tagihan"
        )

    def _with_permissions(self, names, action, denied_message=None):
        """Jalankan ``action`` setelah izin Android yang dibutuhkan diberikan."""
        missing = _android_missing_permissions(names)
        if not missing:
            action()
            return
        try:
            from android.permissions import request_permissions
        except Exception:
            # Bridge izin tidak tersedia; biarkan intent yang menjelaskan sendiri.
            action()
            return
        message = denied_message or "Izin Android tidak diberikan."

        def on_result(_permissions, grants):
            if grants and all(grants):
                Clock.schedule_once(lambda _dt: action(), 0.05)
            else:
                Clock.schedule_once(lambda _dt: self._media_error(message), 0.05)

        request_permissions(missing, on_result)

    def _picker_cancelled(self):
        """Pengguna menutup Files/Galeri tanpa memilih apa pun."""
        return None

    def _choose_files(self, filters=None):
        if _is_android():
            # Storage Access Framework memberi akses per-file, tanpa izin penyimpanan.
            pdf_only = bool(filters) and all(
                str(item).lower().endswith(".pdf") for item in filters
            )
            _android_open_documents(
                "application/pdf" if pdf_only else "*/*", True,
                self._files_selected, self._picker_cancelled,
            )
            return
        try:
            from plyer import filechooser
        except ImportError:
            self._media_error("File picker belum tersedia. Jalankan build dengan paket plyer.")
            return
        filechooser.open_file(
            title="Pilih foto atau PDF",
            filters=filters or ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.pdf"],
            multiple=True,
            on_selection=self._files_selected,
        )

    def _take_photo(self):
        if _is_android():
            names = ["CAMERA"]
            if 0 < _android_sdk_int() < 29:
                # Sebelum scoped storage, menulis ke MediaStore publik butuh izin ini.
                names.append("WRITE_EXTERNAL_STORAGE")
            self._with_permissions(
                names,
                lambda: _android_take_photo(self._camera_complete, self._media_error),
                denied_message="Izin kamera tidak diberikan, jadi foto tidak bisa diambil.",
            )
            return
        try:
            from plyer import camera
        except ImportError:
            self._media_error("Kamera belum tersedia. Jalankan build dengan paket plyer.")
            return
        target = os.path.join(_app_data_dir(), "camera",
                               f"kas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        camera.capture(target, on_complete=self._camera_complete)

    def _camera_complete(self, path):
        if path:
            self._files_selected([path])
        else:
            self._media_error("Kamera dibatalkan atau tidak menghasilkan foto.")

    def _files_selected(self, selection):
        failed = 0
        for source in selection or []:
            if not source:
                failed += 1
                continue
            source = str(source)
            original_name, source_mime = _android_uri_metadata(source)
            stored = _copy_to_app_storage(source, original_name)
            if not stored:
                failed += 1
                continue
            self.pending_attachments.append({
                "path": stored,
                "name": original_name,
                "mime": source_mime or _guess_mime(stored),
            })
        self._update_attachment_label()
        if failed:
            self._media_error(f"{failed} file tidak bisa dibaca dari perangkat.")
        if self.pending_attachments:
            self.open_attachments_menu()

    def _media_error(self, message):
        if hasattr(self, "_show_media_error"):
            self._show_media_error(message)
        else:
            App.get_running_app().home_screen._show_info_popup("Lampiran", message)

    def _download_attachment(self, item):
        if _is_android() and 0 < _android_sdk_int() < 29:
            self._with_permissions(
                ["WRITE_EXTERNAL_STORAGE"],
                lambda: self._store_attachment(item),
                denied_message="Izin penyimpanan tidak diberikan, jadi file tidak bisa disimpan.",
            )
            return
        self._store_attachment(item)

    def _store_attachment(self, item):
        source = item.get("path", "")
        name = _safe_filename(item.get("name") or os.path.basename(source))
        mime = item.get("mime") or _guess_mime(source)
        android_result = _android_save_download(source, name, mime)
        if android_result:
            self._media_success(f"File tersimpan di:\n{android_result}")
            return
        folder = _downloads_buku_kas_dir()
        target = os.path.join(folder, name)
        try:
            shutil.copyfile(source, target)
            self._media_success(f"File tersimpan di:\n{target}")
        except (OSError, TypeError) as exc:
            self._media_error(f"Gagal menyimpan file: {exc}")

    def _media_success(self, message):
        App.get_running_app().home_screen._show_info_popup("Lampiran tersimpan", message)

    def _show_attachment_image(self, item, parent_popup):
        if _guess_mime(item.get("path", "")).startswith("image/"):
            parent_popup.dismiss()
            image = Image(source=item["path"], allow_stretch=True, keep_ratio=True)
            content = BoxLayout(orientation='vertical', spacing=dpw(8), padding=dpw(8))
            content.add_widget(Label(text=item.get("name", "Foto"), size_hint_y=None,
                                    height=dpw(24), font_size=spw(13)))
            content.add_widget(image)
            popup = Popup(title="Foto lampiran", content=content,
                          size_hint=(None, None), size=popup_size(340, 420))
            close = Button(text="Tutup", size_hint_y=None, height=dpw(40),
                           background_color=(0.1, 0.5, 0.88, 1))
            close.bind(on_release=popup.dismiss)
            content.add_widget(close)
            popup.open()
        else:
            self._media_error("PDF dipilih. Gunakan tombol Unduh untuk menyimpan atau membukanya di aplikasi PDF.")

    def _launch_media_action(self, action, parent_popup):
        """Tutup menu sebelum membuka dialog native Android."""
        parent_popup.dismiss()
        action()

    def open_attachments_menu(self, instance=None):
        content = BoxLayout(orientation='vertical', spacing=dpw(6), padding=dpw(10))
        popup = Popup(title="Lampiran transaksi", content=content,
                      size_hint=(None, None), size=popup_size(350, 480))

        def add_button(text, action, color):
            button = Button(text=text, size_hint_y=None, height=dpw(42),
                            background_color=color, font_size=spw(13))
            button.bind(on_release=lambda _x, fn=action: self._launch_media_action(fn, popup))
            content.add_widget(button)

        add_button("Pilih foto / file", self._choose_files, (0.1, 0.5, 0.88, 1))
        add_button("Ambil foto dengan kamera", self._take_photo, (0.2, 0.65, 0.3, 1))
        add_button("Pilih PDF", lambda: self._choose_files(["*.pdf"]), (0.65, 0.35, 0.15, 1))

        self._update_attachment_label()
        if self.pending_attachments:
            label = Label(text="Foto/PDF yang dipilih:", size_hint_y=None, height=dpw(22),
                          font_size=spw(12), halign="left", valign="middle")
            label.bind(size=label.setter("text_size"))
            content.add_widget(label)
            for item in self.pending_attachments:
                row = BoxLayout(size_hint_y=None, height=dpw(40), spacing=dpw(4))
                open_btn = Button(text="Lihat " + item.get("name", "file"),
                                  font_size=spw(11), halign="left")
                open_btn.bind(on_release=lambda _x, entry=item: self._show_attachment_image(entry, popup))
                download_btn = Button(text="Unduh", size_hint_x=None, width=dpw(72),
                                      background_color=(0.2, 0.65, 0.3, 1), font_size=spw(11))
                download_btn.bind(on_release=lambda _x, entry=item: self._download_attachment(entry))
                row.add_widget(open_btn)
                row.add_widget(download_btn)
                content.add_widget(row)

        close = Button(text="Tutup", size_hint_y=None, height=dpw(38),
                       background_color=(0.5, 0.5, 0.5, 1))
        close.bind(on_release=popup.dismiss)
        content.add_widget(close)
        popup.open()

    def set_mode_add(self, tx_type):
        self.current_tx_id = None
        self.amount_input.text = ""
        self.note_input.text = ""
        self.pending_attachments = []
        self.persisted_attachment_paths = set()
        self._update_attachment_label()

        # Selalu ambil tanggal & jam saat ini untuk transaksi baru
        self.today_date = datetime.now().strftime("%d-%b-%Y")
        self.today_time = datetime.now().strftime("%I:%M %p")
        self.date_input.text = f" <  {self.today_date}  > "
        self.time_input.text = self.today_time
        self.btn_delete.opacity = 0
        self.btn_delete.disabled = True
        self.set_type(tx_type)

    def set_mode_edit(self, tx_data):
        self.current_tx_id = tx_data['id']
        self.amount_input.text = str(int(tx_data['amount']))
        self.note_input.text = tx_data['note']
        self.pending_attachments = [
            {"path": a["path"], "name": a.get("original_name") or os.path.basename(a["path"]), "mime": a.get("mime_type")}
            for a in app.home_screen.db.get_attachments(tx_data['id'])
        ] if (app := App.get_running_app()) else []
        self.persisted_attachment_paths = {a["path"] for a in self.pending_attachments}
        self._update_attachment_label()
        self.today_date = tx_data['date_str']
        # Pertahankan jam pencatatan aslinya, bukan jam sekarang
        self.today_time = tx_data.get('time_str') or datetime.now().strftime("%I:%M %p")
        self.date_input.text = f" <  {self.today_date}  > "
        self.time_input.text = self.today_time
        self.btn_delete.opacity = 1
        self.btn_delete.disabled = False
        self.set_type(tx_data['tx_type'])

    def set_type(self, tx_type):
        self.tx_type = tx_type
        self.lbl_title.text = "Edit Transaksi" if self.current_tx_id else f"Kamu {tx_type}"
        self.amount_input.hint_text = f"Kamu {tx_type}"

        if tx_type == "Menerima":
            self.btn_type_in.background_color = (0.2, 0.65, 0.3, 1)
            self.btn_type_in.color = (1, 1, 1, 1)
            self.btn_type_out.background_color = (0.8, 0.8, 0.8, 1)
            self.btn_type_out.color = (0.15, 0.15, 0.15, 1)
        else:
            self.btn_type_in.background_color = (0.8, 0.8, 0.8, 1)
            self.btn_type_in.color = (0.15, 0.15, 0.15, 1)
            self.btn_type_out.background_color = (0.85, 0.25, 0.2, 1)
            self.btn_type_out.color = (1, 1, 1, 1)

    def go_back(self, instance):
        App.get_running_app().sm.current = "home"

    def delete_current_data(self, instance):
        if self.current_tx_id is not None:
            app = App.get_running_app()
            app.home_screen.delete_transaction(self.current_tx_id)
            self.go_back(None)

    def save_data(self, close=True):
        amount_str = self.amount_input.text
        note_str = self.note_input.text

        if amount_str:
            val = float(amount_str)
            app = App.get_running_app()

            tx_data = {
                'id': self.current_tx_id,
                'tx_type': self.tx_type,
                'date_str': self.today_date,
                'time_str': self.today_time,
                'amount': val,
                'note': note_str
            }

            transaction_id = app.home_screen.save_or_update_transaction(tx_data)
            for attachment in self.pending_attachments:
                if attachment.get("path") in self.persisted_attachment_paths:
                    continue
                app.home_screen.db.add_attachment(
                    transaction_id, attachment["path"], attachment.get("name", "Lampiran"),
                    attachment.get("mime"),
                )
            self.persisted_attachment_paths = {a["path"] for a in self.pending_attachments}
            self.pending_attachments = []
            self._update_attachment_label()

            self.amount_input.text = ""
            self.note_input.text = ""

            if close or self.current_tx_id is not None:
                self.go_back(None)
            else:
                # Tetap di layar input: perbarui jam untuk transaksi berikutnya
                self.today_date = datetime.now().strftime("%d-%b-%Y")
                self.today_time = datetime.now().strftime("%I:%M %p")
                self.date_input.text = f" <  {self.today_date}  > "
                self.time_input.text = self.today_time


# --- 3. RUN APPLICATION ---
class CashflowApp(App):
    def build(self):
        update_ui_scale()
        self.sm = ScreenManager(transition=NoTransition())
        self.home_screen = HomeScreen(name="home")
        self.tx_screen = TransactionScreen(name="transaction")

        self.sm.add_widget(self.home_screen)
        self.sm.add_widget(self.tx_screen)

        # UI ikut menyesuaikan saat jendela diubah ukurannya (responsive)
        Window.bind(on_resize=self._on_resize)
        return self.sm

    def _on_resize(self, window, width, height):
        # Debounce: tunggu sebentar setelah resize selesai, baru bangun kembali UI
        if not hasattr(self, '_resize_trigger'):
            self._resize_trigger = Clock.create_trigger(self._apply_resize, 0.12)
        self._resize_trigger()

    @staticmethod
    def _popup_is_open():
        """Cek apakah ada popup yang sedang terbuka di jendela."""
        for w in Window.children:
            if isinstance(w, Popup):
                return True
            if any(isinstance(x, Popup) for x in w.walk()):
                return True
        return False

    def _apply_resize(self, *args):
        # Jangan bongkar UI di belakang popup yang sedang terbuka
        if self._popup_is_open():
            return
        update_ui_scale()
        self.home_screen.rebuild()
        self.tx_screen.rebuild()


if __name__ == '__main__':
    CashflowApp().run()
