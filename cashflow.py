from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
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
from datetime import datetime

# Helper Canvas Background
class ColorBoxLayout(BoxLayout):
    def __init__(self, bg_color=(1, 1, 1, 1), **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*bg_color)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)

    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

class ColorFloatLayout(FloatLayout):
    def __init__(self, bg_color=(0.12, 0.12, 0.12, 1), **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*bg_color)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)

    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

# --- Widget Custom Baris Transaksi ---
class TransactionRow(ColorBoxLayout):
    def __init__(self, tx_data, **kwargs):
        super().__init__(bg_color=(1, 1, 1, 1), size_hint_y=None, height="52dp", padding=["8dp", "4dp"], **kwargs)
        self.tx_data = tx_data
        
        # Tanggal & Catatan
        col_date = BoxLayout(orientation='vertical', size_hint_x=0.36)
        lbl_date = Label(text=tx_data['date_str'], color=(0.1, 0.1, 0.1, 1), font_size="11sp", halign="left", valign="middle")
        lbl_note = Label(text=tx_data['note'] if tx_data['note'] else "-", color=(0.5, 0.5, 0.5, 1), font_size="10sp", halign="left", valign="middle")
        lbl_date.bind(size=lbl_date.setter('text_size'))
        lbl_note.bind(size=lbl_note.setter('text_size'))
        col_date.add_widget(lbl_date)
        col_date.add_widget(lbl_note)

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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Struktur Data Multi Buku Kas: {'nama_kas': [list_transaksi]}
        self.books = {
            "Buku Kas Utama": []
        }
        self.current_book_name = "Buku Kas Utama"
        self.tx_counter = 0

        # Base Container Gelap
        outer_layout = ColorFloatLayout(bg_color=(0.12, 0.12, 0.12, 1))

        # Frame Utama Berukuran Ponsel (360x720 pt)
        phone_frame = ColorBoxLayout(
            bg_color=(0.95, 0.96, 0.97, 1),
            orientation='vertical',
            size_hint=(None, None),
            size=("360dp", "720dp"),
            pos_hint={'center_x': 0.5, 'center_y': 0.5}
        )

        # Header Top Bar dengan Tombol Pemilih Buku Kas
        header = ColorBoxLayout(bg_color=(0.1, 0.5, 0.88, 1), size_hint_y=None, height="50dp", padding=["8dp", "0dp"])
        header.add_widget(Label(text="☰", font_size="18sp", size_hint_x=0.12, halign="left", valign="middle"))
        
        # Tombol Judul Kas (Bisa diklik untuk ganti / buat / edit nama kas)
        self.btn_book_selector = Button(
            text=f"{self.current_book_name} ▼", font_size="14sp", bold=True, 
            size_hint_x=0.6, background_color=(0,0,0,0), halign="left", valign="middle"
        )
        self.btn_book_selector.bind(size=self.btn_book_selector.setter('text_size'))
        self.btn_book_selector.bind(on_release=self.open_book_manager_popup)
        header.add_widget(self.btn_book_selector)
        
        header.add_widget(Label(text="📄  🔍  ⋮", font_size="16sp", size_hint_x=0.28, halign="right", valign="middle"))
        phone_frame.add_widget(header)

        # Tab Filter
        tab_layout = ColorBoxLayout(bg_color=(0.1, 0.5, 0.88, 1), size_hint_y=None, height="40dp", padding=["4dp", "4dp"], spacing="4dp")
        tabs = ["Semua", "Harian", "Mingguan", "Bulanan", "Tahunan"]
        for tab in tabs:
            btn = Button(text=tab, background_color=(1, 1, 1, 0.2) if tab != "Semua" else (1, 1, 1, 0.4), font_size="10sp")
            tab_layout.add_widget(btn)
        phone_frame.add_widget(tab_layout)

        # Sub Header
        sub_header = ColorBoxLayout(bg_color=(0.15, 0.45, 0.75, 1), size_hint_y=None, height="24dp")
        sub_header.add_widget(Label(text="Semua", font_size="11sp", halign="center", valign="middle"))
        phone_frame.add_widget(sub_header)

        # Table Header
        table_header = ColorBoxLayout(bg_color=(0.9, 0.91, 0.93, 1), size_hint_y=None, height="36dp", padding=["8dp", "0dp"])
        
        th_date = Label(text="Tanggal", color=(0.2, 0.2, 0.2, 1), bold=True, font_size="11sp", size_hint_x=0.36, halign="left", valign="middle")
        th_date.bind(size=th_date.setter('text_size'))
        
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
        btn_layout = ColorBoxLayout(bg_color=(0.95, 0.96, 0.97, 1), size_hint_y=None, height="52dp", padding="6dp", spacing="6dp")
        
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
        footer = ColorBoxLayout(bg_color=(1, 1, 1, 1), size_hint_y=None, height="46dp")
        
        box_in = BoxLayout(orientation='vertical')
        box_in.add_widget(Label(text="Total Menerima", color=(0.4, 0.4, 0.4, 1), font_size="10sp", halign="center"))
        self.lbl_total_in = Label(text="0", color=(0.1, 0.6, 0.2, 1), bold=True, font_size="11sp", halign="center")
        box_in.add_widget(self.lbl_total_in)

        box_out = BoxLayout(orientation='vertical')
        box_out.add_widget(Label(text="Total Membayar", color=(0.4, 0.4, 0.4, 1), font_size="10sp", halign="center"))
        self.lbl_total_out = Label(text="0", color=(0.85, 0.25, 0.2, 1), bold=True, font_size="11sp", halign="center")
        box_out.add_widget(self.lbl_total_out)

        box_balance = BoxLayout(orientation='vertical')
        box_balance.add_widget(Label(text="Saldo", color=(0.4, 0.4, 0.4, 1), font_size="10sp", halign="center"))
        self.lbl_balance = Label(text="0", color=(0.1, 0.4, 0.8, 1), bold=True, font_size="11sp", halign="center")
        box_balance.add_widget(self.lbl_balance)

        footer.add_widget(box_in)
        footer.add_widget(box_out)
        footer.add_widget(box_balance)
        phone_frame.add_widget(footer)

        outer_layout.add_widget(phone_frame)
        self.add_widget(outer_layout)

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
                text=f"{'✓ ' if is_active else ''}{book_name}", 
                background_color=(0.1, 0.5, 0.88, 1) if is_active else (0.8, 0.8, 0.8, 1),
                font_size="12sp"
            )
            btn_select.bind(on_release=lambda x, name=book_name: self.switch_book(name, popup))
            
            # Tombol Edit Nama Kas
            btn_edit = Button(text="✏", size_hint_x=None, width="40dp", font_size="12sp")
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
        self.btn_book_selector.text = f"{self.current_book_name} ▼"
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
                self.books[new_name] = []
                self.current_book_name = new_name
                self.btn_book_selector.text = f"{self.current_book_name} ▼"
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
                self.books[new_name] = self.books.pop(old_name)
                if self.current_book_name == old_name:
                    self.current_book_name = new_name
                    self.btn_book_selector.text = f"{self.current_book_name} ▼"
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
            self.tx_counter += 1
            tx_data['id'] = self.tx_counter
            current_tx_list.append(tx_data)
        else:
            for idx, item in enumerate(current_tx_list):
                if item['id'] == tx_data['id']:
                    current_tx_list[idx] = tx_data
                    break
        self.refresh_ui()

    def delete_transaction(self, tx_id):
        self.books[self.current_book_name] = [t for t in self.books[self.current_book_name] if t['id'] != tx_id]
        self.refresh_ui()

    def refresh_ui(self):
        self.tx_container.clear_widgets()
        self.total_in = 0
        self.total_out = 0

        active_transactions = self.books.get(self.current_book_name, [])

        for tx in reversed(active_transactions):
            row = TransactionRow(tx_data=tx)
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
        btn_back = Button(text="←", size_hint_x=0.15, background_color=(0,0,0,0), font_size="18sp")
        btn_back.bind(on_release=self.go_back)
        
        self.lbl_title = Label(text="Kamu Menerima", font_size="16sp", bold=True, size_hint_x=0.7, halign="left", valign="middle")
        self.lbl_title.bind(size=self.lbl_title.setter('text_size'))
        
        self.header.add_widget(btn_back)
        self.header.add_widget(self.lbl_title)
        self.header.add_widget(Label(text="⋮", size_hint_x=0.15, font_size="18sp", halign="right"))
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

        # Date Time
        dt_box = BoxLayout(size_hint_y=None, height="36dp", spacing="6dp")
        self.today_date = datetime.now().strftime("%d-%b-%Y")
        today_time = datetime.now().strftime("%I:%M %p")
        
        dt_box.add_widget(TextInput(text=f" <  {self.today_date}  > ", multiline=False, readonly=True, font_size="11sp"))
        dt_box.add_widget(TextInput(text=today_time, multiline=False, readonly=True, font_size="11sp"))
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
        self.btn_delete.opacity = 0
        self.btn_delete.disabled = True
        self.set_type(tx_type)

    def set_mode_edit(self, tx_data):
        self.current_tx_id = tx_data['id']
        self.amount_input.text = str(int(tx_data['amount']))
        self.note_input.text = tx_data['note']
        self.today_date = tx_data['date_str']
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
                'amount': val,
                'note': note_str
            }

            app.home_screen.save_or_update_transaction(tx_data)

            self.amount_input.text = ""
            self.note_input.text = ""

            if close or self.current_tx_id is not None:
                self.go_back(None)


# --- 3. RUN APPLICATION ---
class CashflowApp(App):
    def build(self):
        self.sm = ScreenManager()
        self.home_screen = HomeScreen(name="home")
        self.tx_screen = TransactionScreen(name="transaction")

        self.sm.add_widget(self.home_screen)
        self.sm.add_widget(self.tx_screen)
        
        return self.sm

if __name__ == '__main__':
    CashflowApp().run()
