[app]
title = Bomba de Jeringa (USB)
package.name = bombajeringausb
package.domain = org.tuproyecto
source.dir = .
source.include_exts = py,kv,png,jpg,xml
version = 0.3

# <<--- ESTA ES LA SECCIÓN MÁS IMPORTANTE --- >>
# Requerimos 'pyserial' para la comunicación y 'usb4a'
# que es la librería que le da a pyserial acceso al USB de Android.
requirements = python3,kivy,pyserial,android,pyjnius

orientation = portrait

[buildozer]
log_level = 2
warn_on_root = 1

# <<--- PERMISOS --- >>
# Ya no necesitamos Bluetooth. Los permisos de USB son
# solicitados por la librería 'usb4a' automáticamente.
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE
android.api = 31
android.minapi = 23
# 3. Declara las características de hardware (CRÍTICO para que usb4a funcione)
android.add_features = android.hardware.usb.host

# 4. Dile a Buildozer dónde están los archivos XML que creamos
# Esto copiará tu carpeta 'xml' a la carpeta de recursos de Android
android.add_resources = xml:res/xml

# 5. Configura el Intent Filter para que Android sepa que tu app maneja USB
android.manifest.intent_filters = xml/usb_device_attached.xml