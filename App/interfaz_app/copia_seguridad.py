import time
import threading
from kivy.app import App
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.modalview import ModalView
from kivy.uix.boxlayout import BoxLayout
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.factory import Factory
from kivy.utils import platform

# ==========================================
# DRIVER HÍBRIDO MEJORADO: CH340 + CDC
# ==========================================
platform_android = platform == 'android'
PythonActivity = None
Context = None
UsbManager = None
UsbConstants = None

if platform_android:
    try:
        from jnius import autoclass, cast
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Context = autoclass('android.content.Context')
        UsbManager = autoclass('android.hardware.usb.UsbManager')
        UsbConstants = autoclass('android.hardware.usb.UsbConstants')
        PendingIntent = autoclass('android.app.PendingIntent')
        Intent = autoclass('android.content.Intent')
    except Exception as e:
        print(f"Error JNIUS: {e}")
else:
    import serial
    import serial.tools.list_ports

arduino_driver = None

class AndroidUSBSerial:
    """ Driver nativo con soporte específico para CH340 y CDC """
    def __init__(self, device, manager):
        self.device = device
        self.manager = manager
        self.connection = manager.openDevice(device)
        self.iface = None
        self.ep_in = None
        self.ep_out = None
        self.is_open = False
        
        if not self.connection:
            raise Exception("No se pudo abrir la conexión USB")

        self.iface = device.getInterface(0)
        if not self.connection.claimInterface(self.iface, True):
            raise Exception("Error reclamando interfaz")

        # Buscar Endpoints
        for i in range(self.iface.getEndpointCount()):
            ep = self.iface.getEndpoint(i)
            if ep.getType() == UsbConstants.USB_ENDPOINT_XFER_BULK:
                if ep.getDirection() == UsbConstants.USB_DIR_IN:
                    self.ep_in = ep
                else:
                    self.ep_out = ep
        
        if not self.ep_in or not self.ep_out:
            raise Exception("Endpoints no encontrados")

        # DETECCIÓN DE DRIVER POR VID
        vid = device.getVendorId()
        if vid == 0x1A86 or vid == 6790:
            print("Detectado chip CH340. Iniciando secuencia especial...")
            self.init_ch340()
        else:
            print("Detectado dispositivo genérico. Iniciando CDC...")
            self.init_cdc()

        self.is_open = True

    def init_ch340(self):
        # Secuencia mágica de inicialización para CH340 a 9600 baudios
        # Si esto falla, el chip no transmite nada.
        ctrl = self.connection.controlTransfer
        # 0x40 = Vendor Write
        ctrl(0x40, 0xA1, 0, 0, None, 0, 1000)
        ctrl(0x40, 0x9A, 0x1312, 0xD982, None, 0, 1000)
        ctrl(0x40, 0x9A, 0x0F2C, 0x0008, None, 0, 1000) # Configura 9600 baudios
        ctrl(0x40, 0xA4, 0x00DA, 0, None, 0, 1000)

    def init_cdc(self):
        # Configuración estándar para Arduino Original (Atmega16u2)
        baud_data = bytes([0x80, 0x25, 0x00, 0x00, 0x00, 0x00, 0x08]) 
        self.connection.controlTransfer(0x21, 0x20, 0, 0, baud_data, len(baud_data), 1000)
        self.connection.controlTransfer(0x21, 0x22, 0x03, 0, None, 0, 1000)

    def write(self, data):
        if not self.is_open: return
        self.connection.bulkTransfer(self.ep_out, data, len(data), 500)

    def readline(self):
        if not self.is_open: return b''
        line_buffer = bytearray()
        start_time = time.time()
        temp_buff = bytearray(64)
        
        while True:
            # Timeout corto para no bloquear la UI
            cnt = self.connection.bulkTransfer(self.ep_in, temp_buff, len(temp_buff), 50)
            if cnt > 0:
                chunk = temp_buff[:cnt]
                if b'\n' in chunk:
                    parts = chunk.split(b'\n', 1)
                    line_buffer.extend(parts[0])
                    return line_buffer.decode('utf-8', errors='ignore')
                else:
                    line_buffer.extend(chunk)
            if time.time() - start_time > 0.2: # Timeout de lectura
                break
        return line_buffer.decode('utf-8', errors='ignore') if line_buffer else ""

    def close(self):
        self.is_open = False
        try:
            self.connection.releaseInterface(self.iface)
            self.connection.close()
        except: pass

class ReturnToZeroPopup(ModalView):
    pass

