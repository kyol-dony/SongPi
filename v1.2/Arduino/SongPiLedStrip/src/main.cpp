#include <Arduino.h>
#include <FastLED.h>

// Keep these aligned with Files/config.json. WS2812B normally uses GRB order.
#define DATA_PIN 6
#define LED_COUNT 30
#define COLOR_ORDER GRB
#define CHIPSET WS2812B

// Absolute strip power ceiling. FastLED scales every output frame to stay
// within this budget, even if SongPi requests a higher brightness.
// The Uno supplies data only; never power the strip from its 5 V pin.
#define LED_SUPPLY_VOLTS 5
#define MAX_POWER_MILLIAMPS 400

// Track-change colors blend over this window instead of snapping.
#define FADE_MS 1000UL
#define FADE_FRAME_MS 16UL

CRGB leds[LED_COUNT];
uint8_t brightness = 46;
String activeState = "starting";

CRGB fadeStart = CRGB::Black;
CRGB fadeTarget = CRGB::Black;
CRGB displayed = CRGB::Black;
unsigned long fadeStartMillis = 0;
bool fadeActive = false;

void startFade(const CRGB &target) {
  fadeStart = displayed;
  fadeTarget = target;
  fadeStartMillis = millis();
  fadeActive = true;
}

void tickFade() {
  if (!fadeActive) {
    return;
  }
  static unsigned long lastFrameMillis = 0;
  const unsigned long now = millis();
  if (now - lastFrameMillis < FADE_FRAME_MS) {
    return;
  }
  lastFrameMillis = now;
  const unsigned long elapsed = now - fadeStartMillis;
  if (elapsed >= FADE_MS) {
    displayed = fadeTarget;
    fadeActive = false;
  } else {
    const fract8 amount = static_cast<fract8>((elapsed * 255UL) / FADE_MS);
    displayed = blend(fadeStart, fadeTarget, amount);
  }
  fill_solid(leds, LED_COUNT, displayed);
  FastLED.show();
}

void handleCommand(String command) {
  command.trim();
  if (command.startsWith("COLOR ")) {
    int red, green, blue;
    if (sscanf(command.c_str(), "COLOR %d %d %d", &red, &green, &blue) == 3) {
      startFade(CRGB(constrain(red, 0, 255), constrain(green, 0, 255), constrain(blue, 0, 255)));
    }
  } else if (command.startsWith("BRIGHTNESS ")) {
    int value;
    if (sscanf(command.c_str(), "BRIGHTNESS %d", &value) == 1) {
      brightness = constrain(value, 0, 255);
      FastLED.setBrightness(brightness);
      FastLED.show();
    }
  } else if (command.startsWith("STATE ")) {
    // Extension point for fades/pulses on listening, recognition, errors, etc.
    activeState = command.substring(6);
  } else if (command == "OFF") {
    startFade(CRGB::Black);
  }
}

void setup() {
  Serial.begin(115200);
  FastLED.addLeds<CHIPSET, DATA_PIN, COLOR_ORDER>(leds, LED_COUNT);
  FastLED.setMaxPowerInVoltsAndMilliamps(LED_SUPPLY_VOLTS, MAX_POWER_MILLIAMPS);
  FastLED.setBrightness(brightness);
  FastLED.clear(true);
}

void loop() {
  static String command;
  while (Serial.available()) {
    const char input = static_cast<char>(Serial.read());
    if (input == '\n') {
      handleCommand(command);
      command = "";
    } else if (input != '\r' && command.length() < 63) {
      command += input;
    }
  }
  tickFade();
}
