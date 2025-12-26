// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
//      CONFIGURACIÓN Y PINES (USB OTG)
// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
const int clkPin = 3;
const int cwPin = 9;
const int enPin = 5;
const int ledVerdePin = 6;
const int ledRojoPin = 7;

// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
//      PARÁMETROS FÍSICOS (ACTUALIZADOS)
// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
// CÁLCULO BASADO EN TU DATO: 14159 pasos en 2ml (Jeringa 6ml)
// 14159 / 2 = 7079.5 pasos/mL
// Avance lineal de 1mL en jeringa de 12mm = 0.884 cm
// 7079.5 / 0.884 = ~8008 pasos por cm
// Calibración Experimental (Factor 1.182 sobre teórico)
const float PASOS_POR_CM = 9465.0;

const long MIN_DELAY = 100;
const long MAX_DELAY_TECNICO = 16000; 

long velocidadDelay = 1000;
long currentPositionInSteps = 0;

// -- ESTADOS --
enum ProgramState {
  STATE_HOMING, STATE_LOAD_SETUP, STATE_MODE_SELECT, STATE_CAUDAL_SUBMENU, 
  STATE_CAUDAL_PRESET, STATE_CAUDAL_MANUAL, STATE_TIME_SETUP, STATE_POST_EXPULSION
};
ProgramState currentState = STATE_HOMING;

// -- Variables de operación --
float volumenACargar = 1.0;
float incrementoVolumen = 0.1;

// Variables Caudal
float caudalManual = 250.0;
float incrementoCaudal = 10.0;
float caudalMinimoPermitido = 0.0; 
float caudalMaximoPermitido = 0.0; 

float presetsCaudal[] = {250.0, 350.0, 500.0, 750.0, 1000.0};
int presetIndex = 0; 
int bucleRepeticiones = 1; 
int buclesPosibles[] = {1, 3, 5, 10};
int bucleIndex = 0;

// Variables Tiempo
float tiempoFinal = 10.0;
float incrementoTiempo = 1.0;

// -- JOGGING --
int jogDirection = 0;
long jogSpeedDelay = 300;
long suctionSpeedDelay = 250;

// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
//      CALIBRACIÓN (MODO RAW - NEUTRALIZADO)
// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
const float pendiente_m = 1.0; 
const float ordenada_c = 0.0;  
struct SyringeProfile { String nombre; float volumenTotalML; float diametroInternoMM; };
SyringeProfile jeringas[] = {
  {"Jeringa de 6 ml", 6.0, 12.0}, {"Jeringa de 10 ml", 10.0, 14.5},
  {"Jeringa de 5 ml", 5.0, 12.0}, {"Jeringa de 20 ml", 20.0, 20.0}
};
int jeringaActualIndex = 0;
float pasosPorML;

// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
//      PROTOTIPOS
// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
void calcularPasosPorML();
float obtenerVolumenCorregido(float volumenDeseado); 
void handleHomingCommands(char cmd);
void handleContinuousJogging();
void handleLoadSetupCommands(char cmd);
void handleModeSelectCommands(char cmd);
void handleCaudalSubmenuCommands(char cmd);
void handleCaudalPresetCommands(char cmd);
void handleCaudalManualCommands(char cmd);
void handleTimeSetupCommands(char cmd);
void handlePostExpulsionCommands(char cmd);
void ejecutarExpulsion(float volumen, float caudal, int repeticiones);
bool moveAndTrackMotor(long steps, long customDelay);
void sendData(String type, float value);
void sendStatus();
void sendConfigSummary(); 

// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
//      SETUP & LOOP
// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
void setup() {
  pinMode(clkPin, OUTPUT); pinMode(cwPin, OUTPUT); pinMode(enPin, OUTPUT);
  pinMode(ledVerdePin, OUTPUT); pinMode(ledRojoPin, OUTPUT);
  digitalWrite(enPin, LOW);
  Serial.begin(9600);
  Serial.println("BOMBA DE JERINGA PRO (NUEVA CALIBRACION)");
  calcularPasosPorML();
}