class ConnectionScreen(Screen):
    def on_pre_enter(self, *args):
        if platform_android:
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
        Clock.schedule_once(self.list_devices, 0)

    def list_devices(self, *args):
        self.ids.device_spinner.values = []
        device_list = []
        
        if platform_android:
            if UsbManager:
                try:
                    activity = PythonActivity.mActivity
                    manager = activity.getSystemService(Context.USB_SERVICE)
                    devices = manager.getDeviceList()
                    if devices:
                        for d in devices.values():
                            device_list.append(f"{d.getDeviceName()} ({d.getVendorId()}:{d.getProductId()})")
                    else:
                        self.ids.connect_status.text = "Sin USB detectado"
                except: pass
        else:
            # En MAC, preferimos los puertos 'cu.' sobre 'tty.' para evitar bloqueos
            ports = serial.tools.list_ports.comports()
            for port in ports:
                if "Bluetooth" not in port.device:
                    device_list.append(f"{port.device}")

        if device_list:
            self.ids.device_spinner.values = device_list
            self.ids.device_spinner.text = device_list[0]
            self.ids.connect_status.text = "Listo para conectar."
        else:
            self.ids.connect_status.text = "No se encontraron dispositivos."

    def connect_to_device(self, device_text):
        if not device_text or "Selecciona" in device_text: return
        path = device_text.split(' ')[0]
        if platform_android:
            self.android_connect(path)
        else:
            self.pc_connect(path)

    def android_connect(self, path):
        try:
            activity = PythonActivity.mActivity
            manager = activity.getSystemService(Context.USB_SERVICE)
            device = next((d for d in manager.getDeviceList().values() if d.getDeviceName() == path), None)
            
            if not device: return
            
            if not manager.hasPermission(device):
                self.ids.connect_status.text = "Pidiendo permiso..."
                intent = Intent("com.android.example.USB_PERMISSION")
                pIntent = PendingIntent.getBroadcast(activity, 0, intent, 33554432)
                manager.requestPermission(device, pIntent)
            else:
                self.start_driver(device, manager)
        except Exception as e:
            self.ids.connect_status.text = f"Error: {e}"

    def pc_connect(self, port):
        try:
            global arduino_driver
            # En Mac/PC, dsrdtr=True ayuda a reiniciar correctamente el Arduino
            arduino_driver = serial.Serial(port, 9600, timeout=0.1, dsrdtr=True)
            self.ids.connect_status.text = "Reiniciando Arduino..."
            # ESPERA CRÍTICA: El Arduino tarda 2s en arrancar tras abrir puerto
            Clock.schedule_once(self.finish_pc_connect, 2.5) 
        except Exception as e:
            self.ids.connect_status.text = f"Error PC: {e}"

    def finish_pc_connect(self, dt):
        self.ids.connect_status.text = "¡Conectado!"
        self.manager.get_screen('control').start_listening()
        self.manager.current = 'control'

    def start_driver(self, device, manager):
        try:
            global arduino_driver
            arduino_driver = AndroidUSBSerial(device, manager)
            self.ids.connect_status.text = "Conectado (Android)"
            self.manager.get_screen('control').start_listening()
            self.manager.current = 'control'
        except Exception as e:
            self.ids.connect_status.text = f"Fallo Driver: {e}"

