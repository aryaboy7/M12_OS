import json
import re
import subprocess
from pathlib import Path

try:
    from android.permissions import request_permissions, Permission
    from jnius import autoclass
except Exception:
    request_permissions = None
    Permission = None
    autoclass = None

from kivy.clock import Clock
from kivy.utils import platform
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label

from utils.logger import log
from utils.ui_scale import (
    title_font,
    button_font,
    list_font,
    text_font,
    status_font,
    row_height,
    button_height,
    padding_size,
    spacing_size,
)


BASE_DIR = Path(__file__).resolve().parent.parent
BT_DIR = BASE_DIR / "data" / "bluetooth"
BT_DIR.mkdir(parents=True, exist_ok=True)
SPEAKERS_FILE = BT_DIR / "speakers.json"
DEFAULT_SPEAKER_FILE = BT_DIR / "default_speaker.json"


class BluetoothScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.devices = []
        self.selected_device = None
        self.saved_devices = self.load_saved_devices()
        self.last_scan_mode = "paired"

        root = BoxLayout(
            orientation="vertical",
            padding=padding_size(),
            spacing=spacing_size(),
        )

        root.add_widget(Label(
            text="Bluetooth",
            font_size=title_font(),
            bold=True,
            size_hint=(1, 0.08),
        ))

        self.selected_label = Label(
            text="No device selected",
            font_size=text_font(),
            size_hint=(1, 0.09),
            halign="center",
            valign="middle",
        )
        self.selected_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        root.add_widget(self.selected_label)

        scroll = ScrollView(
            size_hint=(1, 0.34),
            do_scroll_x=False,
            do_scroll_y=True,
        )

        self.device_list = GridLayout(
            cols=1,
            spacing=spacing_size(),
            size_hint_y=None,
        )
        self.device_list.bind(minimum_height=self.device_list.setter("height"))
        scroll.add_widget(self.device_list)
        root.add_widget(scroll)

        row1 = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=button_height(),
        )

        scan_btn = self.make_button("Paired", (0.12, 0.20, 0.35, 1))
        scan_btn.bind(on_press=self.scan_devices)
        row1.add_widget(scan_btn)

        nearby_btn = self.make_button("Nearby", (0.55, 0.45, 0.10, 1))
        nearby_btn.bind(on_press=self.scan_nearby_devices)
        row1.add_widget(nearby_btn)

        pair_btn = self.make_button("Pair", (0.10, 0.45, 0.20, 1))
        pair_btn.bind(on_press=self.pair_selected)
        row1.add_widget(pair_btn)

        root.add_widget(row1)

        row2 = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=button_height(),
        )

        connect_btn = self.make_button("Connect", (0.10, 0.45, 0.20, 1))
        connect_btn.bind(on_press=self.connect_selected)
        row2.add_widget(connect_btn)

        disconnect_btn = self.make_button("Disconnect", (0.35, 0.12, 0.12, 1))
        disconnect_btn.bind(on_press=self.disconnect_selected)
        row2.add_widget(disconnect_btn)

        back_btn = self.make_button("< Back", (0.10, 0.15, 0.25, 1))
        back_btn.bind(on_press=self.go_back)
        row2.add_widget(back_btn)

        root.add_widget(row2)

        row3 = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=button_height(),
        )

        save_btn = self.make_button("Save", (0.42, 0.28, 0.12, 1))
        save_btn.bind(on_press=self.save_selected)
        row3.add_widget(save_btn)

        remove_btn = self.make_button("Remove", (0.35, 0.12, 0.12, 1))
        remove_btn.bind(on_press=self.remove_selected)
        row3.add_widget(remove_btn)

        rescan_btn = self.make_button("Refresh", (0.12, 0.20, 0.35, 1))
        rescan_btn.bind(on_press=self.refresh_last_scan)
        row3.add_widget(rescan_btn)

        root.add_widget(row3)

        row4 = BoxLayout(
            orientation="horizontal",
            spacing=spacing_size(),
            size_hint=(1, None),
            height=button_height(),
        )

        default_btn = self.make_button("Set Default", (0.42, 0.28, 0.12, 1))
        default_btn.bind(on_press=self.set_default_selected)
        row4.add_widget(default_btn)

        self.auto_btn = self.make_button(
            self.auto_connect_text(),
            (0.10, 0.45, 0.20, 1) if self.auto_connect_enabled() else (0.50, 0.15, 0.15, 1)
        )
        self.auto_btn.bind(on_press=self.toggle_auto_connect)
        row4.add_widget(self.auto_btn)

        root.add_widget(row4)

        self.status_label = Label(
            text=self.platform_status_text(),
            font_size=status_font(),
            size_hint=(1, 0.10),
            halign="center",
            valign="middle",
        )
        self.status_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        root.add_widget(self.status_label)

        self.add_widget(root)

    def make_button(self, text, color):
        return Button(
            text=text,
            font_size=button_font(),
            background_normal="",
            background_color=color,
        )

    def platform_status_text(self):
        if platform == "macosx":
            if self.blueutil_available():
                return "Mac Bluetooth ready. Use Paired or Nearby scan."
            return "Install blueutil first:\nbrew install blueutil"

        if platform == "android":
            return (
                "Android Bluetooth ready.\n"
                "Paired = list paired speakers.\n"
                "Phone BT = Android Bluetooth settings."
            )

        return "Bluetooth support for this platform will be added later."

    def request_android_bt_permissions(self):
        if platform != "android":
            return

        if request_permissions is None or Permission is None:
            self.status_label.text = "Android permission API not available."
            return

        try:
            permissions = [
                Permission.BLUETOOTH,
                Permission.BLUETOOTH_ADMIN,
                Permission.ACCESS_FINE_LOCATION,
            ]

            for name in ("BLUETOOTH_CONNECT", "BLUETOOTH_SCAN"):
                if hasattr(Permission, name):
                    permissions.append(getattr(Permission, name))

            request_permissions(permissions)
            log.info("Bluetooth: Android permissions requested")

        except Exception as e:
            self.status_label.text = f"Permission request failed:\n{e}"
            log.error(f"Bluetooth: Android permission request failed {e}")

    def get_android_adapter(self):
        if platform != "android" or autoclass is None:
            return None

        try:
            BluetoothAdapter = autoclass("android.bluetooth.BluetoothAdapter")
            return BluetoothAdapter.getDefaultAdapter()
        except Exception as e:
            log.error(f"Bluetooth: Android adapter failed {e}")
            return None

    def open_android_bluetooth_settings(self):
        if platform != "android" or autoclass is None:
            self.status_label.text = "Android settings API not available."
            return

        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            Settings = autoclass("android.provider.Settings")

            intent = Intent(Settings.ACTION_BLUETOOTH_SETTINGS)
            PythonActivity.mActivity.startActivity(intent)
            self.status_label.text = "Opened Android Bluetooth Settings."
            log.info("Bluetooth: opened Android Bluetooth settings")

        except Exception as e:
            self.status_label.text = f"Open BT settings failed:\n{e}"
            log.error(f"Bluetooth: open Android settings failed {e}")

    def scan_android_paired_devices(self):
        self.request_android_bt_permissions()

        adapter = self.get_android_adapter()

        if adapter is None:
            self.status_label.text = "No Android Bluetooth adapter."
            return []

        try:
            if not adapter.isEnabled():
                self.status_label.text = "Bluetooth is OFF. Turn it ON in Phone BT."
                return []

            bonded = adapter.getBondedDevices()
            iterator = bonded.iterator()
            devices = []

            while iterator.hasNext():
                dev = iterator.next()

                try:
                    name = dev.getName() or "Unknown"
                except Exception:
                    name = "Unknown"

                try:
                    address = dev.getAddress() or ""
                except Exception:
                    address = ""

                if address:
                    devices.append({
                        "name": name,
                        "address": address.lower(),
                        "connected": False,
                        "saved": False,
                        "android_paired": True,
                    })

            return devices

        except Exception as e:
            self.status_label.text = f"Android paired scan failed:\n{e}"
            log.error(f"Bluetooth: Android paired scan failed {e}")
            return []

    def load_default_speaker(self):
        try:
            if DEFAULT_SPEAKER_FILE.exists():
                data = json.loads(DEFAULT_SPEAKER_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception as e:
            log.error(f"Bluetooth: load default speaker failed {e}")

        return {}

    def save_default_speaker_data(self, data):
        try:
            DEFAULT_SPEAKER_FILE.write_text(
                json.dumps(data, indent=4),
                encoding="utf-8",
            )
            return True
        except Exception as e:
            log.error(f"Bluetooth: save default speaker failed {e}")
            return False

    def auto_connect_enabled(self):
        data = self.load_default_speaker()
        return bool(data.get("auto_connect", False))

    def auto_connect_text(self):
        return "Auto ON" if self.auto_connect_enabled() else "Auto OFF"

    def update_auto_button(self):
        if hasattr(self, "auto_btn"):
            enabled = self.auto_connect_enabled()
            self.auto_btn.text = "Auto ON" if enabled else "Auto OFF"
            self.auto_btn.background_color = (
                (0.10, 0.45, 0.20, 1)
                if enabled
                else (0.50, 0.15, 0.15, 1)
            )

    def set_default_selected(self, instance):
        if not self.selected_device:
            self.status_label.text = "Select a speaker first."
            return

        address = self.selected_device.get("address", "")
        if not address:
            self.status_label.text = "Selected device has no address."
            return

        data = {
            "name": self.selected_device.get("name", "Unknown"),
            "address": address,
            "auto_connect": True,
        }

        if self.save_default_speaker_data(data):
            self.status_label.text = "Default speaker saved.\nAuto Connect ON."
            self.update_auto_button()

            saved = self.load_saved_devices()
            if not any(d.get("address") == address for d in saved):
                saved.append({
                    "name": data["name"],
                    "address": address,
                })
                self.saved_devices = saved
                self.save_saved_devices()

            self.do_scan_devices()

    def toggle_auto_connect(self, instance):
        data = self.load_default_speaker()

        if not data.get("address"):
            if self.selected_device and self.selected_device.get("address"):
                data = {
                    "name": self.selected_device.get("name", "Unknown"),
                    "address": self.selected_device.get("address", ""),
                    "auto_connect": True,
                }
            else:
                self.status_label.text = "Select default speaker first."
                return
        else:
            data["auto_connect"] = not bool(data.get("auto_connect", False))

        if self.save_default_speaker_data(data):
            self.status_label.text = self.auto_connect_text()
            self.update_auto_button()

    def auto_connect_default(self):
        if platform == "android":
            data = self.load_default_speaker()
            if data and data.get("auto_connect"):
                log.info("Bluetooth: Android auto connect uses Android system Bluetooth")
            return

        if platform != "macosx":
            return

        data = self.load_default_speaker()

        if not data or not data.get("auto_connect"):
            log.info("Bluetooth: auto connect disabled")
            return

        address = data.get("address", "")
        name = data.get("name", "Default speaker")

        if not address:
            log.warning("Bluetooth: auto connect has no address")
            return

        if not self.blueutil_available():
            log.error("Bluetooth: auto connect requires blueutil")
            return

        self.status_label.text = f"Auto connecting:\n{name}"
        log.info(f"Bluetooth: auto connecting {name} {address}")
        self.do_connect(address)

    def load_saved_devices(self):
        try:
            if SPEAKERS_FILE.exists():
                data = json.loads(SPEAKERS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
        except Exception as e:
            log.error(f"Bluetooth: load saved devices failed {e}")

        return []

    def save_saved_devices(self):
        try:
            SPEAKERS_FILE.write_text(
                json.dumps(self.saved_devices, indent=4),
                encoding="utf-8",
            )
        except Exception as e:
            log.error(f"Bluetooth: save devices failed {e}")

    def blueutil_available(self):
        try:
            result = subprocess.run(
                ["which", "blueutil"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return result.returncode == 0
        except Exception:
            return False

    def run_command(self, command, timeout=20):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return 1, "", str(e)

    def scan_devices(self, instance):
        self.last_scan_mode = "paired"

        if platform == "android":
            self.status_label.text = "Scanning paired Android Bluetooth devices..."
            Clock.schedule_once(lambda dt: self.do_scan_android_devices(), 0.1)
            return

        self.status_label.text = "Scanning paired/recent Bluetooth devices..."
        Clock.schedule_once(lambda dt: self.do_scan_devices(), 0.1)

    def do_scan_android_devices(self):
        self.devices = []

        found = self.scan_android_paired_devices()

        saved = self.load_saved_devices()
        saved_by_address = {
            d.get("address", "").lower(): d
            for d in saved
            if d.get("address")
        }

        for dev in found:
            address = dev.get("address", "").lower()
            if address in saved_by_address:
                dev["saved"] = True

        self.devices = sorted(
            found,
            key=lambda d: (
                not d.get("saved", False),
                d.get("name", "").lower(),
            )
        )

        self.status_label.text = (
            f"Paired devices: {len(self.devices)}\n"
            "Select speaker. If missing, press Phone BT."
        )
        self.rebuild_device_list()

    def scan_nearby_devices(self, instance):
        self.last_scan_mode = "nearby"

        if platform == "android":
            self.open_android_bluetooth_settings()
            return

        if platform != "macosx":
            self.status_label.text = self.platform_status_text()
            return

        if not self.blueutil_available():
            self.status_label.text = "Nearby scan requires blueutil:\nbrew install blueutil"
            return

        self.status_label.text = (
            "Scanning nearby devices...\n"
            "Put speaker in pairing mode. This can take 10-15 seconds."
        )
        Clock.schedule_once(lambda dt: self.do_scan_nearby_devices(), 0.1)

    def refresh_last_scan(self, instance):
        if self.last_scan_mode == "nearby":
            self.scan_nearby_devices(instance)
        else:
            self.scan_devices(instance)

    def do_scan_nearby_devices(self):
        self.devices = []

        if platform != "macosx":
            self.status_label.text = self.platform_status_text()
            self.rebuild_device_list()
            return

        # blueutil --inquiry performs live discovery of nearby discoverable devices.
        found = self.scan_blueutil_inquiry()

        saved = self.load_saved_devices()
        saved_by_address = {
            d.get("address", ""): d
            for d in saved
            if d.get("address")
        }

        for dev in found:
            address = dev.get("address", "")
            if address in saved_by_address:
                dev["saved"] = True

        self.devices = sorted(
            found,
            key=lambda d: (
                not d.get("saved", False),
                d.get("name", "").lower(),
            )
        )

        self.status_label.text = (
            f"Nearby devices found: {len(self.devices)}\n"
            "Select device, then press Pair."
        )
        self.rebuild_device_list()

    def do_scan_devices(self):
        self.devices = []

        if platform != "macosx":
            self.status_label.text = self.platform_status_text()
            self.rebuild_device_list()
            return

        saved = self.load_saved_devices()
        saved_by_address = {
            d.get("address", ""): d
            for d in saved
            if d.get("address")
        }

        found = []

        # Prefer blueutil because it exposes paired/recent Bluetooth devices more reliably.
        if self.blueutil_available():
            found.extend(self.scan_blueutil("--paired"))
            found.extend(self.scan_blueutil("--recent"))
            found.extend(self.scan_blueutil("--connected"))

        # Also scan macOS system profiler as fallback.
        found.extend(self.scan_macos_system_profiler())

        # Deduplicate after combining sources.
        deduped = {}
        for dev in found:
            address = dev.get("address", "").lower().replace("-", ":")
            name = dev.get("name", "Unknown")

            if not address:
                # Keep named devices without address as visible diagnostic rows.
                address = f"name-only:{name.lower()}"

            if address not in deduped:
                dev["address"] = address if not address.startswith("name-only:") else dev.get("address", "")
                deduped[address] = dev
            else:
                old_dev = deduped[address]
                old_dev["connected"] = old_dev.get("connected", False) or dev.get("connected", False)
                old_dev["saved"] = old_dev.get("saved", False) or dev.get("saved", False)
                if old_dev.get("name", "Unknown") == "Unknown" and name != "Unknown":
                    old_dev["name"] = name

        found = list(deduped.values())

        # Mark saved devices and include saved devices even if not visible in scan.
        found_by_address = {
            d.get("address", ""): d
            for d in found
            if d.get("address")
        }

        for address, saved_dev in saved_by_address.items():
            if address in found_by_address:
                found_by_address[address]["saved"] = True
            else:
                saved_dev["saved"] = True
                saved_dev["connected"] = False
                found.append(saved_dev)

        self.devices = sorted(
            found,
            key=lambda d: (
                not d.get("saved", False),
                not d.get("connected", False),
                d.get("name", "").lower(),
            )
        )

        self.status_label.text = f"Devices found: {len(self.devices)}"
        self.rebuild_device_list()

    def scan_macos_system_profiler(self):
        code, out, err = self.run_command(
            ["system_profiler", "SPBluetoothDataType"],
            timeout=30,
        )

        if code != 0:
            self.status_label.text = f"Mac scan failed:\n{err}"
            return []

        devices = []
        current_name = None
        current_address = None
        current_connected = False

        for raw in out.splitlines():
            line = raw.rstrip()
            stripped = line.strip()

            # Device names often appear like: "My Speaker:"
            if stripped.endswith(":") and not stripped.startswith(("Bluetooth", "Controller", "Devices", "Services")):
                # Save previous device if it had an address.
                if current_name and current_address:
                    devices.append({
                        "name": current_name,
                        "address": current_address,
                        "connected": current_connected,
                        "saved": False,
                    })

                current_name = stripped[:-1].strip()
                current_address = None
                current_connected = False
                continue

            if "Address:" in stripped:
                address = stripped.split("Address:", 1)[1].strip().lower()
                if self.is_mac_address(address):
                    current_address = address
                continue

            if "Connected:" in stripped:
                value = stripped.split("Connected:", 1)[1].strip().lower()
                current_connected = value.startswith("yes")
                continue

        if current_name and current_address:
            devices.append({
                "name": current_name,
                "address": current_address,
                "connected": current_connected,
                "saved": False,
            })

        # Deduplicate
        result = []
        seen = set()
        for d in devices:
            address = d.get("address", "")
            if address and address not in seen:
                seen.add(address)
                result.append(d)

        # Bose fallback: if system_profiler text contains Bose but parser missed address,
        # add a diagnostic row so user can confirm it is visible to macOS.
        if not any("bose" in d.get("name", "").lower() for d in result):
            for raw in out.splitlines():
                if "bose" in raw.lower():
                    result.append({
                        "name": raw.strip().rstrip(":"),
                        "address": "",
                        "connected": False,
                        "saved": False,
                    })
                    break

        return result

    def scan_blueutil_inquiry(self):
        code, out, err = self.run_command(["blueutil", "--inquiry"], timeout=30)

        if code != 0:
            self.status_label.text = f"Nearby scan failed:\n{err or out}"
            log.error(f"Bluetooth: inquiry failed: {err or out}")
            return []

        devices = []

        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue

            parsed = self.parse_blueutil_device_line(line)
            if parsed:
                parsed["connected"] = False
                parsed["saved"] = False
                devices.append(parsed)

        # Deduplicate
        deduped = {}
        for dev in devices:
            address = dev.get("address", "")
            if address and address not in deduped:
                deduped[address] = dev

        return list(deduped.values())

    def parse_blueutil_device_line(self, line):
        address = ""
        name = "Unknown"

        address_match = re.search(
            r"(?:address:\s*)?([0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})",
            line
        )
        name_match = re.search(
            r"name:\s*(.+?)(?:,\s*(?:address|connected|paired|recent|rssi|class):|$)",
            line
        )

        if address_match:
            address = address_match.group(1).replace("-", ":").lower()

        if name_match:
            name = name_match.group(1).strip()
        else:
            # Some inquiry lines show address first and then name after comma.
            parts = [p.strip() for p in line.split(",")]
            for part in parts:
                if "name:" in part.lower():
                    name = part.split(":", 1)[1].strip()
                    break

        if not address:
            return None

        return {
            "name": name,
            "address": address,
            "connected": False,
            "saved": False,
        }

    def scan_blueutil(self, mode="--paired"):
        code, out, err = self.run_command(["blueutil", mode], timeout=15)

        if code != 0:
            log.error(f"Bluetooth: blueutil {mode} failed: {err}")
            return []

        devices = []

        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue

            address = ""
            name = "Unknown"
            connected = False

            # Common blueutil formats:
            # address: aa-bb-cc-dd-ee-ff, connected: 1, name: Bose Mini II SoundLink
            # aa-bb-cc-dd-ee-ff, connected: 0, name: Bose Mini II SoundLink
            address_match = re.search(r"(?:address:\s*)?([0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})", line)
            name_match = re.search(r"name:\s*(.+?)(?:,\s*(?:address|connected|paired|recent):|$)", line)
            connected_match = re.search(r"connected:\s*([01]|yes|no|true|false)", line, re.IGNORECASE)

            if address_match:
                address = address_match.group(1).replace("-", ":").lower()

            if name_match:
                name = name_match.group(1).strip()
            else:
                # If the line contains Bose but no name field, keep whole line as name for visibility.
                if "bose" in line.lower():
                    name = line

            if connected_match:
                value = connected_match.group(1).lower()
                connected = value in ("1", "yes", "true")

            if address or name != "Unknown":
                devices.append({
                    "name": name,
                    "address": address,
                    "connected": connected,
                    "saved": False,
                })

        return devices

    def is_mac_address(self, value):
        return bool(re.match(r"^[0-9a-fA-F]{2}([:-][0-9a-fA-F]{2}){5}$", value))

    def rebuild_device_list(self):
        self.device_list.clear_widgets()

        if not self.devices:
            self.device_list.add_widget(Label(
                text="No Bluetooth devices found.\nFor new speakers: put speaker in pairing mode, then press Nearby.",
                font_size=text_font(),
                size_hint_y=None,
                height=max(button_height(), int(row_height() * 0.90)),
                halign="center",
                valign="middle",
            ))
            return

        for dev in self.devices:
            name = dev.get("name", "Unknown")
            address = dev.get("address", "")
            connected = dev.get("connected", False)
            saved = dev.get("saved", False)

            prefix = ""
            if saved:
                prefix += "★ "
            if connected:
                prefix += "[CONNECTED] "

            text = f"{prefix}{name}\n{address}"

            btn = Button(
                text=text,
                font_size=text_font(),
                size_hint_y=None,
                height=max(button_height(), int(row_height() * 0.62)),
                background_normal="",
                background_color=(0.25, 0.45, 0.75, 1)
                if self.selected_device and self.selected_device.get("address") == address
                else (0.10, 0.15, 0.25, 1),
                halign="left",
                valign="middle",
            )
            btn.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - spacing_size(), val[1])))
            btn.bind(on_press=lambda inst, d=dev: self.select_device(d))
            self.device_list.add_widget(btn)

    def select_device(self, dev):
        self.selected_device = dev
        name = dev.get("name", "Unknown")
        address = dev.get("address", "")
        self.selected_label.text = f"Selected:\n{name}\n{address}"
        self.rebuild_device_list()

    def pair_selected(self, instance):
        if not self.selected_device:
            if platform == "android":
                self.open_android_bluetooth_settings()
                return

            self.status_label.text = "Select a nearby Bluetooth device first."
            return

        if platform == "android":
            self.open_android_bluetooth_settings()
            return

        if platform != "macosx":
            self.status_label.text = self.platform_status_text()
            return

        if not self.blueutil_available():
            self.status_label.text = "Pair requires blueutil:\nbrew install blueutil"
            return

        address = self.selected_device.get("address", "")
        if not address:
            self.status_label.text = "Selected device has no address."
            return

        self.status_label.text = "Pairing..."
        Clock.schedule_once(lambda dt: self.do_pair(address), 0.1)

    def do_pair(self, address):
        self.run_command(["blueutil", "--power", "1"], timeout=10)
        code, out, err = self.run_command(["blueutil", "--pair", address], timeout=45)

        if code == 0:
            self.status_label.text = "Paired. Now press Connect."
            log.info(f"Bluetooth: paired {address}")
            self.last_scan_mode = "paired"
            self.do_scan_devices()
        else:
            self.status_label.text = f"Pair failed:\n{err or out}"
            log.error(f"Bluetooth: pair failed {address}: {err or out}")

    def connect_selected(self, instance):
        if not self.selected_device:
            self.status_label.text = "Select a Bluetooth speaker first."
            return

        if platform == "android":
            name = self.selected_device.get("name", "Unknown")
            address = self.selected_device.get("address", "")

            if address:
                self.save_default_speaker_data({
                    "name": name,
                    "address": address,
                    "auto_connect": True,
                    "platform": "android"
                })
                self.update_auto_button()

            self.status_label.text = (
                "Speaker saved as default.\n"
                "Connect audio in Android Bluetooth settings."
            )
            self.open_android_bluetooth_settings()
            return

        if platform != "macosx":
            self.status_label.text = self.platform_status_text()
            return

        if not self.blueutil_available():
            self.status_label.text = "Connect requires blueutil:\nbrew install blueutil"
            return

        address = self.selected_device.get("address", "")
        if not address:
            self.status_label.text = "Selected device has no address."
            return

        self.status_label.text = "Connecting..."
        Clock.schedule_once(lambda dt: self.do_connect(address), 0.1)

    def do_connect(self, address):
        # Turn Bluetooth on, then connect.
        self.run_command(["blueutil", "--power", "1"], timeout=10)
        code, out, err = self.run_command(["blueutil", "--connect", address], timeout=30)

        if code == 0:
            self.status_label.text = "Connected."
            log.info(f"Bluetooth: connected {address}")
        else:
            self.status_label.text = f"Connect failed:\n{err or out}"

        self.do_scan_devices()

    def disconnect_selected(self, instance):
        if not self.selected_device:
            self.status_label.text = "Select a Bluetooth device first."
            return

        if platform == "android":
            self.open_android_bluetooth_settings()
            return

        if platform != "macosx":
            self.status_label.text = self.platform_status_text()
            return

        if not self.blueutil_available():
            self.status_label.text = "Disconnect requires blueutil:\nbrew install blueutil"
            return

        address = self.selected_device.get("address", "")
        self.status_label.text = "Disconnecting..."
        Clock.schedule_once(lambda dt: self.do_disconnect(address), 0.1)

    def do_disconnect(self, address):
        code, out, err = self.run_command(["blueutil", "--disconnect", address], timeout=30)

        if code == 0:
            self.status_label.text = "Disconnected."
            log.info(f"Bluetooth: disconnected {address}")
        else:
            self.status_label.text = f"Disconnect failed:\n{err or out}"

        self.do_scan_devices()

    def save_selected(self, instance):
        if not self.selected_device:
            self.status_label.text = "Select a speaker first."
            return

        address = self.selected_device.get("address", "")
        if not address:
            self.status_label.text = "Selected device has no address."
            return

        saved = self.load_saved_devices()

        for dev in saved:
            if dev.get("address") == address:
                self.status_label.text = "Speaker already saved."
                return

        saved.append({
            "name": self.selected_device.get("name", "Unknown"),
            "address": address,
        })

        self.saved_devices = saved
        self.save_saved_devices()
        self.status_label.text = "Speaker saved."
        self.do_scan_devices()

    def remove_selected(self, instance):
        if not self.selected_device:
            self.status_label.text = "Select a saved speaker first."
            return

        address = self.selected_device.get("address", "")
        saved = self.load_saved_devices()
        new_saved = [d for d in saved if d.get("address") != address]

        self.saved_devices = new_saved
        self.save_saved_devices()
        self.status_label.text = "Speaker removed."
        self.do_scan_devices()

    def go_back(self, instance):
        if self.manager:
            self.manager.current = "home"