void loop() {
  if (Serial.available() > 0) {
    char command = tolower(Serial.read());
    while (Serial.available() > 0) Serial.read();

    if (command == 'r') {
      jogDirection = 0; currentState = STATE_HOMING; Serial.println("ACK:RESET");
    } else if (command == 'q') {
      sendStatus();
    } else {
      switch (currentState) {
        case STATE_HOMING:          handleHomingCommands(command); break;
        case STATE_LOAD_SETUP:      handleLoadSetupCommands(command); break;
        case STATE_MODE_SELECT:     handleModeSelectCommands(command); break;
        case STATE_CAUDAL_SUBMENU:  handleCaudalSubmenuCommands(command); break;
        case STATE_CAUDAL_PRESET:   handleCaudalPresetCommands(command); break;
        case STATE_CAUDAL_MANUAL:   handleCaudalManualCommands(command); break;
        case STATE_TIME_SETUP:      handleTimeSetupCommands(command); break;
        case STATE_POST_EXPULSION:  handlePostExpulsionCommands(command); break;
      }
    }
  }
  if (currentState == STATE_HOMING) handleContinuousJogging();
}

// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
//      FUNCIÓN DE CALIBRACIÓN (NEUTRALIZADA)
// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
float obtenerVolumenCorregido(float volumenDeseado) {
    // Retornamos el valor directo para probar la nueva constante física
    return volumenDeseado; 
}

// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
//      MANEJO DE COMANDOS (ESTADOS)
// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=

void handleHomingCommands(char cmd) {
  if (cmd == '+') jogDirection = 1;
  else if (cmd == '-') jogDirection = -1;
  else if (cmd == 'p') jogDirection = 0;
  else if (cmd == 's') {
    jogDirection = 0; currentPositionInSteps = 0;
    currentState = STATE_LOAD_SETUP;
    Serial.println("ACK:ZERO_SET");
    sendData("VOL", volumenACargar);
  }
}

void handleLoadSetupCommands(char cmd) {
  float maxVol = jeringas[jeringaActualIndex].volumenTotalML;
  if (cmd == '+') { volumenACargar = min(volumenACargar + incrementoVolumen, maxVol); sendData("VOL", volumenACargar); }
  else if (cmd == '-') { volumenACargar = max(volumenACargar - incrementoVolumen, 0.0f); sendData("VOL", volumenACargar); }
  else if (cmd == 's') {
    float volCorregido = obtenerVolumenCorregido(volumenACargar);
    long targetSteps = long(volCorregido * pasosPorML);
    long stepsToMove = targetSteps - currentPositionInSteps;
    moveAndTrackMotor(stepsToMove, suctionSpeedDelay);
    currentState = STATE_MODE_SELECT;
    Serial.println("ACK:LOAD_COMPLETE");
  }
}

void handleModeSelectCommands(char cmd) {
  if (cmd == '1') { currentState = STATE_CAUDAL_SUBMENU; Serial.println("ACK:CAUDAL_SUBMENU"); }
  else if (cmd == '2') { currentState = STATE_TIME_SETUP; sendData("TIME", tiempoFinal); }
}

void handleCaudalSubmenuCommands(char cmd) {
  if (cmd == '1') { 
    currentState = STATE_CAUDAL_PRESET;
    if (presetsCaudal[presetIndex] < caudalMinimoPermitido) presetsCaudal[presetIndex] = caudalMinimoPermitido; 
    Serial.print("PRESET:"); Serial.print(presetsCaudal[presetIndex]); Serial.print(":LOOP:"); Serial.println(bucleRepeticiones);
  } else if (cmd == '2') { 
    currentState = STATE_CAUDAL_MANUAL;
    if (caudalManual < caudalMinimoPermitido) caudalManual = caudalMinimoPermitido;
    Serial.print("CUSTOM:"); Serial.print(caudalManual); Serial.print(":INC:"); Serial.println(incrementoCaudal);
  }
}

void handleCaudalPresetCommands(char cmd) {
  if (cmd == '+') {
    presetIndex = (presetIndex + 1) % 5; 
    float valorAUsar = (presetsCaudal[presetIndex] < caudalMinimoPermitido) ? caudalMinimoPermitido : presetsCaudal[presetIndex];
    Serial.print("PRESET:"); Serial.println(valorAUsar);
  } else if (cmd == '-') {
    presetIndex = (presetIndex - 1 + 5) % 5;
    float valorAUsar = (presetsCaudal[presetIndex] < caudalMinimoPermitido) ? caudalMinimoPermitido : presetsCaudal[presetIndex];
    Serial.print("PRESET:"); Serial.println(valorAUsar);
  } else if (cmd == 'b') {
    bucleIndex = (bucleIndex + 1) % 4;
    bucleRepeticiones = buclesPosibles[bucleIndex];
    Serial.print("LOOP:"); Serial.println(bucleRepeticiones);
  } else if (cmd == 's') { 
    float valorFinal = (presetsCaudal[presetIndex] < caudalMinimoPermitido) ? caudalMinimoPermitido : presetsCaudal[presetIndex];
    sendConfigSummary(); 
    currentState = STATE_POST_EXPULSION; 
    ejecutarExpulsion(volumenACargar, valorFinal, bucleRepeticiones);
    Serial.println("ACK:EXPULSION_COMPLETE");
  }
}

