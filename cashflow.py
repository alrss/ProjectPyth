from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle
from kivy.properties import StringProperty, NumericProperty
from datetime import datetime, timedelta

from cashflow_db import CashflowDB

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


# --- Widget Custom Baris Transaksi ---
class TransactionRow(ColorBoxLayout):
   def __init__(self, tx_data, palette=None, **kwargs):
       palette = palette or THEMES["light"]
       has_edit_note = bool(tx_data.get('edited_at'))
       row_height = "66dp" if has_edit_note else "52dp"

       super().__init__(bg_color=palette["row_bg"], size_hint_y=None, height=row_height, padding=["8dp", "4dp"], **kwargs)
       self.tx_data = tx_data

       # Tanggal & Jam + Catatan (+ info edit kalau pernah diedit)
       col_date = BoxLayout(orientation='vertical', size_hint_x=0.36)

       date_time_text = tx_data['date_str']
       if tx_data.get('time_str'):
           date_time_text += f"  {tx_data['time_str']}"
       lbl_date = Label(text=date_time_text, color=palette["text_primary"], font_size="11sp", halign="left", valign="middle")
       lbl_note = Label(text=tx_data['note'] if tx_data['note'] else "-", color=palette["text_secondary"], font_size="10sp", halign="left", valign="middle")
       lbl_date.bind(size=lbl_date.setter('text_size'))
       lbl_note.bind(size=lbl_note.setter('text_size'))
       col_date.add_widget(lbl_date)
       col_date.add_widget(lbl_note)

       if has_edit_note:
           lbl_edited = Label(
               text=f"Diedit pada {tx_data['edited_at']}",
               color=(0.85, 0.55, 0.1, 1), font_size="9sp", italic=True,
               halign="left", valign="middle"
           )
           lbl_edited.bind(size=lbl_edited.setter('text_size'))
           col_date.add_widget(lbl_edited)

       formatted_amount = f"{int(tx_data['amount']):,}"

       # Kolom Menerima (Center)
       lbl_in = Label(
           text=formatted_amount if tx_data['tx_type'] == "Menerima" else "-",
           color=(0.1, 0.6, 0.2, 1), bold=True, size_hint_x=0.32,
           halign="center", valign="middle"
       )
       lbl_in.bind(size=lbl_in.setter('text_size'))

       # Kolom Membayar (Center)
       lbl_out = Label(
           text=formatted_amount if tx_data['tx_type'] == "Membayar" else "-",
           color=(0.85, 0.25, 0.2, 1), bold=True, size_hint_x=0.32,
           halign="center", valign="middle"
       )
       lbl_out.bind(size=lbl_out.setter('text_size'))

       self.add_widget(col_date)
       self.add_widget(lbl_in)
       self.add_widget(lbl_out)

   def on_touch_down(self, touch):
       if self.collide_point(*touch.pos):
           app = App.get_running_app()
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
       self.themed_bg = {}    # widget -> nama key warna di THEMES
       self.themed_text = {}  # label -> nama key warna di THEMES
       self.tab_buttons = {}  # nama_tab -> tombol

       palette = THEMES[self.theme]

       # Base Container Gelap
       outer_layout = ColorFloatLayout(bg_color=palette["app_bg"])
       self.themed_bg[outer_layout] = "app_bg"

       # Frame Utama Berukuran Ponsel (360x720 pt)
       phone_frame = ColorBoxLayout(
           bg_color=palette["phone_bg"],
           orientation='vertical',
           size_hint=(None, None),
           size=("360dp", "720dp"),
           pos_hint={'center_x': 0.5, 'center_y': 0.5}
       )
       self.themed_bg[phone_frame] = "phone_bg"

       # Header Top Bar dengan Tombol Pemilih Buku Kas
       header = ColorBoxLayout(bg_color=palette["header_bg"], size_hint_y=None, height="50dp", padding=["8dp", "0dp"])
       self.themed_bg[header] = "header_bg"

       # Icon garis tiga horizontal (", font_size="18sp", size_hint_x=0.12,
           background_color=(0, 0, 0, 0), color=(1, 1, 1, 1)
       )
       self.btn_theme.bind(on_release=self.toggle_theme)
       header.add_widget(self.btn_theme)

       # Tombol Judul Kas (Bisa diklik untuk ganti / buat / edit nama kas)
       self.btn_book_selector = Button(
           text=f"{self.current_book_name} \u25bc", font_size="14sp", bold=True,
           size_hint_x=0.6, background_color=(0, 0, 0, 0), halign="left", valign="middle"
       )
       self.btn_book_selector.bind(size=self.btn_book_selector.setter('text_size'))
       self.btn_book_selector.bind(on_release=self.open_book_manager_popup)
       header.add_widget(self.btn_book_selector)

       header.add_widget(Label(text="\U0001F4C4  \U0001F50D  \u22ee", font_size="16sp", size_hint_x=0.28, halign="right", valign="middle"))
       phone_frame.add_widget(header)

       # Tab Filter (kini benar-benar berfungsi)
       tab_layout = ColorBoxLayout(bg_color=palette["tab_bg"], size_hint_y=None, height="40dp", padding=["4dp", "4dp"], spacing="4dp")
       self.themed_bg[tab_layout] = "tab_bg"
       for tab in self.FILTER_LABELS:
           is_active = (tab == self.current_filter)
           btn = Button(
               text=tab,
               background_color=palette["tab_active"] if is_active else palette["tab_inactive"],
               bold=is_active, font_size="10sp"
           )
           btn.bind(on_release=lambda x, t=tab: self.set_filter(t))
           tab_layout.add_widget(btn)
           self.tab_buttons[tab] = btn
       phone_frame.add_widget(tab_layout)

       # Sub Header -> jadi indikator filter yang sedang aktif
       sub_header = ColorBoxLayout(bg_color=palette["subheader_bg"], size_hint_y=None, height="24dp")
       self.themed_bg[sub_header] = "subheader_bg"
       self.lbl_subheader = Label(text="Semua Transaksi", font_size="11sp", halign="center", valign="middle")
       sub_header.add_widget(self.lbl_subheader)
       phone_frame.add_widget(sub_header)

       # Table Header
       table_header = ColorBoxLayout(bg_color=palette["table_header_bg"], size_hint_y=None, height="36dp", padding=["8dp", "0dp"])
       self.themed_bg[table_header] = "table_header_bg"

       th_date = Label(text="Tanggal", color=palette["text_primary"], bold=True, font_size="11sp", size_hint_x=0.36, halign="left", valign="middle")
       th_date.bind(size=th_date.setter('text_size'))
       self.themed_text[th_date] = "text_primary"

       th_in = Label(text="Kamu Menerima", color=(0.1, 0.6, 0.2, 1), bold=True, font_size="11sp", size_hint_x=0.32, halign="center", valign="middle")
       th_in.bind(size=th_in.setter('text_size'))

       th_out = Label(text="Kamu Membayar", color=(0.85, 0.25, 0.2, 1), bold=True, font_size="11sp", size_hint_x=0.32, halign="center", valign="middle")
       th_out.bind(size=th_out.setter('text_size'))

       table_header.add_widget(th_date)
       table_header.add_widget(th_in)
       table_header.add_widget(th_out)
       phone_frame.add_widget(table_header)

       # Scroll Area Daftar Transaksi
       self.scroll_view = ScrollView(size_hint=(1, 1))
       self.tx_container = GridLayout(cols=1, spacing="1dp", size_hint_y=None)
       self.tx_container.bind(minimum_height=self.tx_container.setter('height'))
       self.scroll_view.add_widget(self.tx_container)
       phone_frame.add_widget(self.scroll_view)

       # Tombol Aksi Input
       btn_layout = ColorBoxLayout(bg_color=palette["phone_bg"], size_hint_y=None, height="52dp", padding="6dp", spacing="6dp")
       self.themed_bg[btn_layout] = "phone_bg"

       btn_in = Button(
           text="Kamu Menerima", background_normal='', background_color=(0.2, 0.65, 0.3, 1),
           bold=True, font_size="12sp", halign="center", valign="middle"
       )
       btn_in.bind(on_release=lambda x: self.open_tx_screen("Menerima"))

       btn_out = Button(
           text="Kamu Membayar", background_normal='', background_color=(0.85, 0.25, 0.2, 1),
           bold=True, font_size="12sp", halign="center", valign="middle"
       )
       btn_out.bind(on_release=lambda x: self.open_tx_screen("Membayar"))

       btn_layout.add_widget(btn_in)
       btn_layout.add_widget(btn_out)
       phone_frame.add_widget(btn_layout)

       # Footer Saldo
       footer = ColorBoxLayout(bg_color=palette["footer_bg"], size_hint_y=None, height="46dp")
       self.themed_bg[footer] = "footer_bg"

       box_in = BoxLayout(orientation='vertical')
       lbl_in_title = Label(text="Total Menerima", color=palette["text_muted"], font_size="10sp", halign="center")
       self.themed_text[lbl_in_title] = "text_muted"
       box_in.add_widget(lbl_in_title)
       self.lbl_total_in = Label(text="0", color=(0.1, 0.6, 0.2, 1), bold=True, font_size="11sp", halign="center")
       box_in.add_widget(self.lbl_total_in)

       box_out = BoxLayout(orientation='vertical')
       lbl_out_title = Label(text="Total Membayar", color=palette["text_muted"], font_size="10sp", halign="center")
       self.themed_text[lbl_out_title] = "text_muted"
       box_out.add_widget(lbl_out_title)
       self.lbl_total_out = Label(text="0", color=(0.85, 0.25, 0.2, 1), bold=True, font_size="11sp", halign="center")
       box_out.add_widget(self.lbl_total_out)

       box_balance = BoxLayout(orientation='vertical')
       lbl_balance_title = Label(text="Saldo", color=palette["text_muted"], font_size="10sp", halign="center")
       self.themed_text[lbl_balance_title] = "text_muted"
       box_balance.add_widget(lbl_balance_title)
       self.lbl_balance = Label(text="0", color=(0.1, 0.4, 0.8, 1), bold=True, font_size="11sp", halign="center")
       box_balance.add_widget(self.lbl_balance)

       footer.add_widget(box_in)
       footer.add_widget(box_out)
       footer.add_widget(box_balance)
       phone_frame.add_widget(footer)

       outer_layout.add_widget(phone_frame)
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
       content = BoxLayout(orientation='vertical', spacing="10dp", padding="10dp")

       lbl_info = Label(text="Pilih atau Buat Buku Kas:", size_hint_y=None, height="24dp", font_size="12sp")
       content.add_widget(lbl_info)

       # Scroll Daftar Buku Kas
       scroll = ScrollView(size_hint=(1, 1))
       book_list_layout = GridLayout(cols=1, spacing="6dp", size_hint_y=None)
       book_list_layout.bind(minimum_height=book_list_layout.setter('height'))

       popup = Popup(title="Kelola Buku Kas", content=content, size_hint=(None, None), size=("300dp", "400dp"))

       for book_name in self.books.keys():
           row = BoxLayout(size_hint_y=None, height="40dp", spacing="4dp")

           # Tombol Pilih Buku
           is_active = (book_name == self.current_book_name)
           btn_select = Button(
               text=f"{'", size_hint_x=None, width="40dp", font_size="12sp")
           btn_edit.bind(on_release=lambda x, name=book_name: self.open_rename_popup(name, popup))

           row.add_widget(btn_select)
           row.add_widget(btn_edit)
           book_list_layout.add_widget(row)

       scroll.add_widget(book_list_layout)
       content.add_widget(scroll)

       # Tombol Tambah Buku Kas Baru
       btn_add_new = Button(
           text="+ Buat Buku Kas Baru", size_hint_y=None, height="40dp",
           background_normal='', background_color=(0.2, 0.65, 0.3, 1), bold=True, font_size="12sp"
       )
       btn_add_new.bind(on_release=lambda x: self.open_create_book_popup(popup))
       content.add_widget(btn_add_new)

       popup.open()

   def switch_book(self, book_name, parent_popup):
       self.current_book_name = book_name
       self.btn_book_selector.text = f"{self.current_book_name} \u25bc"
       self.refresh_ui()
       parent_popup.dismiss()

   def open_create_book_popup(self, parent_popup):
       parent_popup.dismiss()

       content = BoxLayout(orientation='vertical', spacing="10dp", padding="10dp")
       txt_input = TextInput(hint_text="Nama Buku Kas Baru", multiline=False, size_hint_y=None, height="40dp", font_size="13sp")

       btn_box = BoxLayout(size_hint_y=None, height="40dp", spacing="6dp")
       btn_save = Button(text="Simpan", background_color=(0.1, 0.5, 0.88, 1))

       popup = Popup(title="Buat Buku Kas Baru", content=content, size_hint=(None, None), size=("280dp", "180dp"))

       def save_new_book(instance):
           new_name = txt_input.text.strip()
           if new_name and new_name not in self.books:
               if self.db.add_book(new_name):
                   self.books[new_name] = []
                   self.current_book_name = new_name
                   self.btn_book_selector.text = f"{self.current_book_name} \u25bc"
                   self.refresh_ui()
                   popup.dismiss()

       btn_save.bind(on_release=save_new_book)
       btn_box.add_widget(btn_save)

       content.add_widget(txt_input)
       content.add_widget(btn_box)
       popup.open()

   def open_rename_popup(self, old_name, parent_popup):
       parent_popup.dismiss()

       content = BoxLayout(orientation='vertical', spacing="10dp", padding="10dp")
       txt_input = TextInput(text=old_name, multiline=False, size_hint_y=None, height="40dp", font_size="13sp")

       btn_box = BoxLayout(size_hint_y=None, height="40dp", spacing="6dp")
       btn_save = Button(text="Ubah Nama", background_color=(0.1, 0.5, 0.88, 1))

       popup = Popup(title="Kustom Nama Buku Kas", content=content, size_hint=(None, None), size=("280dp", "180dp"))

       def rename_book(instance):
           new_name = txt_input.text.strip()
           if new_name and new_name != old_name:
               if self.db.rename_book(old_name, new_name):
                   self.books[new_name] = self.books.pop(old_name)
                   if self.current_book_name == old_name:
                       self.current_book_name = new_name
                       self.btn_book_selector.text = f"{self.current_book_name} \u25bc"
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

   def delete_transaction(self, tx_id):
       self.db.delete_transaction(tx_id)
       self.books[self.current_book_name] = [t for t in self.books[self.current_book_name] if t['id'] != tx_id]
       self.refresh_ui()

   def refresh_ui(self):
       self.tx_container.clear_widgets()
       self.total_in = 0
       self.total_out = 0
       palette = THEMES[self.theme]

       self.lbl_subheader.text = self._subheader_text()

       active_transactions = self.books.get(self.current_book_name, [])
       filtered_transactions = [tx for tx in active_transactions if self._matches_filter(tx)]

       for tx in reversed(filtered_transactions):
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

       outer_layout = ColorFloatLayout(bg_color=(0.12, 0.12, 0.12, 1))

       # Phone Frame (Fixed Size & Centered)
       phone_frame = ColorBoxLayout(
           bg_color=(0.95, 0.96, 0.97, 1),
           orientation='vertical',
           size_hint=(None, None),
           size=("360dp", "720dp"),
           pos_hint={'center_x': 0.5, 'center_y': 0.5}
       )

       # Header Transaksi
       self.header = ColorBoxLayout(bg_color=(0.1, 0.5, 0.88, 1), size_hint_y=None, height="50dp", padding=["12dp", "0dp"])
       btn_back = Button(text="", size_hint_x=0.15, font_size="18sp", halign="right"))
       phone_frame.add_widget(self.header)

       # Form Card
       form_card = ColorBoxLayout(bg_color=(1, 1, 1, 1), orientation='vertical', padding="14dp", spacing="12dp", size_hint_y=None, height="220dp")

       # Toggle Button Menerima / Membayar
       toggle_box = BoxLayout(size_hint_y=None, height="38dp", spacing="8dp")

       self.btn_type_in = Button(
           text="Kamu Menerima", background_normal='', font_size="12sp",
           halign="center", valign="middle"
       )
       self.btn_type_in.bind(on_release=lambda x: self.set_type("Menerima"))

       self.btn_type_out = Button(
           text="Kamu Membayar", background_normal='', font_size="12sp",
           halign="center", valign="middle"
       )
       self.btn_type_out.bind(on_release=lambda x: self.set_type("Membayar"))

       toggle_box.add_widget(self.btn_type_in)
       toggle_box.add_widget(self.btn_type_out)
       form_card.add_widget(toggle_box)

       # Date & Time (waktu ikut tersimpan bersama tanggal)
       dt_box = BoxLayout(size_hint_y=None, height="36dp", spacing="6dp")
       self.today_date = datetime.now().strftime("%d-%b-%Y")
       self.today_time = datetime.now().strftime("%I:%M %p")

       self.date_input = TextInput(text=f" <  {self.today_date}  > ", multiline=False, readonly=True, font_size="11sp")
       self.time_input = TextInput(text=self.today_time, multiline=False, readonly=True, font_size="11sp")
       dt_box.add_widget(self.date_input)
       dt_box.add_widget(self.time_input)
       form_card.add_widget(dt_box)

       # Input Nominal
       self.amount_input = TextInput(
           hint_text="Kamu Menerima", input_filter='int', multiline=False,
           size_hint_y=None, height="42dp", font_size="14sp"
       )
       form_card.add_widget(self.amount_input)

       # Input Catatan
       self.note_input = TextInput(
           hint_text="Catatan", multiline=False,
           size_hint_y=None, height="42dp", font_size="13sp"
       )
       form_card.add_widget(self.note_input)

       phone_frame.add_widget(form_card)
       phone_frame.add_widget(BoxLayout()) # Spacer

       # Tombol Bawah (Hapus, Simpan & Keluar, Simpan & Lanjutkan)
       bottom_box = ColorBoxLayout(bg_color=(0.95, 0.96, 0.97, 1), size_hint_y=None, height="52dp", padding="4dp", spacing="4dp")

       self.btn_delete = Button(
           text="Hapus", background_normal='',
           background_color=(0.85, 0.25, 0.2, 1), bold=True, font_size="11sp", size_hint_x=0.25
       )
       self.btn_delete.bind(on_release=self.delete_current_data)

       btn_save_exit = Button(
           text="Simpan &\nKeluar", background_normal='',
           background_color=(0.7, 0.85, 1, 1), color=(0,0,0,1), font_size="10sp", halign="center", size_hint_x=0.375
       )
       btn_save_exit.bind(on_release=lambda x: self.save_data(close=True))

       btn_save_cont = Button(
           text="Simpan &\nLanjutkan", background_normal='',
           background_color=(0.1, 0.5, 0.88, 1), bold=True, font_size="10sp", halign="center", size_hint_x=0.375
       )
       btn_save_cont.bind(on_release=lambda x: self.save_data(close=False))

       bottom_box.add_widget(self.btn_delete)
       bottom_box.add_widget(btn_save_exit)
       bottom_box.add_widget(btn_save_cont)
       phone_frame.add_widget(bottom_box)

       outer_layout.add_widget(phone_frame)
       self.add_widget(outer_layout)

   def set_mode_add(self, tx_type):
       self.current_tx_id = None
       self.amount_input.text = ""
       self.note_input.text = ""
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
           self.btn_type_out.background_color = (0.8, 0.8, 0.8, 1)
       else:
           self.btn_type_in.background_color = (0.8, 0.8, 0.8, 1)
           self.btn_type_out.background_color = (0.85, 0.25, 0.2, 1)

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

           app.home_screen.save_or_update_transaction(tx_data)

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
       self.sm = ScreenManager(transition=NoTransition())
       self.home_screen = HomeScreen(name="home")
       self.tx_screen = TransactionScreen(name="transaction")

       self.sm.add_widget(self.home_screen)
       self.sm.add_widget(self.tx_screen)

       return self.sm

if __name__ == '__main__':
   CashflowApp().run()