class ControlScreen(BoxLayout, Screen):
    current_state = 'HOMING'
    current_volume = 1.0
    current_parameter = 100.0
    is_caudal_mode = True
    adjustment_event = None
    stop_thread = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.return_popup = Factory.ReturnToZeroPopup()

    def start_listening(self):
        self.stop_thread = False
        threading.Thread(target=self.read_loop, daemon=True).start()

    def read_loop(self):
        while not self.stop_thread:
            if not arduino_driver: break
            try:
                line = ""
                if platform_android:
                    line = arduino_driver.readline()
                else:
                    if arduino_driver.in_waiting:
                        line = arduino_driver.readline().decode('utf-8', errors='ignore').strip()
                
                if line:
                    print(f"RX: {line}")
                    Clock.schedule_once(lambda dt, l=line: self.process_message(l))
                else:
                    time.sleep(0.05) # Evitar consumo excesivo de CPU
            except: pass

    def process_message(self, line):
        try:
            parts = line.split(':')
            if len(parts) < 2: return
            msg_type = parts[0]
            if msg_type == "VOL":
                self.current_volume = float(parts[1])
            elif msg_type == "PARAM":
                self.current_parameter = float(parts[1])
                self.current_state = 'PARAMETER_SETUP'
            elif msg_type == "ACK":
                self.handle_ack(parts[1])
            self.update_ui()
        except: pass

    def handle_ack(self, msg):
        if msg == "ZERO_SET": self.current_state = 'LOAD_SETUP'
        elif msg == "LOAD_COMPLETE": self.current_state = 'MODE_SELECT'
        elif msg == "EXPULSION_COMPLETE": 
            self.current_state = 'POST_EXPULSION'
            self.return_popup.open()
        elif msg in ["RETURNED_TO_ZERO", "STAYING_POSITION"]: self.current_state = 'LOAD_SETUP'
        elif msg == "RESET": self.current_state = 'HOMING'
        self.update_ui()

    def send(self, cmd):
        if arduino_driver:
            try:
                data = cmd.encode() if isinstance(cmd, str) else cmd
                arduino_driver.write(data)
                if not platform_android:
                    arduino_driver.flush() # Importante en PC
            except Exception as e:
                print(f"Error TX: {e}")

    # --- Lógica de Botones ---
    def start_adjustment(self, amount, dt=0):
        cmd = '+' if amount > 0 else '-'
        self.send(cmd)
        # Actualización visual optimista
        if self.current_state == 'LOAD_SETUP':
            self.current_volume = max(0, self.current_volume + amount * 0.1)
        elif self.current_state == 'PARAMETER_SETUP':
            incr = 50.0 if self.is_caudal_mode else 1.0
            self.current_parameter = max(0, self.current_parameter + amount * incr)
        self.update_ui()

    def stop_adjustment(self, *args):
        if self.adjustment_event:
            Clock.unschedule(self.adjustment_event)
            self.adjustment_event = None
        if self.current_state == 'HOMING': self.send('p')

    def handle_plus_press(self):
        self.stop_adjustment()
        if self.current_state == 'HOMING': self.send('-')
        elif self.current_state == 'MODE_SELECT':
            self.is_caudal_mode = True
            self.send('1')
        else:
            self.start_adjustment(1)
            self.adjustment_event = Clock.schedule_interval(lambda dt: self.start_adjustment(1, dt), 0.15)

    def handle_minus_press(self):
        self.stop_adjustment()
        if self.current_state == 'HOMING': self.send('+')
        elif self.current_state == 'MODE_SELECT':
            self.is_caudal_mode = False
            self.send('2')
        else:
            self.start_adjustment(-1)
            self.adjustment_event = Clock.schedule_interval(lambda dt: self.start_adjustment(-1, dt), 0.15)

    def handle_select_press(self):
        self.stop_adjustment()
        self.send('s')
        if self.current_state == 'PARAMETER_SETUP': self.ids.control_panel.disabled = True

    def confirm_return_to_zero(self, decision):
        self.return_popup.dismiss()
        self.send(decision)

    def send_reset_command(self):
        self.stop_adjustment()
        self.send('r')

    def send_stop_command(self):
        self.stop_adjustment()
        self.send('p')

    def update_ui(self):
        self.ids.control_panel.disabled = False
        self.ids.plus_button.disabled = False
        self.ids.minus_button.disabled = False
        self.ids.select_button.disabled = False
        
        # Binding/Unbinding dinámico
        self.ids.plus_button.funbind('on_release', self.stop_adjustment)
        self.ids.minus_button.funbind('on_release', self.stop_adjustment)
        if self.current_state == 'HOMING':
            self.ids.plus_button.fbind('on_release', self.stop_adjustment)
            self.ids.minus_button.fbind('on_release', self.stop_adjustment)

        if self.current_state == 'HOMING':
            self.ids.title_label.text = 'PUESTA A CERO'
            self.ids.value_display.text = 'Ajustar Posición'
            self.ids.plus_button.text = '+'
            self.ids.minus_button.text = '-'
            self.ids.select_button.text = 'Fijar CERO'
        elif self.current_state == 'LOAD_SETUP':
            self.ids.title_label.text = 'VOLUMEN A CARGAR'
            self.ids.value_display.text = f"{self.current_volume:.1f} mL"
            self.ids.plus_button.text = '+'
            self.ids.minus_button.text = '-'
            self.ids.select_button.text = 'Cargar'
        elif self.current_state == 'MODE_SELECT':
            self.ids.title_label.text = 'MODO DE OPERACIÓN'
            self.ids.value_display.text = "Seleccione:"
            self.ids.plus_button.text = 'Caudal'
            self.ids.minus_button.text = 'Tiempo'
            self.ids.select_button.text = '...'
            self.ids.select_button.disabled = True
        elif self.current_state == 'PARAMETER_SETUP':
            lbl = "CAUDAL" if self.is_caudal_mode else "TIEMPO"
            unit = "uL/min" if self.is_caudal_mode else "s"
            self.ids.title_label.text = f'AJUSTAR {lbl}'
            self.ids.value_display.text = f"{int(self.current_parameter)} {unit}"
            self.ids.plus_button.text = '+'
            self.ids.minus_button.text = '-'
            self.ids.select_button.text = 'INICIAR'
        elif self.current_state == 'POST_EXPULSION':
            self.ids.title_label.text = 'FINALIZADO'
            self.ids.value_display.text = '...'

class BombaApp(App):
    def build(self):
        return Builder.load_file('interfaz.kv')
    def on_stop(self):
        if arduino_driver:
            try: arduino_driver.close()
            except: pass

if __name__ == '__main__':
    BombaApp().run()