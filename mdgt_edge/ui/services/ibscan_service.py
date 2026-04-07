"""IBScan service — QThread worker bridging sensor callbacks to Qt signals.

Runs IBScanUltimateDriver in a background thread and emits Qt signals
for thread-safe UI updates. All sensor I/O happens off the main thread.
"""
import logging
import queue
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

from PyQt6.QtCore import QThread, pyqtSignal, QMutex

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """Commands that can be sent to the worker thread."""
    OPEN = auto()
    CLOSE = auto()
    BEGIN_CAPTURE = auto()
    CANCEL_CAPTURE = auto()
    SET_PROPERTY = auto()
    ENABLE_SPOOF = auto()
    SET_SPOOF_LEVEL = auto()
    SET_LEDS = auto()
    BEEP = auto()
    NFIQ2_INIT = auto()
    NFIQ2_SCORE = auto()
    SPOOF_CHECK = auto()
    STOP = auto()


@dataclass(frozen=True)
class Command:
    """Immutable command for the worker queue."""
    type: CommandType
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)


class IBScanService(QThread):
    """Background thread managing IBScanUltimate device communication.

    Bridges C callback events to Qt signals for thread-safe UI updates.
    Send commands via ``send_command()``; receive results via signals.
    """

    # --- Signals (emitted on main thread via Qt signal mechanism) ---
    device_connected = pyqtSignal(dict)
    device_disconnected = pyqtSignal()
    device_count_changed = pyqtSignal(int)
    preview_frame = pyqtSignal(bytes, int, int)
    finger_count_changed = pyqtSignal(int)
    finger_quality_changed = pyqtSignal(list)
    capture_complete = pyqtSignal(object)
    spoof_result = pyqtSignal(bool, list)
    nfiq2_score_ready = pyqtSignal(int)
    error_occurred = pyqtSignal(str, int)
    property_changed = pyqtSignal(str, str)
    leds_changed = pyqtSignal(int)
    status_message = pyqtSignal(str)

    def __init__(
        self,
        lib_path: Optional[str] = None,
        nfiq2_lib_path: Optional[str] = None,
        parent: Optional[Any] = None,
    ):
        super().__init__(parent)
        self._lib_path = lib_path
        self._nfiq2_lib_path = nfiq2_lib_path
        self._cmd_queue: queue.Queue[Command] = queue.Queue()
        self._running = False
        self._mutex = QMutex()
        self._driver = None

    # ------------------------------------------------------------------
    # Public API (called from main / UI thread)
    # ------------------------------------------------------------------

    def send_command(self, cmd_type: CommandType, *args: Any, **kwargs: Any) -> None:
        """Enqueue a command for the worker thread."""
        self._cmd_queue.put(Command(cmd_type, args, kwargs))

    def open_device(self, index: int = 0) -> None:
        self.send_command(CommandType.OPEN, index)

    def close_device(self) -> None:
        self.send_command(CommandType.CLOSE)

    def begin_capture(
        self, image_type: int = 2, resolution: int = 500, options: int = 3,
    ) -> None:
        self.send_command(CommandType.BEGIN_CAPTURE, image_type, resolution, options)

    def cancel_capture(self) -> None:
        self.send_command(CommandType.CANCEL_CAPTURE)

    def set_property(self, prop_id: int, value: str) -> None:
        self.send_command(CommandType.SET_PROPERTY, prop_id, value)

    def enable_spoof(self, enabled: bool) -> None:
        self.send_command(CommandType.ENABLE_SPOOF, enabled)

    def set_spoof_level(self, level: int) -> None:
        self.send_command(CommandType.SET_SPOOF_LEVEL, level)

    def set_leds(self, mask: int) -> None:
        self.send_command(CommandType.SET_LEDS, mask)

    def beep(self, duration_ms: int = 100) -> None:
        self.send_command(CommandType.BEEP, duration_ms)

    def request_nfiq2_init(self) -> None:
        self.send_command(CommandType.NFIQ2_INIT)

    def request_nfiq2_score(
        self, image_data: bytes, width: int, height: int,
    ) -> None:
        self.send_command(CommandType.NFIQ2_SCORE, image_data, width, height)

    def request_spoof_check(
        self, image_data: bytes, width: int, height: int,
    ) -> None:
        self.send_command(CommandType.SPOOF_CHECK, image_data, width, height)

    def stop(self) -> None:
        """Request graceful shutdown."""
        self._running = False
        self.send_command(CommandType.STOP)

    @property
    def is_device_open(self) -> bool:
        if self._driver is None:
            return False
        return self._driver.is_open

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Worker thread main loop — processes command queue."""
        self._running = True
        self._init_driver()

        while self._running:
            try:
                cmd = self._cmd_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if cmd.type == CommandType.STOP:
                break

            try:
                self._dispatch(cmd)
            except Exception as exc:
                logger.exception("Command %s failed", cmd.type.name)
                self.error_occurred.emit(str(exc), -1)

        self._cleanup()

    # ------------------------------------------------------------------
    # Driver lifecycle
    # ------------------------------------------------------------------

    def _init_driver(self) -> None:
        try:
            from mdgt_edge.sensor.ibscan_driver import IBScanUltimateDriver
            self._driver = IBScanUltimateDriver(
                self._lib_path, self._nfiq2_lib_path,
            )
            self._driver.on_preview = self._on_preview
            self._driver.on_finger_count = self._on_finger_count
            self._driver.on_finger_quality = self._on_finger_quality
            self._driver.on_result = self._on_result
            self._driver.on_device_count = self._on_device_count
            self.status_message.emit("IBScan driver initialized")
        except Exception as exc:
            logger.error("Failed to initialize IBScan driver: %s", exc)
            self.error_occurred.emit(f"Driver init failed: {exc}", -1)
            self._driver = None

    def _cleanup(self) -> None:
        if self._driver is not None:
            try:
                self._driver.close_device()
            except Exception:
                pass
            self._driver = None
        self.status_message.emit("IBScan service stopped")

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, cmd: Command) -> None:
        handler = {
            CommandType.OPEN: self._handle_open,
            CommandType.CLOSE: self._handle_close,
            CommandType.BEGIN_CAPTURE: self._handle_begin_capture,
            CommandType.CANCEL_CAPTURE: self._handle_cancel_capture,
            CommandType.SET_PROPERTY: self._handle_set_property,
            CommandType.ENABLE_SPOOF: self._handle_enable_spoof,
            CommandType.SET_SPOOF_LEVEL: self._handle_set_spoof_level,
            CommandType.SET_LEDS: self._handle_set_leds,
            CommandType.BEEP: self._handle_beep,
            CommandType.NFIQ2_INIT: self._handle_nfiq2_init,
            CommandType.NFIQ2_SCORE: self._handle_nfiq2_score,
            CommandType.SPOOF_CHECK: self._handle_spoof_check,
        }.get(cmd.type)

        if handler is not None:
            handler(*cmd.args, **cmd.kwargs)

    def _handle_open(self, index: int = 0) -> None:
        if self._driver is None:
            self.error_occurred.emit("Driver not initialized", -1)
            return
        self._driver.open_device(index)
        self._driver.register_callbacks()
        info = self._driver.get_device_description(index)
        self.device_connected.emit({
            "serial_number": info.serial_number,
            "product_name": info.product_name,
            "firmware_version": info.firmware_version,
            "revision": info.revision,
            "interface_type": info.interface_type,
            "is_locked": info.is_locked,
        })
        self.status_message.emit(f"Connected: {info.product_name}")

    def _handle_close(self) -> None:
        if self._driver is None:
            return
        self._driver.close_device()
        self.device_disconnected.emit()
        self.status_message.emit("Device disconnected")

    def _handle_begin_capture(
        self, image_type: int = 2, resolution: int = 500, options: int = 3,
    ) -> None:
        if self._driver is None:
            return
        self._driver.begin_capture(image_type, resolution, options)
        self.status_message.emit("Capture started")

    def _handle_cancel_capture(self) -> None:
        if self._driver is None:
            return
        self._driver.cancel_capture()
        self.status_message.emit("Capture cancelled")

    def _handle_set_property(self, prop_id: int, value: str) -> None:
        if self._driver is None:
            return
        self._driver.set_property(prop_id, value)
        self.property_changed.emit(str(prop_id), value)

    def _handle_enable_spoof(self, enabled: bool) -> None:
        if self._driver is None:
            return
        self._driver.enable_spoof(enabled)
        self.status_message.emit(f"PAD {'enabled' if enabled else 'disabled'}")

    def _handle_set_spoof_level(self, level: int) -> None:
        if self._driver is None:
            return
        self._driver.set_spoof_level(level)
        self.status_message.emit(f"Spoof level set to {level}")

    def _handle_set_leds(self, mask: int) -> None:
        if self._driver is None:
            return
        self._driver.set_leds(mask)
        self.leds_changed.emit(mask)

    def _handle_beep(self, duration_ms: int = 100) -> None:
        if self._driver is None:
            return
        self._driver.beeper_control(duration_ms)

    def _handle_nfiq2_init(self) -> None:
        if self._driver is None:
            return
        self._driver.nfiq2_initialize()
        self.status_message.emit("NFIQ2 initialized")

    def _handle_nfiq2_score(
        self, image_data: bytes, width: int, height: int,
    ) -> None:
        if self._driver is None:
            return
        score = self._driver.nfiq2_compute_score(image_data, width, height)
        self.nfiq2_score_ready.emit(score)

    def _handle_spoof_check(
        self, image_data: bytes, width: int, height: int,
    ) -> None:
        if self._driver is None:
            return
        is_spoof = self._driver.check_spoof_from_bytes(image_data, width, height)
        self.spoof_result.emit(is_spoof, [{"finger": 0, "is_spoof": is_spoof}])

    # ------------------------------------------------------------------
    # C callback handlers (called from SDK thread → emit Qt signals)
    # ------------------------------------------------------------------

    def _on_preview(self, data: bytes, width: int, height: int) -> None:
        self.preview_frame.emit(data, width, height)

    def _on_finger_count(self, state: int) -> None:
        self.finger_count_changed.emit(int(state))

    def _on_finger_quality(self, qualities: list) -> None:
        self.finger_quality_changed.emit([int(q) for q in qualities])

    def _on_result(
        self, status: int, img_bytes: bytes,
        width: int, height: int,
        segments: tuple, finger_count: int,
    ) -> None:
        from mdgt_edge.sensor.ibscan_driver import IBScanCaptureResult
        result = IBScanCaptureResult(
            success=status == 0,
            image_data=img_bytes,
            width=width,
            height=height,
            finger_count=finger_count,
            segment_images=segments,
            error="" if status == 0 else f"Capture status: {status}",
        )
        self.capture_complete.emit(result)
        self.status_message.emit(
            "Capture complete" if result.success else f"Capture failed (status={status})",
        )

    def _on_device_count(self, count: int) -> None:
        self.device_count_changed.emit(count)
