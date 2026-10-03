# ABOUTME: Shared constants for the victrola_stream integration.
# ABOUTME: Single source of truth for NSDK node paths and tuning constants.
from datetime import timedelta

DOMAIN = "victrola_stream"

POLL_TIMEOUT_S = 25
BACKOFF_START_S = 1.0
BACKOFF_MAX_S = 30.0
FULL_REFRESH_INTERVAL = timedelta(minutes=5)

# Identity: stable facts about the device, read once at setup.
NODE_SERIAL = "settings:/system/serialNumber"
NODE_MAC = "settings:/system/primaryMacAddress"
NODE_MANUFACTURER = "settings:/system/manufacturer"
NODE_PRODUCT = "settings:/system/productName"
NODE_DEVICE_NAME = "settings:/deviceName"
NODE_FIRMWARE = "settings:/version"
NODE_MCU_FIRMWARE = "hostlink:hostFirmwareVersion"

# State: values that change while the device runs.
NODE_MOTOR = "hostlink:motorDet"
NODE_SONOS_SESSION = "victrola:isConnectedToSonosGroup"
NODE_UPNP_STATE = "victrola:UpnpState"
NODE_VOLUME = "player:volume"
NODE_MUTE = "settings:/mediaPlayer/mute"
NODE_AUTOPLAY = "settings:/victrola/autoplay"
NODE_KNOB_BRIGHTNESS = "settings:/victrola/lightBrightness"
NODE_STREAMING_QUALITY = "settings:/victrola/forceLowBitrate"
NODE_SONOS_DELAY = "settings:/victrola/wirelessAudioDelay"
NODE_RCA_MODE = "settings:/adchls/dacMode"
NODE_RCA_DELAY = "settings:/adchls/dacDelay"
NODE_RCA_FIXED_VOLUME = "settings:/adchls/fixedVolume"
NODE_POWER = "powermanager:target"
NODE_NETWORK = "network:info"
NODE_RSSI_EVENT = "network:wirelessRssi"  # sends events only; it reads as empty

# Actions: nodes written with role "activate" rather than read for state.
NODE_REBOOT = "powermanager:goReboot"
NODE_SET_DEFAULT_OUTPUT = "victrola:ui/setDefaultOutput"

OUTPUT_TOGGLES: dict[str, str] = {
    "sonos": "settings:/victrola/sonosEnabled",
    "upnp": "settings:/victrola/upnpEnabled",
    "roon": "settings:/victrola/roonEnabled",
    "bluetooth": "settings:/victrola/bluetoothEnabled",
}
SPEAKERS_PATH = "victrola:ui/speakerSelection"
URL_PATHS: dict[str, str] = {
    "hls": "adchls:serverUrl",
    "mp3": "adchls:serverUrl/mp3",
    "flac": "adchls:serverUrl/flac",
}

IDENTITY_PATHS = (
    NODE_SERIAL,
    NODE_MAC,
    NODE_MANUFACTURER,
    NODE_PRODUCT,
    NODE_DEVICE_NAME,
    NODE_FIRMWARE,
    NODE_MCU_FIRMWARE,
)

STATE_PATHS = (
    NODE_MOTOR,
    NODE_SONOS_SESSION,
    NODE_UPNP_STATE,
    NODE_VOLUME,
    NODE_MUTE,
    NODE_AUTOPLAY,
    NODE_KNOB_BRIGHTNESS,
    NODE_STREAMING_QUALITY,
    NODE_SONOS_DELAY,
    NODE_RCA_MODE,
    NODE_RCA_DELAY,
    NODE_RCA_FIXED_VOLUME,
    NODE_POWER,
    NODE_NETWORK,
    *OUTPUT_TOGGLES.values(),
    *URL_PATHS.values(),
)

TRACKED_PATHS = IDENTITY_PATHS + STATE_PATHS + (NODE_RSSI_EVENT,)

SUBSCRIBED_PATHS = (*(p for p in STATE_PATHS if p != NODE_NETWORK), NODE_RSSI_EVENT)