void handleCaudalManualCommands(char cmd) {
  if (cmd == '+') {
    caudalManual += incrementoCaudal;
    if (caudalManual > caudalMaximoPermitido) caudalManual = caudalMaximoPermitido; 
    Serial.print("CUSTOM:"); Serial.println(caudalManual);
  } else if (cmd == '-') {
    caudalManual -= incrementoCaudal;
    if (caudalManual < caudalMinimoPermitido) caudalManual = caudalMinimoPermitido; 
    Serial.print("CUSTOM:"); Serial.println(caudalManual);
  } else if (cmd == 'm') {
    if (incrementoCaudal == 10.0) incrementoCaudal = 100.0;
    else if (incrementoCaudal == 100.0) incrementoCaudal = 1000.0;
    else incrementoCaudal = 10.0;
    Serial.print("INC:"); Serial.println(incrementoCaudal);
  } else if (cmd == 's') { 
    sendConfigSummary();
    currentState = STATE_POST_EXPULSION;
    ejecutarExpulsion(volumenACargar, caudalManual, 1);
    Serial.println("ACK:EXPULSION_COMPLETE");
  }
}

void handleTimeSetupCommands(char cmd) {
  if (cmd == '+') { tiempoFinal += incrementoTiempo; sendData("TIME", tiempoFinal); }
  else if (cmd == '-') { tiempoFinal -= incrementoTiempo; if(tiempoFinal < 0) tiempoFinal=0; sendData("TIME", tiempoFinal); }
  else if (cmd == 's') { 
    sendConfigSummary();
    
    float volumenCorregido = obtenerVolumenCorregido(volumenACargar);
    long pasosTotales = long(volumenCorregido * pasosPorML);
    
    velocidadDelay = (long)((tiempoFinal * 500000.0 / (float)abs(pasosTotales))); 
    if (velocidadDelay > MAX_DELAY_TECNICO) velocidadDelay = MAX_DELAY_TECNICO;
    if (velocidadDelay < MIN_DELAY) velocidadDelay = MIN_DELAY;
    
    Serial.println("Expulsando...");
    currentState = STATE_POST_EXPULSION;
    Serial.println("STATUS:EXPULSION"); 
    moveAndTrackMotor(-pasosTotales, velocidadDelay);
    Serial.println("ACK:EXPULSION_COMPLETE");
  }
}

void handlePostExpulsionCommands(char cmd) {
    if (cmd == 'z') {
        moveAndTrackMotor(-currentPositionInSteps, suctionSpeedDelay); 
        currentState = STATE_LOAD_SETUP;
        Serial.println("ACK:RETURNED_TO_ZERO");
        sendData("VOL", volumenACargar);
    } else if (cmd == 'k') {
        currentState = STATE_LOAD_SETUP;
        Serial.println("ACK:STAYING_POSITION");
        sendData("VOL", volumenACargar);
    }
}

// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
//      LÓGICA DE EXPULSIÓN
// =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=

void ejecutarExpulsion(float volumenTotal, float caudal, int repeticiones) {
  if (caudal < caudalMinimoPermitido) caudal = caudalMinimoPermitido;

  float volumenUnMinutoCorregido = obtenerVolumenCorregido(caudal / 1000.0); 
  float pasos_por_minuto = volumenUnMinutoCorregido * pasosPorML;
  
  long delayExpulsion = (long)(30000000.0 / pasos_por_minuto);
  if (delayExpulsion < MIN_DELAY) delayExpulsion = MIN_DELAY;

  float volumenTotalCorregido = obtenerVolumenCorregido(volumenTotal);
  long pasosFull = long(volumenTotalCorregido * pasosPorML);
  
  long stepsToExpel = -pasosFull; 
  long stepsToReload = pasosFull; 

  Serial.println("Iniciando Secuencia...");

  for (int i = 1; i <= repeticiones; i++) {
    Serial.print(">>> CICLO "); Serial.print(i); Serial.print("/"); Serial.println(repeticiones);
    
    Serial.println("STATUS:EXPULSION"); 
    if (moveAndTrackMotor(stepsToExpel, delayExpulsion)) {
      Serial.println("ABORTADO por usuario");
      return;
    }

    if (i == repeticiones) {
      Serial.println("Secuencia Finalizada (Jeringa Vacia).");
      break;
    }

    Serial.println("Pausa 1s...");
    delay(1000); 

    Serial.println("STATUS:RECARGA"); 
    if (moveAndTrackMotor(stepsToReload, suctionSpeedDelay)) {
      Serial.println("ABORTADO por usuario");
      return;
    }

    Serial.println("Pausa 1s...");
    delay(1000);
  }
}

