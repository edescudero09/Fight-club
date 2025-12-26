# main.py
import os

# --- CONFIGURACIÓN DE VENTANA TIPO CELULAR ---
# ¡IMPORTANTE! Esto debe ir ANTES de cualquier otro import de Kivy
from kivy.config import Config
Config.set('graphics', 'resizable', '0') 
Config.set('graphics', 'width', '400')
Config.set('graphics', 'height', '750')
# ---------------------------------------------

import serial
import time
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.factory import Factory

# --- CONFIGURACIÓN ARDUINO ---
try:
    # Ajusta tu puerto aquí (COM3 o /dev/cu.usbserial...)
    # Asegúrate de que coincida con la velocidad de tu Arduino (9600 según tu último código)
    arduino = serial.Serial('/dev/cu.usbserial-110', 9600, timeout=1)
    time.sleep(2) 
except serial.SerialException as e:
    print(f"ERROR: {e}")
    arduino = None
# -----------------------------

Builder.load_file('interfaz.kv')

class ReturnToZeroPopup(ModalView):
    pass

class ExpulsionProgressPopup(ModalView):
    pass

class ControlBombaWidget(BoxLayout):
    
    current_state = 'HOMING'
    current_val_1 = 0.0 # Volumen / Preset / Manual
    current_val_2 = 0.0 # Loop / Inc
    active_total_vol = 0.0 
    adjustment_event = None
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.return_popup = Factory.ReturnToZeroPopup()
        self.progress_popup = Factory.ExpulsionProgressPopup()
        Clock.schedule_once(self.inicializar_ui, 0.5)

    def inicializar_ui(self, dt):
        if not arduino:
            self.ids.title_label.text = "ERROR DE CONEXIÓN"
            self.ids.value_display.text = "Revise puerto USB"
            self.disabled = True
        else:
            Clock.schedule_interval(self.read_serial_data, 0.05)
            self.update_ui_for_state()
    
    def read_serial_data(self, dt):
        try:
            if arduino and arduino.in_waiting > 0:
                line = arduino.readline().decode('utf-8', errors='ignore').strip()
                if not line: return
                
                parts = line.split(':')
                header = parts[0]

                # --- 1. LÓGICA DE ESTADO VISUAL ---
                if header == "STATUS":
                    estado = parts[1]
                    if estado == "EXPULSION":
                        self.progress_popup.ids.lbl_current.color = (0.2, 1, 0.2, 1)
                        self.progress_popup.title = "PROCESO: EXPULSANDO..."
                    elif estado == "RECARGA":
                        self.progress_popup.ids.lbl_current.color = (1, 0.2, 0.2, 1)
                        self.progress_popup.title = "PROCESO: RECARGANDO..."

                # --- 2. INFORMACIÓN DE INICIO ---
                elif header == "INFO":
                    self.parse_info_packet(parts)

                # --- 3. PROGRESO ---
                elif header == "PROG":
                    self.update_progress_bar(parts[1])

                # --- 4. DATOS DE ESTADO ---
                elif header == "VOL":
                    self.current_val_1 = float(parts[1])
                    self.update_ui_for_state()
                
                elif header == "PRESET" or header == "CUSTOM" or header == "TIME":
                    self.current_val_1 = float(parts[1])
                    if header == "PRESET": self.current_state = 'CAUDAL_PRESET'
                    if header == "CUSTOM": self.current_state = 'CAUDAL_MANUAL'
                    if header == "TIME": self.current_state = 'TIME_SETUP'
                    self.update_ui_for_state()
                
                elif header == "LOOP" or header == "INC":
                    self.current_val_2 = float(parts[1])
                    self.update_ui_for_state()

                # --- 5. CONFIRMACIONES ---
                elif header == "ACK":
                    self.handle_ack(parts[1])

        except Exception as e:
            print(f"Error lectura: {e}")

    def parse_info_packet(self, parts):
        """ Procesa INFO:VOL:VALOR:MODO para abrir el popup """
        try:
            vol = float(parts[1])
            val_param = float(parts[2])
            mode = parts[3]
            self.active_total_vol = vol 
            
            self.progress_popup.ids.lbl_total.text = f"{vol:.2f} mL"
            
            time_est = "---"
            if mode == "TIME":
                time_est = f"{int(val_param)} seg"
            elif mode == "FLOW" and val_param > 0:
                flow_ml = val_param / 1000.0
                seconds = (vol / flow_ml) * 60
                time_est = f"~{int(seconds)} seg"

            self.progress_popup.ids.lbl_time.text = time_est
            self.progress_popup.ids.lbl_current.color = (0.2, 1, 0.2, 1) 
            self.progress_popup.open()
            
        except Exception as e:
            print(f"Error INFO: {e}")

    def update_progress_bar(self, percent_str):
        try:
            percent = int(percent_str)
            self.progress_popup.ids.progress_bar.value = percent
            self.progress_popup.ids.lbl_percent.text = f"{percent}%"
            
            if self.progress_popup.ids.lbl_current.color[0] < 0.5: 
                current_ml = self.active_total_vol * (percent / 100.0)
                self.progress_popup.ids.lbl_current.text = f"{current_ml:.2f} mL"
            else:
                self.progress_popup.ids.lbl_current.text = "RECARGANDO..."
        except: pass

    def handle_ack(self, msg):
        if msg == "ZERO_SET": self.current_state = 'LOAD_SETUP'
        elif msg == "LOAD_COMPLETE": self.current_state = 'MODE_SELECT'
        elif msg == "CAUDAL_SUBMENU": self.current_state = 'CAUDAL_SUBMENU'
        
        elif msg == "EXPULSION_COMPLETE": 
            self.current_state = 'POST_EXPULSION'
            self.progress_popup.dismiss()
            self.return_popup.open()
            
        elif msg in ["RETURNED_TO_ZERO", "STAYING_POSITION"]: self.current_state = 'LOAD_SETUP'
        elif msg == "RESET": 
            self.current_state = 'HOMING'
            self.progress_popup.dismiss()
            self.return_popup.dismiss()
        
        self.update_ui_for_state()

    # --- BOTONES ---
    def start_adjustment(self, amount, dt=0):
        cmd = b'+' if amount > 0 else b'-'
        if self.current_state in ['LOAD_SETUP', 'CAUDAL_PRESET', 'CAUDAL_MANUAL', 'TIME_SETUP']:
            self.send_command(cmd.decode())
            # Actualización Local Optimista
            if self.current_state == 'LOAD_SETUP': self.current_val_1 += (amount * 0.1)
            elif self.current_state == 'CAUDAL_MANUAL': self.current_val_1 += (amount * self.current_val_2)
            elif self.current_state == 'TIME_SETUP': self.current_val_1 += amount
            self.update_ui_for_state()

    def stop_adjustment(self, *args):
        if self.adjustment_event:
            Clock.unschedule(self.adjustment_event)
            self.adjustment_event = None
        if self.current_state == 'HOMING': self.send_command('p')

    def handle_plus_press(self):
        self.stop_adjustment()
        if self.current_state == 'HOMING': self.send_command('-')
        elif self.current_state == 'MODE_SELECT': self.send_command('1')
        elif self.current_state == 'CAUDAL_SUBMENU': self.send_command('1')
        else:
            self.start_adjustment(1)
            self.adjustment_event = Clock.schedule_interval(lambda dt: self.start_adjustment(1, dt), 0.15)

    def handle_minus_press(self):
        self.stop_adjustment()
        if self.current_state == 'HOMING': self.send_command('+')
        elif self.current_state == 'MODE_SELECT': self.send_command('2')
        elif self.current_state == 'CAUDAL_SUBMENU': self.send_command('2')
        else:
            self.start_adjustment(-1)
            self.adjustment_event = Clock.schedule_interval(lambda dt: self.start_adjustment(-1, dt), 0.15)
    
    def handle_select_press(self):
        self.stop_adjustment()
        self.send_command('s')

    def handle_extra_press(self):
        if self.current_state == 'CAUDAL_PRESET': self.send_command('b')
        elif self.current_state == 'CAUDAL_MANUAL': self.send_command('m')

    def confirm_return_to_zero(self, decision):
        self.return_popup.dismiss()
        self.send_command(decision)

    def send_reset_command(self):
        self.stop_adjustment()
        self.send_command('r')

    def send_stop_command(self):
        self.stop_adjustment()
        self.send_command('p')
        self.progress_popup.dismiss()
        self.ids.status_label.text = "PARADA DE EMERGENCIA"

    def send_command(self, cmd):
        if arduino and arduino.is_open:
            arduino.write(cmd.encode())

    # --- UI UPDATE ---
    def update_ui_for_state(self):
        self.ids.control_panel.disabled = False
        self.ids.extra_panel.opacity = 0
        self.ids.extra_panel.disabled = True
        self.ids.sub_display.text = ""
        self.ids.center_btn.disabled = False

        is_homing = (self.current_state == 'HOMING')
        self.ids.right_btn.funbind('on_release', self.stop_adjustment)
        self.ids.left_btn.funbind('on_release', self.stop_adjustment)
        if is_homing:
            self.ids.right_btn.fbind('on_release', self.stop_adjustment)
            self.ids.left_btn.fbind('on_release', self.stop_adjustment)

        if self.current_state == 'HOMING':
            self.ids.title_label.text = 'CALIBRACIÓN INICIAL'
            self.ids.value_display.text = 'Ajustar Posición'
            self.ids.left_btn.text = '-'
            self.ids.right_btn.text = '+'
            self.ids.center_btn.text = 'FIJAR CERO'

        elif self.current_state == 'LOAD_SETUP':
            self.ids.title_label.text = 'CARGAR VOLUMEN'
            self.ids.value_display.text = f"{max(0, self.current_val_1):.1f} mL"
            self.ids.left_btn.text = '-'
            self.ids.right_btn.text = '+'
            self.ids.center_btn.text = 'CARGAR'

        elif self.current_state == 'MODE_SELECT':
            self.ids.title_label.text = 'SELECCIONAR MODO'
            self.ids.value_display.text = "¿Cómo expulsar?"
            self.ids.right_btn.text = 'CAUDAL'
            self.ids.left_btn.text = 'TIEMPO'
            self.ids.center_btn.text = '...'
            self.ids.center_btn.disabled = True

        elif self.current_state == 'CAUDAL_SUBMENU':
            self.ids.title_label.text = 'CONFIGURAR CAUDAL'
            self.ids.value_display.text = "Tipo de Control"
            self.ids.right_btn.text = 'PRESETS'
            self.ids.left_btn.text = 'MANUAL'
            self.ids.center_btn.text = '...'
            self.ids.center_btn.disabled = True

        elif self.current_state == 'CAUDAL_PRESET':
            self.ids.title_label.text = 'MODO PRESETS'
            self.ids.value_display.text = f"{int(self.current_val_1)} uL/min"
            self.ids.sub_display.text = f"Repeticiones: {int(self.current_val_2)}"
            self.ids.left_btn.text = '<'
            self.ids.right_btn.text = '>'
            self.ids.center_btn.text = 'INICIAR'
            self.ids.extra_panel.opacity = 1
            self.ids.extra_panel.disabled = False
            self.ids.extra_btn.text = "Cambiar Repeticiones"

        elif self.current_state == 'CAUDAL_MANUAL':
            self.ids.title_label.text = 'MODO MANUAL'
            self.ids.value_display.text = f"{int(self.current_val_1)} uL/min"
            self.ids.sub_display.text = f"Paso: +/- {int(self.current_val_2)}"
            self.ids.left_btn.text = '-'
            self.ids.right_btn.text = '+'
            self.ids.center_btn.text = 'INICIAR'
            self.ids.extra_panel.opacity = 1
            self.ids.extra_panel.disabled = False
            self.ids.extra_btn.text = f"Cambiar Escala (+/- {int(self.current_val_2)})"

        elif self.current_state == 'TIME_SETUP':
            self.ids.title_label.text = 'MODO TIEMPO'
            self.ids.value_display.text = f"{int(self.current_val_1)} seg"
            self.ids.left_btn.text = '-'
            self.ids.right_btn.text = '+'
            self.ids.center_btn.text = 'INICIAR'

        elif self.current_state == 'POST_EXPULSION':
            self.ids.title_label.text = 'CICLO COMPLETADO'
            self.ids.value_display.text = 'Finalizado'
            self.ids.control_panel.disabled = True

class BombaApp(App):
    def build(self):
        return ControlBombaWidget()
    def on_stop(self):
        if arduino: arduino.close()

if __name__ == '__main__':
    BombaApp().run()