bool moveAndTrackMotor(long steps, long customDelay) {
  if (steps == 0) return false;
  int direction = (steps > 0) ? HIGH : LOW;
  digitalWrite(cwPin, direction);
  digitalWrite(ledVerdePin, direction == LOW);
  digitalWrite(ledRojoPin, direction == HIGH);
  long stepCount = abs(steps);
  bool stopped = false;
  unsigned long lastReportTime = 0; 
  for (long i = 0; i < stepCount; i++) {
    if (Serial.available() > 0) {
      char cmd = tolower(Serial.read());
      if (cmd == 'p') { stopped = true; break; }
    }
    digitalWrite(clkPin, HIGH); delayMicroseconds(customDelay);
    digitalWrite(clkPin, LOW); delayMicroseconds(customDelay);
    if (direction == HIGH) currentPositionInSteps++; else currentPositionInSteps--;
    if (millis() - lastReportTime > 200) {
      lastReportTime = millis();
      int porcentaje = (int)((float)i / (float)stepCount * 100.0);
      if (currentState == STATE_POST_EXPULSION || currentState == STATE_LOAD_SETUP) {
         Serial.print("PROG:"); Serial.println(porcentaje);
      }
    }
  }
  if (!stopped && (currentState == STATE_POST_EXPULSION || currentState == STATE_LOAD_SETUP)) {
      Serial.println("PROG:100");
  }
  digitalWrite(ledVerdePin, LOW); digitalWrite(ledRojoPin, LOW);
  return stopped;
}

void handleContinuousJogging() {
  if (jogDirection == 0) { digitalWrite(ledVerdePin, LOW); digitalWrite(ledRojoPin, LOW); return; }
  int direction = (jogDirection == 1) ? HIGH : LOW;
  // ** IMPORTANTE: Enviar dirección al driver **
  digitalWrite(cwPin, direction); 
  digitalWrite(ledVerdePin, direction == LOW);
  digitalWrite(ledRojoPin, direction == HIGH);
  digitalWrite(clkPin, HIGH); delayMicroseconds(jogSpeedDelay);
  digitalWrite(clkPin, LOW); delayMicroseconds(jogSpeedDelay);
  if (direction == HIGH) currentPositionInSteps++; else currentPositionInSteps--;
}

void sendData(String type, float value) { Serial.print(type); Serial.print(":"); Serial.println(value, 2); }
void sendStatus() { Serial.print("STATUS:"); Serial.print(currentState); Serial.print(":VOL:"); Serial.println(volumenACargar, 2); }
void sendConfigSummary() {
  Serial.print("INFO:"); Serial.print(volumenACargar, 2); Serial.print(":");
  if (currentState == STATE_TIME_SETUP) { Serial.print(tiempoFinal, 2); Serial.print(":TIME"); } 
  else {
     if (currentState == STATE_CAUDAL_MANUAL) Serial.print(caudalManual, 2);
     else Serial.print(presetsCaudal[presetIndex], 2);
     Serial.print(":FLOW");
  }
  Serial.print(":"); Serial.println(jeringas[jeringaActualIndex].nombre); 
}

void calcularPasosPorML() {
  SyringeProfile jeringaActual = jeringas[jeringaActualIndex];
  float radio = jeringaActual.diametroInternoMM / 2.0;
  float area_mm2 = PI * (radio * radio);
  float cmPorML = (1000.0 / area_mm2) / 10.0;
  pasosPorML = PASOS_POR_CM * cmPorML;

  float pasosPorMinutoMinimos = 30000000.0 / (float)MAX_DELAY_TECNICO;
  caudalMinimoPermitido = (pasosPorMinutoMinimos / pasosPorML) * 1000.0;
  
  float pasosPorMinutoMaximos = 30000000.0 / (float)MIN_DELAY;
  caudalMaximoPermitido = (pasosPorMinutoMaximos / pasosPorML) * 1000.0;
  
  Serial.print("DEBUG:MinFlow:"); Serial.println(caudalMinimoPermitido);
}