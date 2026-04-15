"""IBScanUltimate sensor driver using ctypes bindings.

Wraps libIBScanUltimate.so and libIBScanNFIQ2.so for Python access.
Provides both the low-level IBScanUltimateDriver (ctypes) and the
high-level IBScanSensorDriver (implements SensorDriver ABC).
"""
import ctypes
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .ibscan_types import (
    IBSU_CallbackCompleteAcquisition,
    IBSU_CallbackDeviceCount,
    IBSU_CallbackFingerCount,
    IBSU_CallbackFingerQuality,
    IBSU_CallbackKeyButtons,
    IBSU_CallbackPreviewImage,
    IBSU_CallbackResultImageEx,
    IBSU_CallbackTakingAcquisition,
    IBSU_DeviceDesc,
    IBSU_FingerCountState,
    IBSU_FingerQualityState,
    IBSU_ImageData,
    IBSU_ImageResolution,
    IBSU_ImageType,
    IBSU_PropertyId,
    IBSU_SegmentPosition,
    IBSU_STATUS_OK,
    IBSU_ERR_DEVICE_NOT_FOUND,
    IBSU_ERR_PAD_PROPERTY_DISABLED,
    IBSU_OPTION_AUTO_CAPTURE,
    IBSU_OPTION_AUTO_CONTRAST,
    IBSU_MAX_STR_LEN,
    error_code_to_name,
)
from .base import CaptureResult, LEDColor, SensorDriver, SensorInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Immutable result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IBScanDeviceInfo:
    """Immutable device information."""
    serial_number: str
    product_name: str
    interface_type: str
    firmware_version: str
    revision: str
    is_locked: bool


@dataclass(frozen=True)
class IBScanCaptureResult:
    """Immutable capture result with extended info."""
    success: bool
    image_data: bytes = b""
    width: int = 0
    height: int = 0
    resolution: float = 500.0
    quality_score: float = 0.0
    nfiq2_score: int = 0
    is_spoof: Optional[bool] = None
    finger_count: int = 0
    segment_images: Tuple[bytes, ...] = ()
    segment_qualities: Tuple[int, ...] = ()
    error: str = ""


class IBScanError(Exception):
    """Exception raised by IBScanUltimate SDK calls."""

    def __init__(self, message: str, code: int = -1):
        self.code = code
        super().__init__(f"{message} (code={code}, {error_code_to_name(code)})")


# ---------------------------------------------------------------------------
# Helper: extract raw bytes from IBSU_ImageData
# ---------------------------------------------------------------------------

def _image_data_to_bytes(img: IBSU_ImageData) -> bytes:
    """Copy pixel buffer from an IBSU_ImageData struct to Python bytes."""
    if not img.Buffer:
        return b""
    nbytes = int(img.Width) * int(img.Height) * (img.BitsPerPixel // 8)
    return ctypes.string_at(img.Buffer, nbytes)


def _check(rc: int, context: str = "") -> None:
    """Raise IBScanError if *rc* is not IBSU_STATUS_OK."""
    if rc != IBSU_STATUS_OK:
        raise IBScanError(context, rc)


# ---------------------------------------------------------------------------
# Low-level ctypes driver
# ---------------------------------------------------------------------------

class IBScanUltimateDriver:
    """Python ctypes wrapper for IBScanUltimate SDK.

    Provides device management, capture, PAD/spoof detection,
    NFIQ2 quality scoring, LED control, and image export.

    Thread-safety: every public method acquires ``_lock``.
    """

    _LIB_SEARCH_PATHS = [
        "/usr/lib",
        "/usr/local/lib",
        "/usr/lib/aarch64-linux-gnu",
        "/opt/IBScanUltimate/lib",
        "/opt/IBScanUltimate/lib/aarch64-linux-gnu",
    ]

    def __init__(
        self,
        lib_path: Optional[str] = None,
        nfiq2_lib_path: Optional[str] = None,
    ):
        self._lib: Optional[ctypes.CDLL] = None
        self._nfiq2_lib: Optional[ctypes.CDLL] = None
        self._handle: int = -1
        self._lock = threading.Lock()
        self._is_open = False

        # prevent GC of C callback pointers
        self._cb_preview: Optional[IBSU_CallbackPreviewImage] = None
        self._cb_finger_count: Optional[IBSU_CallbackFingerCount] = None
        self._cb_finger_quality: Optional[IBSU_CallbackFingerQuality] = None
        self._cb_result_ex: Optional[IBSU_CallbackResultImageEx] = None
        self._cb_device_count: Optional[IBSU_CallbackDeviceCount] = None
        self._cb_taking: Optional[IBSU_CallbackTakingAcquisition] = None
        self._cb_complete: Optional[IBSU_CallbackCompleteAcquisition] = None
        self._cb_key: Optional[IBSU_CallbackKeyButtons] = None

        # Python-side handlers
        self.on_preview: Optional[Callable] = None
        self.on_finger_count: Optional[Callable] = None
        self.on_finger_quality: Optional[Callable] = None
        self.on_result: Optional[Callable] = None
        self.on_device_count: Optional[Callable] = None
        self.on_taking_acquisition: Optional[Callable] = None
        self.on_complete_acquisition: Optional[Callable] = None
        self.on_key_buttons: Optional[Callable] = None

        self._nfiq2_initialized = False
        self._load_library(lib_path)
        self._load_nfiq2_library(nfiq2_lib_path)

    # ------------------------------------------------------------------
    # Library loading
    # ------------------------------------------------------------------

    def _find_lib(self, name: str, explicit: Optional[str]) -> Optional[str]:
        if explicit:
            p = Path(explicit)
            if p.is_file():
                return str(p)
        env_dirs = [
            os.environ.get("MDGT_IBSCAN_LIB_DIR"),
            os.environ.get("IBSCAN_LIB_DIR"),
        ]
        for d in env_dirs:
            if not d:
                continue
            p = Path(d) / name
            if p.is_file():
                return str(p)
        for d in self._LIB_SEARCH_PATHS:
            p = Path(d) / name
            if p.is_file():
                return str(p)
        return None

    def _load_library(self, lib_path: Optional[str]) -> None:
        path = self._find_lib("libIBScanUltimate.so", lib_path)
        if path is None:
            logger.warning("libIBScanUltimate.so not found — driver will be non-functional")
            return
        try:
            self._lib = ctypes.cdll.LoadLibrary(path)
            self._setup_functions()
            logger.info("Loaded IBScanUltimate from %s", path)
        except OSError as exc:
            logger.error("Failed to load IBScanUltimate: %s", exc)
            self._lib = None

    def _load_nfiq2_library(self, lib_path: Optional[str]) -> None:
        path = self._find_lib("libIBScanNFIQ2.so", lib_path)
        if path is None:
            logger.info("libIBScanNFIQ2.so not found — NFIQ2 scoring unavailable")
            return
        try:
            self._nfiq2_lib = ctypes.cdll.LoadLibrary(path)
            self._setup_nfiq2_functions()
            logger.info("Loaded IBScanNFIQ2 from %s", path)
        except OSError as exc:
            logger.error("Failed to load IBScanNFIQ2: %s", exc)
            self._nfiq2_lib = None

    # ------------------------------------------------------------------
    # Function signature setup
    # ------------------------------------------------------------------

    def _setup_functions(self) -> None:
        lib = self._lib
        if lib is None:
            return

        # --- Device management ---
        lib.IBSU_GetDeviceCount.argtypes = [ctypes.POINTER(ctypes.c_int)]
        lib.IBSU_GetDeviceCount.restype = ctypes.c_int

        lib.IBSU_GetDeviceDescription.argtypes = [
            ctypes.c_int, ctypes.POINTER(IBSU_DeviceDesc),
        ]
        lib.IBSU_GetDeviceDescription.restype = ctypes.c_int

        lib.IBSU_OpenDevice.argtypes = [
            ctypes.c_int, ctypes.POINTER(ctypes.c_int),
        ]
        lib.IBSU_OpenDevice.restype = ctypes.c_int

        lib.IBSU_OpenDeviceEx.argtypes = [
            ctypes.c_int, ctypes.c_char_p,
            ctypes.c_int, ctypes.POINTER(ctypes.c_int),
        ]
        lib.IBSU_OpenDeviceEx.restype = ctypes.c_int

        lib.IBSU_CloseDevice.argtypes = [ctypes.c_int]
        lib.IBSU_CloseDevice.restype = ctypes.c_int

        lib.IBSU_CloseAllDevice.argtypes = []
        lib.IBSU_CloseAllDevice.restype = ctypes.c_int

        lib.IBSU_IsDeviceOpened.argtypes = [ctypes.c_int]
        lib.IBSU_IsDeviceOpened.restype = ctypes.c_int

        # --- Properties ---
        lib.IBSU_SetProperty.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_char_p,
        ]
        lib.IBSU_SetProperty.restype = ctypes.c_int

        lib.IBSU_GetProperty.argtypes = [
            ctypes.c_int, ctypes.c_int,
            ctypes.c_char * IBSU_MAX_STR_LEN,
        ]
        lib.IBSU_GetProperty.restype = ctypes.c_int

        # --- Capture ---
        lib.IBSU_IsCaptureAvailable.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
        ]
        lib.IBSU_IsCaptureAvailable.restype = ctypes.c_int

        lib.IBSU_BeginCaptureImage.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ]
        lib.IBSU_BeginCaptureImage.restype = ctypes.c_int

        lib.IBSU_CancelCaptureImage.argtypes = [ctypes.c_int]
        lib.IBSU_CancelCaptureImage.restype = ctypes.c_int

        # --- Spoof ---
        lib.IBSU_IsSpoofFingerDetected.argtypes = [
            ctypes.c_int, IBSU_ImageData, ctypes.POINTER(ctypes.c_int),
        ]
        lib.IBSU_IsSpoofFingerDetected.restype = ctypes.c_int

        # --- Error string ---
        lib.IBSU_GetErrorString.argtypes = [
            ctypes.c_int, ctypes.c_char * IBSU_MAX_STR_LEN,
        ]
        lib.IBSU_GetErrorString.restype = ctypes.c_int

        # --- LED ---
        lib.IBSU_SetLEDs.argtypes = [ctypes.c_int, ctypes.c_ulong]
        lib.IBSU_SetLEDs.restype = ctypes.c_int

        lib.IBSU_GetLEDs.argtypes = [
            ctypes.c_int, ctypes.POINTER(ctypes.c_ulong),
        ]
        lib.IBSU_GetLEDs.restype = ctypes.c_int

        # --- Beeper ---
        lib.IBSU_SetBeeper.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ]
        lib.IBSU_SetBeeper.restype = ctypes.c_int

        # --- Callbacks ---
        lib.IBSU_RegisterCallbacks.argtypes = [
            ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_void_p,
        ]
        lib.IBSU_RegisterCallbacks.restype = ctypes.c_int

        # --- Image save ---
        lib.IBSU_SaveBitmapImage.argtypes = [
            ctypes.c_char_p, ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_uint, ctypes.c_uint, ctypes.c_int,
            ctypes.c_double, ctypes.c_double,
        ]
        lib.IBSU_SaveBitmapImage.restype = ctypes.c_int

        lib.IBSU_SavePngImage.argtypes = [
            ctypes.c_char_p, ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_uint, ctypes.c_uint, ctypes.c_int,
            ctypes.c_double, ctypes.c_double,
        ]
        lib.IBSU_SavePngImage.restype = ctypes.c_int

        lib.IBSU_WSQEncodeToFile.argtypes = [
            ctypes.c_char_p, ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_uint, ctypes.c_uint, ctypes.c_int,
            ctypes.c_int, ctypes.c_double,
        ]
        lib.IBSU_WSQEncodeToFile.restype = ctypes.c_int

        lib.IBSU_SaveJP2Image.argtypes = [
            ctypes.c_char_p, ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_uint, ctypes.c_uint, ctypes.c_int,
            ctypes.c_double, ctypes.c_double,
        ]
        lib.IBSU_SaveJP2Image.restype = ctypes.c_int

        # --- NFIQ ---
        lib.IBSU_GetNFIQScore.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_uint, ctypes.c_uint, ctypes.c_ubyte,
            ctypes.POINTER(ctypes.c_int),
        ]
        lib.IBSU_GetNFIQScore.restype = ctypes.c_int

        # --- Capture state ---
        lib.IBSU_IsCaptureActive.argtypes = [
            ctypes.c_int, ctypes.POINTER(ctypes.c_int),
        ]
        lib.IBSU_IsCaptureActive.restype = ctypes.c_int

        lib.IBSU_TakeResultImageManually.argtypes = [ctypes.c_int]
        lib.IBSU_TakeResultImageManually.restype = ctypes.c_int

        # --- Duplicate / finger geometry ---
        lib.IBSU_RemoveFingerImage.argtypes = [
            ctypes.c_int, ctypes.c_ulong,
        ]
        lib.IBSU_RemoveFingerImage.restype = ctypes.c_int

        lib.IBSU_AddFingerImage.argtypes = [
            ctypes.c_int, IBSU_ImageData, ctypes.c_ulong,
            ctypes.c_int,  # imageType
        ]
        lib.IBSU_AddFingerImage.restype = ctypes.c_int

        lib.IBSU_IsFingerDuplicated.argtypes = [
            ctypes.c_int, IBSU_ImageData, ctypes.c_ulong,
            ctypes.c_int,  # imageType
            ctypes.POINTER(ctypes.c_int),  # pMatchedPosition
        ]
        lib.IBSU_IsFingerDuplicated.restype = ctypes.c_int

        lib.IBSU_IsValidFingerGeometry.argtypes = [
            ctypes.c_int, IBSU_ImageData, ctypes.c_ulong,
            ctypes.c_int,  # imageType
            ctypes.POINTER(ctypes.c_int),  # pValid
        ]
        lib.IBSU_IsValidFingerGeometry.restype = ctypes.c_int

        # --- Rolling info ---
        lib.IBSU_BGetRollingInfo.argtypes = [
            ctypes.c_int, ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ]
        lib.IBSU_BGetRollingInfo.restype = ctypes.c_int

        # --- In-memory WSQ ---
        lib.IBSU_WSQEncodeMem.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),  # image
            ctypes.c_uint, ctypes.c_uint,    # width, height
            ctypes.c_int,                     # pitch
            ctypes.c_int,                     # bpp
            ctypes.c_int,                     # ppi
            ctypes.c_double,                  # bitRate
            ctypes.POINTER(ctypes.c_void_p),  # pOutWSQ
            ctypes.POINTER(ctypes.c_uint),    # pOutLength
        ]
        lib.IBSU_WSQEncodeMem.restype = ctypes.c_int

        lib.IBSU_WSQDecodeMem.argtypes = [
            ctypes.c_void_p, ctypes.c_uint,   # wsqData, wsqLength
            ctypes.POINTER(ctypes.c_void_p),   # pOutImage
            ctypes.POINTER(ctypes.c_uint),     # pOutWidth
            ctypes.POINTER(ctypes.c_uint),     # pOutHeight
            ctypes.POINTER(ctypes.c_int),      # pOutPitch
            ctypes.POINTER(ctypes.c_int),      # pOutBpp
            ctypes.POINTER(ctypes.c_int),      # pOutPpi
        ]
        lib.IBSU_WSQDecodeMem.restype = ctypes.c_int

        lib.IBSU_FreeMemory.argtypes = [ctypes.c_void_p]
        lib.IBSU_FreeMemory.restype = ctypes.c_int

        # --- ISO/ANSI template ---
        lib.IBSU_ConvertImageToISOANSI.argtypes = [
            ctypes.c_int,           # handle
            IBSU_ImageData,         # image
            ctypes.c_uint,          # imageCount (1 for single)
            ctypes.c_int,           # fingerPosition (IBSM_FingerPosition)
            ctypes.c_int,           # standardFormat
            ctypes.POINTER(ctypes.c_void_p),  # pOutTemplate
            ctypes.POINTER(ctypes.c_uint),    # pOutTemplateLength
        ]
        lib.IBSU_ConvertImageToISOANSI.restype = ctypes.c_int

        # --- Contrast ---
        lib.IBSU_GetContrast.argtypes = [
            ctypes.c_int, ctypes.POINTER(ctypes.c_int),
        ]
        lib.IBSU_GetContrast.restype = ctypes.c_int

        lib.IBSU_SetContrast.argtypes = [ctypes.c_int, ctypes.c_int]
        lib.IBSU_SetContrast.restype = ctypes.c_int

        # --- Release callbacks ---
        lib.IBSU_ReleaseCallbacks.argtypes = [
            ctypes.c_int, ctypes.c_int,
        ]
        lib.IBSU_ReleaseCallbacks.restype = ctypes.c_int

        # --- Trace log ---
        lib.IBSU_EnableTraceLog.argtypes = [ctypes.c_int]
        lib.IBSU_EnableTraceLog.restype = ctypes.c_int

        # --- SDK version ---
        lib.IBSU_GetSDKVersion.argtypes = [
            ctypes.POINTER(ctypes.c_char * IBSU_MAX_STR_LEN),
        ]
        lib.IBSU_GetSDKVersion.restype = ctypes.c_int

    def _setup_nfiq2_functions(self) -> None:
        lib = self._nfiq2_lib
        if lib is None:
            return

        lib.IBSU_NFIQ2_GetVersion.argtypes = [
            ctypes.c_char * IBSU_MAX_STR_LEN,
        ]
        lib.IBSU_NFIQ2_GetVersion.restype = ctypes.c_int

        lib.IBSU_NFIQ2_Initialize.argtypes = []
        lib.IBSU_NFIQ2_Initialize.restype = ctypes.c_int

        lib.IBSU_NFIQ2_IsInitialized.argtypes = [ctypes.POINTER(ctypes.c_int)]
        lib.IBSU_NFIQ2_IsInitialized.restype = ctypes.c_int

        lib.IBSU_NFIQ2_ComputeScore.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_uint, ctypes.c_uint, ctypes.c_ubyte,
            ctypes.POINTER(ctypes.c_int),
        ]
        lib.IBSU_NFIQ2_ComputeScore.restype = ctypes.c_int

    # ------------------------------------------------------------------
    # Device management
    # ------------------------------------------------------------------

    def get_device_count(self) -> int:
        with self._lock:
            if self._lib is None:
                return 0
            count = ctypes.c_int(0)
            rc = self._lib.IBSU_GetDeviceCount(ctypes.byref(count))
            if rc != IBSU_STATUS_OK:
                logger.warning("GetDeviceCount failed: %s", error_code_to_name(rc))
                return 0
            return count.value

    def get_device_description(self, index: int = 0) -> IBScanDeviceInfo:
        with self._lock:
            if self._lib is None:
                raise IBScanError("Library not loaded", -1)
            desc = IBSU_DeviceDesc()
            _check(
                self._lib.IBSU_GetDeviceDescription(index, ctypes.byref(desc)),
                "GetDeviceDescription",
            )
            return IBScanDeviceInfo(
                serial_number=desc.serialNumber.decode("utf-8", errors="replace").strip("\x00"),
                product_name=desc.productName.decode("utf-8", errors="replace").strip("\x00"),
                interface_type=desc.interfaceType.decode("utf-8", errors="replace").strip("\x00"),
                firmware_version=desc.fwVersion.decode("utf-8", errors="replace").strip("\x00"),
                revision=desc.devRevision.decode("utf-8", errors="replace").strip("\x00"),
                is_locked=bool(desc.IsDeviceLocked),
            )

    def open_device(self, index: int = 0, uniformity_mask_path: str = "") -> None:
        with self._lock:
            if self._lib is None:
                raise IBScanError("Library not loaded", -1)
            if self._is_open:
                logger.warning("Device already open (handle=%d)", self._handle)
                return
            handle = ctypes.c_int(-1)
            if uniformity_mask_path:
                _check(
                    self._lib.IBSU_OpenDeviceEx(
                        index,
                        uniformity_mask_path.encode("utf-8"),
                        ctypes.c_int(0),
                        ctypes.byref(handle),
                    ),
                    "OpenDeviceEx",
                )
            else:
                _check(
                    self._lib.IBSU_OpenDevice(index, ctypes.byref(handle)),
                    "OpenDevice",
                )
            self._handle = handle.value
            self._is_open = True
            logger.info("Opened device index=%d handle=%d", index, self._handle)

    def close_device(self) -> None:
        with self._lock:
            if not self._is_open or self._lib is None:
                return
            rc = self._lib.IBSU_CloseDevice(self._handle)
            if rc != IBSU_STATUS_OK:
                logger.warning("CloseDevice returned %s", error_code_to_name(rc))
            self._handle = -1
            self._is_open = False
            logger.info("Device closed")

    @property
    def is_open(self) -> bool:
        return self._is_open

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def set_property(self, prop_id: int, value: str) -> None:
        with self._lock:
            self._require_open()
            _check(
                self._lib.IBSU_SetProperty(
                    self._handle, prop_id, value.encode("utf-8"),
                ),
                f"SetProperty({prop_id})",
            )

    def get_property(self, prop_id: int) -> str:
        with self._lock:
            self._require_open()
            buf = (ctypes.c_char * IBSU_MAX_STR_LEN)()
            _check(
                self._lib.IBSU_GetProperty(self._handle, prop_id, buf),
                f"GetProperty({prop_id})",
            )
            return buf.value.decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def is_capture_available(
        self,
        image_type: int = IBSU_ImageType.FLAT_SINGLE_FINGER,
        resolution: int = IBSU_ImageResolution.RESOLUTION_500,
    ) -> bool:
        with self._lock:
            self._require_open()
            avail = ctypes.c_int(0)
            rc = self._lib.IBSU_IsCaptureAvailable(
                self._handle, image_type, resolution, ctypes.byref(avail),
            )
            return rc == IBSU_STATUS_OK and avail.value != 0

    def begin_capture(
        self,
        image_type: int = IBSU_ImageType.FLAT_SINGLE_FINGER,
        resolution: int = IBSU_ImageResolution.RESOLUTION_500,
        capture_options: int = IBSU_OPTION_AUTO_CONTRAST | IBSU_OPTION_AUTO_CAPTURE,
    ) -> None:
        with self._lock:
            self._require_open()
            _check(
                self._lib.IBSU_BeginCaptureImage(
                    self._handle, image_type, resolution, capture_options,
                ),
                "BeginCaptureImage",
            )
            logger.info(
                "Capture started: type=%s res=%d opts=0x%x",
                image_type, resolution, capture_options,
            )

    def cancel_capture(self) -> None:
        with self._lock:
            self._require_open()
            rc = self._lib.IBSU_CancelCaptureImage(self._handle)
            if rc != IBSU_STATUS_OK:
                logger.warning("CancelCapture: %s", error_code_to_name(rc))

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def register_callbacks(self) -> None:
        """Register all C callbacks that bridge to Python handlers."""
        with self._lock:
            self._require_open()
            self._register_cb_preview()
            self._register_cb_finger_count()
            self._register_cb_finger_quality()
            self._register_cb_result_ex()
            self._register_cb_device_count()

    def _register_cb_preview(self) -> None:
        def _on_preview(handle: int, ctx: int, image: IBSU_ImageData) -> None:
            try:
                if self.on_preview:
                    data = _image_data_to_bytes(image)
                    self.on_preview(data, int(image.Width), int(image.Height))
            except Exception:
                logger.exception("Preview callback error")

        self._cb_preview = IBSU_CallbackPreviewImage(_on_preview)
        from .ibscan_types import IBSU_Events
        self._lib.IBSU_RegisterCallbacks(
            self._handle,
            IBSU_Events.PREVIEW_IMAGE,
            ctypes.cast(self._cb_preview, ctypes.c_void_p),
            None,
        )

    def _register_cb_finger_count(self) -> None:
        def _on_fc(handle: int, ctx: int, state: int) -> None:
            try:
                if self.on_finger_count:
                    self.on_finger_count(IBSU_FingerCountState(state))
            except Exception:
                logger.exception("FingerCount callback error")

        self._cb_finger_count = IBSU_CallbackFingerCount(_on_fc)
        from .ibscan_types import IBSU_Events
        self._lib.IBSU_RegisterCallbacks(
            self._handle,
            IBSU_Events.FINGER_COUNT,
            ctypes.cast(self._cb_finger_count, ctypes.c_void_p),
            None,
        )

    def _register_cb_finger_quality(self) -> None:
        def _on_fq(handle: int, ctx: int, arr: ctypes.POINTER(ctypes.c_int), count: int) -> None:
            try:
                if self.on_finger_quality:
                    qualities = [IBSU_FingerQualityState(arr[i]) for i in range(count)]
                    self.on_finger_quality(qualities)
            except Exception:
                logger.exception("FingerQuality callback error")

        self._cb_finger_quality = IBSU_CallbackFingerQuality(_on_fq)
        from .ibscan_types import IBSU_Events
        self._lib.IBSU_RegisterCallbacks(
            self._handle,
            IBSU_Events.FINGER_QUALITY,
            ctypes.cast(self._cb_finger_quality, ctypes.c_void_p),
            None,
        )

    def _register_cb_result_ex(self) -> None:
        def _on_result(
            handle: int, ctx: int, status: int,
            image: IBSU_ImageData, image_type: int,
            detected_count: int, seg_count: int,
            seg_arr: ctypes.POINTER(IBSU_ImageData),
            seg_pos: ctypes.POINTER(IBSU_SegmentPosition),
        ) -> None:
            try:
                if self.on_result:
                    main_bytes = _image_data_to_bytes(image)
                    segments = []
                    for i in range(seg_count):
                        segments.append(_image_data_to_bytes(seg_arr[i]))
                    self.on_result(
                        status, main_bytes,
                        int(image.Width), int(image.Height),
                        tuple(segments), detected_count,
                    )
            except Exception:
                logger.exception("ResultImageEx callback error")

        self._cb_result_ex = IBSU_CallbackResultImageEx(_on_result)
        from .ibscan_types import IBSU_Events
        self._lib.IBSU_RegisterCallbacks(
            self._handle,
            IBSU_Events.RESULT_IMAGE_EX,
            ctypes.cast(self._cb_result_ex, ctypes.c_void_p),
            None,
        )

    def _register_cb_device_count(self) -> None:
        def _on_dc(count: int, ctx: int) -> None:
            try:
                if self.on_device_count:
                    self.on_device_count(count)
            except Exception:
                logger.exception("DeviceCount callback error")

        self._cb_device_count = IBSU_CallbackDeviceCount(_on_dc)
        from .ibscan_types import IBSU_Events
        self._lib.IBSU_RegisterCallbacks(
            self._handle,
            IBSU_Events.DEVICE_COUNT,
            ctypes.cast(self._cb_device_count, ctypes.c_void_p),
            None,
        )

    # ------------------------------------------------------------------
    # PAD / Spoof Detection
    # ------------------------------------------------------------------

    def is_spoof_supported(self) -> bool:
        try:
            val = self.get_property(IBSU_PropertyId.IS_SPOOF_SUPPORTED)
            return val.upper() == "TRUE"
        except IBScanError:
            return False

    def enable_spoof(self, enabled: bool = True) -> None:
        self.set_property(
            IBSU_PropertyId.ENABLE_SPOOF, "TRUE" if enabled else "FALSE",
        )
        if enabled:
            try:
                self.set_property(IBSU_PropertyId.DISABLE_SEGMENT_ROTATION, "TRUE")
            except IBScanError:
                pass

    def set_spoof_level(self, level: int = 3) -> None:
        clamped = max(1, min(5, level))
        self.set_property(IBSU_PropertyId.SPOOF_LEVEL, str(clamped))

    def is_spoof_finger_detected(self, image: IBSU_ImageData) -> bool:
        with self._lock:
            self._require_open()
            is_spoof = ctypes.c_int(0)
            rc = self._lib.IBSU_IsSpoofFingerDetected(
                self._handle, image, ctypes.byref(is_spoof),
            )
            if rc == IBSU_ERR_PAD_PROPERTY_DISABLED:
                logger.warning("PAD not enabled — call enable_spoof() first")
                return False
            if rc != IBSU_STATUS_OK:
                logger.warning("IsSpoofFingerDetected: %s", error_code_to_name(rc))
                return False
            return bool(is_spoof.value)

    def check_spoof_from_bytes(
        self, image_bytes: bytes, width: int, height: int,
    ) -> bool:
        """Build a temporary IBSU_ImageData and check spoof."""
        buf = (ctypes.c_ubyte * len(image_bytes)).from_buffer_copy(image_bytes)
        img = IBSU_ImageData()
        img.Buffer = ctypes.cast(buf, ctypes.c_void_p)
        img.Width = width
        img.Height = height
        img.BitsPerPixel = 8
        img.Format = 0  # GRAY
        img.Pitch = width
        img.IsFinal = 1
        return self.is_spoof_finger_detected(img)

    # ------------------------------------------------------------------
    # NFIQ2
    # ------------------------------------------------------------------

    def nfiq2_initialize(self) -> None:
        if self._nfiq2_lib is None:
            raise IBScanError("NFIQ2 library not loaded", -1)
        with self._lock:
            rc = self._nfiq2_lib.IBSU_NFIQ2_Initialize()
            if rc == IBSU_STATUS_OK or rc == 901:  # 901 = already initialized
                self._nfiq2_initialized = True
            else:
                raise IBScanError("NFIQ2_Initialize", rc)

    def nfiq2_is_initialized(self) -> bool:
        if self._nfiq2_lib is None:
            return False
        is_init = ctypes.c_int(0)
        self._nfiq2_lib.IBSU_NFIQ2_IsInitialized(ctypes.byref(is_init))
        return bool(is_init.value)

    def nfiq2_compute_score(
        self, image_buffer: bytes, width: int, height: int, bpp: int = 8,
    ) -> int:
        if self._nfiq2_lib is None:
            raise IBScanError("NFIQ2 library not loaded", -1)
        if not self._nfiq2_initialized:
            self.nfiq2_initialize()
        buf = (ctypes.c_ubyte * len(image_buffer)).from_buffer_copy(image_buffer)
        score = ctypes.c_int(0)
        with self._lock:
            _check(
                self._nfiq2_lib.IBSU_NFIQ2_ComputeScore(
                    buf, width, height, bpp, ctypes.byref(score),
                ),
                "NFIQ2_ComputeScore",
            )
        return score.value

    # ------------------------------------------------------------------
    # LED / Beeper
    # ------------------------------------------------------------------

    def set_leds(self, led_mask: int) -> None:
        with self._lock:
            self._require_open()
            _check(
                self._lib.IBSU_SetLEDs(self._handle, ctypes.c_ulong(led_mask)),
                "SetLEDs",
            )

    def get_leds(self) -> int:
        with self._lock:
            self._require_open()
            mask = ctypes.c_ulong(0)
            _check(
                self._lib.IBSU_GetLEDs(self._handle, ctypes.byref(mask)),
                "GetLEDs",
            )
            return mask.value

    def beeper_control(
        self,
        duration_ms: int = 100,
        pattern: int = 0,
        sound_tone: int = 0,
    ) -> None:
        with self._lock:
            self._require_open()
            rc = self._lib.IBSU_SetBeeper(
                self._handle, pattern, sound_tone, duration_ms, 0, 0,
            )
            if rc != IBSU_STATUS_OK:
                logger.debug("SetBeeper: %s", error_code_to_name(rc))

    # ------------------------------------------------------------------
    # Image export (to file)
    # ------------------------------------------------------------------

    def save_png(
        self, filepath: str, image_bytes: bytes,
        width: int, height: int, pitch: int = 0,
        res_x: float = 500.0, res_y: float = 500.0,
    ) -> None:
        if self._lib is None:
            raise IBScanError("Library not loaded", -1)
        buf = (ctypes.c_ubyte * len(image_bytes)).from_buffer_copy(image_bytes)
        _check(
            self._lib.IBSU_SavePngImage(
                filepath.encode("utf-8"), buf,
                width, height, pitch or width,
                ctypes.c_double(res_x), ctypes.c_double(res_y),
            ),
            "SavePngImage",
        )

    def save_wsq(
        self, filepath: str, image_bytes: bytes,
        width: int, height: int, pitch: int = 0,
        bpp: int = 8, bit_rate: float = 0.75,
    ) -> None:
        if self._lib is None:
            raise IBScanError("Library not loaded", -1)
        buf = (ctypes.c_ubyte * len(image_bytes)).from_buffer_copy(image_bytes)
        _check(
            self._lib.IBSU_WSQEncodeToFile(
                filepath.encode("utf-8"), buf,
                width, height, pitch or width,
                bpp, ctypes.c_double(bit_rate),
            ),
            "WSQEncodeToFile",
        )

    def save_jp2(
        self, filepath: str, image_bytes: bytes,
        width: int, height: int, pitch: int = 0,
        res_x: float = 500.0, res_y: float = 500.0,
    ) -> None:
        if self._lib is None:
            raise IBScanError("Library not loaded", -1)
        buf = (ctypes.c_ubyte * len(image_bytes)).from_buffer_copy(image_bytes)
        _check(
            self._lib.IBSU_SaveJP2Image(
                filepath.encode("utf-8"), buf,
                width, height, pitch or width,
                ctypes.c_double(res_x), ctypes.c_double(res_y),
            ),
            "SaveJP2Image",
        )

    # ------------------------------------------------------------------
    # Capture state
    # ------------------------------------------------------------------

    def is_capture_active(self) -> bool:
        with self._lock:
            self._require_open()
            active = ctypes.c_int(0)
            rc = self._lib.IBSU_IsCaptureActive(
                self._handle, ctypes.byref(active),
            )
            return rc == IBSU_STATUS_OK and active.value != 0

    def take_result_manually(self) -> None:
        with self._lock:
            self._require_open()
            _check(
                self._lib.IBSU_TakeResultImageManually(self._handle),
                "TakeResultImageManually",
            )

    # ------------------------------------------------------------------
    # Duplicate finger detection
    # ------------------------------------------------------------------

    def add_finger_image(
        self, image: IBSU_ImageData, finger_position: int,
        image_type: int = IBSU_ImageType.FLAT_SINGLE_FINGER,
    ) -> None:
        """Add a finger image to the internal duplicate-check gallery."""
        with self._lock:
            self._require_open()
            _check(
                self._lib.IBSU_AddFingerImage(
                    self._handle, image, finger_position, image_type,
                ),
                "AddFingerImage",
            )

    def remove_finger_image(self, finger_position: int) -> None:
        """Remove a finger image from the duplicate-check gallery."""
        with self._lock:
            self._require_open()
            _check(
                self._lib.IBSU_RemoveFingerImage(
                    self._handle, ctypes.c_ulong(finger_position),
                ),
                "RemoveFingerImage",
            )

    def is_finger_duplicated(
        self, image: IBSU_ImageData, finger_position: int,
        image_type: int = IBSU_ImageType.FLAT_SINGLE_FINGER,
    ) -> Tuple[bool, int]:
        """Check if finger image matches any previously added image.

        Returns:
            (is_duplicate, matched_position): True and the matched
            finger position if a duplicate is found.
        """
        with self._lock:
            self._require_open()
            matched = ctypes.c_int(0)
            rc = self._lib.IBSU_IsFingerDuplicated(
                self._handle, image, finger_position, image_type,
                ctypes.byref(matched),
            )
            if rc == IBSU_STATUS_OK:
                return False, 0
            if rc == IBSU_WRN_SPOOF_DETECTED:
                return False, 0
            # rc > 0 with matched position means duplicate found
            return matched.value != 0, matched.value

    def is_finger_duplicated_from_bytes(
        self, image_bytes: bytes, width: int, height: int,
        finger_position: int,
    ) -> Tuple[bool, int]:
        """Convenience: check duplicate from raw bytes."""
        buf = (ctypes.c_ubyte * len(image_bytes)).from_buffer_copy(image_bytes)
        img = IBSU_ImageData()
        img.Buffer = ctypes.cast(buf, ctypes.c_void_p)
        img.Width = width
        img.Height = height
        img.BitsPerPixel = 8
        img.Format = 0  # GRAY
        img.Pitch = width
        img.IsFinal = 1
        return self.is_finger_duplicated(img, finger_position)

    def add_finger_image_from_bytes(
        self, image_bytes: bytes, width: int, height: int,
        finger_position: int,
    ) -> None:
        """Convenience: add finger from raw bytes to duplicate gallery."""
        buf = (ctypes.c_ubyte * len(image_bytes)).from_buffer_copy(image_bytes)
        img = IBSU_ImageData()
        img.Buffer = ctypes.cast(buf, ctypes.c_void_p)
        img.Width = width
        img.Height = height
        img.BitsPerPixel = 8
        img.Format = 0
        img.Pitch = width
        img.IsFinal = 1
        self.add_finger_image(img, finger_position)

    def is_valid_finger_geometry(
        self, image: IBSU_ImageData, finger_position: int,
        image_type: int = IBSU_ImageType.FLAT_SINGLE_FINGER,
    ) -> bool:
        """Check if finger placement geometry is valid."""
        with self._lock:
            self._require_open()
            valid = ctypes.c_int(0)
            rc = self._lib.IBSU_IsValidFingerGeometry(
                self._handle, image, finger_position, image_type,
                ctypes.byref(valid),
            )
            return rc == IBSU_STATUS_OK and valid.value != 0

    # ------------------------------------------------------------------
    # Rolling info
    # ------------------------------------------------------------------

    def get_rolling_info(self) -> Tuple[int, int]:
        """Get rolling capture progress.

        Returns:
            (rolling_state, rolling_line_position)
        """
        with self._lock:
            self._require_open()
            state = ctypes.c_int(0)
            line = ctypes.c_int(0)
            _check(
                self._lib.IBSU_BGetRollingInfo(
                    self._handle, ctypes.byref(state), ctypes.byref(line),
                ),
                "BGetRollingInfo",
            )
            return state.value, line.value

    # ------------------------------------------------------------------
    # In-memory WSQ encode/decode
    # ------------------------------------------------------------------

    def wsq_encode_mem(
        self, image_bytes: bytes, width: int, height: int,
        ppi: int = 500, bit_rate: float = 0.75,
    ) -> bytes:
        """Encode image to WSQ format in memory (no temp file)."""
        with self._lock:
            if self._lib is None:
                raise IBScanError("Library not loaded", -1)
            buf = (ctypes.c_ubyte * len(image_bytes)).from_buffer_copy(image_bytes)
            out_ptr = ctypes.c_void_p()
            out_len = ctypes.c_uint(0)
            _check(
                self._lib.IBSU_WSQEncodeMem(
                    buf, width, height, width, 8, ppi,
                    ctypes.c_double(bit_rate),
                    ctypes.byref(out_ptr), ctypes.byref(out_len),
                ),
                "WSQEncodeMem",
            )
            result = ctypes.string_at(out_ptr, out_len.value)
            self._lib.IBSU_FreeMemory(out_ptr)
            return result

    def wsq_decode_mem(self, wsq_data: bytes) -> Tuple[bytes, int, int]:
        """Decode WSQ data in memory.

        Returns:
            (image_bytes, width, height)
        """
        with self._lock:
            if self._lib is None:
                raise IBScanError("Library not loaded", -1)
            wsq_buf = (ctypes.c_ubyte * len(wsq_data)).from_buffer_copy(wsq_data)
            out_img = ctypes.c_void_p()
            out_w = ctypes.c_uint(0)
            out_h = ctypes.c_uint(0)
            out_pitch = ctypes.c_int(0)
            out_bpp = ctypes.c_int(0)
            out_ppi = ctypes.c_int(0)
            _check(
                self._lib.IBSU_WSQDecodeMem(
                    wsq_buf, len(wsq_data),
                    ctypes.byref(out_img), ctypes.byref(out_w),
                    ctypes.byref(out_h), ctypes.byref(out_pitch),
                    ctypes.byref(out_bpp), ctypes.byref(out_ppi),
                ),
                "WSQDecodeMem",
            )
            nbytes = out_w.value * out_h.value * (out_bpp.value // 8)
            result = ctypes.string_at(out_img, nbytes)
            self._lib.IBSU_FreeMemory(out_img)
            return result, out_w.value, out_h.value

    # ------------------------------------------------------------------
    # ISO/ANSI template conversion
    # ------------------------------------------------------------------

    def convert_image_to_iso(
        self, image: IBSU_ImageData,
        finger_position: int = 0,
        standard_format: int = 0,  # 0 = ISO_19794_2_2005
    ) -> bytes:
        """Convert captured image to ISO/ANSI standard template."""
        with self._lock:
            self._require_open()
            out_ptr = ctypes.c_void_p()
            out_len = ctypes.c_uint(0)
            _check(
                self._lib.IBSU_ConvertImageToISOANSI(
                    self._handle, image, 1,
                    finger_position, standard_format,
                    ctypes.byref(out_ptr), ctypes.byref(out_len),
                ),
                "ConvertImageToISOANSI",
            )
            result = ctypes.string_at(out_ptr, out_len.value)
            self._lib.IBSU_FreeMemory(out_ptr)
            return result

    # ------------------------------------------------------------------
    # Contrast
    # ------------------------------------------------------------------

    def get_contrast(self) -> int:
        with self._lock:
            self._require_open()
            val = ctypes.c_int(0)
            _check(
                self._lib.IBSU_GetContrast(self._handle, ctypes.byref(val)),
                "GetContrast",
            )
            return val.value

    def set_contrast(self, value: int) -> None:
        with self._lock:
            self._require_open()
            _check(
                self._lib.IBSU_SetContrast(self._handle, value),
                "SetContrast",
            )

    # ------------------------------------------------------------------
    # Trace log
    # ------------------------------------------------------------------

    def enable_trace_log(self, enable: bool = True) -> None:
        if self._lib is None:
            return
        self._lib.IBSU_EnableTraceLog(1 if enable else 0)

    # ------------------------------------------------------------------
    # SDK version
    # ------------------------------------------------------------------

    def get_sdk_version(self) -> str:
        if self._lib is None:
            return "N/A"
        buf = (ctypes.c_char * IBSU_MAX_STR_LEN)()
        rc = self._lib.IBSU_GetSDKVersion(ctypes.byref(buf))
        if rc != IBSU_STATUS_OK:
            return "N/A"
        return buf.value.decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Error string
    # ------------------------------------------------------------------

    def get_error_string(self, code: int) -> str:
        if self._lib is None:
            return error_code_to_name(code)
        buf = (ctypes.c_char * IBSU_MAX_STR_LEN)()
        self._lib.IBSU_GetErrorString(code, buf)
        return buf.value.decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "IBScanUltimateDriver":
        return self

    def __exit__(self, *args: object) -> None:
        self.close_device()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_open(self) -> None:
        if not self._is_open or self._lib is None:
            raise IBScanError("Device not open", IBSU_ERR_DEVICE_NOT_FOUND)


# ---------------------------------------------------------------------------
# High-level adapter implementing SensorDriver ABC
# ---------------------------------------------------------------------------

class IBScanSensorDriver(SensorDriver):
    """SensorDriver implementation wrapping IBScanUltimateDriver.

    Provides the standard SensorDriver interface for backward
    compatibility, plus extended IBScanUltimate features through
    additional public methods.
    """

    def __init__(
        self,
        lib_path: Optional[str] = None,
        nfiq2_lib_path: Optional[str] = None,
    ):
        self._driver = IBScanUltimateDriver(lib_path, nfiq2_lib_path)
        self._lock = threading.Lock()
        self._logger = logging.getLogger("IBScanSensorDriver")
        self._last_capture: Optional[IBScanCaptureResult] = None
        self._capture_event = threading.Event()
        self._capture_result_data: Optional[tuple] = None

    # --- SensorDriver ABC implementation ---

    def open(self) -> bool:
        try:
            if self._driver._lib is None:
                self._logger.warning(
                    "IBScan runtime not loaded; install libIBScanUltimate.so for the target architecture"
                )
                return False
            count = self._driver.get_device_count()
            if count <= 0:
                self._logger.warning("No IBScan devices found")
                return False
            self._driver.open_device(0)
            self._driver.on_result = self._on_capture_result
            self._driver.register_callbacks()
            return True
        except IBScanError as exc:
            self._logger.error("Failed to open IBScan device: %s", exc)
            return False

    def close(self) -> None:
        try:
            self._driver.close_device()
        except IBScanError:
            pass

    def is_connected(self) -> bool:
        return self._driver.is_open

    def capture_image(self) -> CaptureResult:
        """Blocking single-finger capture — returns as soon as result ready.

        Used for verify/identify where speed matters.
        """
        return self._do_capture(timeout=15.0)

    def capture_image_for_enroll(
        self,
        capture_duration: float = 4.0,
        image_type: int = IBSU_ImageType.FLAT_SINGLE_FINGER,
        resolution: int = IBSU_ImageResolution.RESOLUTION_500,
    ) -> IBScanCaptureResult:
        """Blocking capture optimised for enrollment.

        Waits *capture_duration* seconds (3-5s recommended) to allow the
        sensor to collect the best possible image with full finger area
        coverage.  Auto-capture is disabled so the SDK keeps refining
        until we manually take the result.

        Returns:
            IBScanCaptureResult with segments and quality info.
        """
        if not self._driver.is_open:
            return IBScanCaptureResult(success=False, error="Device not open")
        try:
            self._capture_event.clear()
            self._capture_result_data = None

            # Disable auto-capture so sensor keeps scanning for *duration*
            options = IBSU_OPTION_AUTO_CONTRAST  # no AUTO_CAPTURE
            self._driver.begin_capture(image_type, resolution, options)

            # Let sensor collect for the full duration
            import time
            time.sleep(capture_duration)

            # Now manually trigger result capture
            try:
                self._driver.take_result_manually()
            except IBScanError:
                pass  # May already have result if finger was lifted

            # Wait for the result callback
            if not self._capture_event.wait(timeout=5.0):
                self._driver.cancel_capture()
                return IBScanCaptureResult(success=False, error="Capture timeout after enrollment wait")

            data = self._capture_result_data
            if data is None:
                return IBScanCaptureResult(success=False, error="No capture data")

            status, img_bytes, width, height, segments, finger_count = data
            quality = _calculate_quality_fast(img_bytes)

            seg_qualities = []
            for seg_img in segments:
                seg_qualities.append(
                    int(_calculate_quality_fast(seg_img))
                )

            return IBScanCaptureResult(
                success=True,
                image_data=img_bytes,
                width=width,
                height=height,
                resolution=float(resolution),
                quality_score=quality,
                finger_count=finger_count,
                segment_images=segments,
                segment_qualities=tuple(seg_qualities),
            )
        except IBScanError as exc:
            return IBScanCaptureResult(success=False, error=str(exc))

    def check_finger(self) -> bool:
        return self._driver.is_open

    def get_info(self) -> SensorInfo:
        try:
            desc = self._driver.get_device_description(0)
            width_str = self._driver.get_property(IBSU_PropertyId.IMAGE_WIDTH)
            height_str = self._driver.get_property(IBSU_PropertyId.IMAGE_HEIGHT)
            return SensorInfo(
                vendor_id=0x113F,  # Integrated Biometrics
                product_id=0,
                name=desc.product_name,
                resolution_dpi=500,
                image_width=int(width_str) if width_str.isdigit() else 0,
                image_height=int(height_str) if height_str.isdigit() else 0,
                firmware_version=desc.firmware_version,
                serial_number=desc.serial_number,
            )
        except IBScanError:
            return SensorInfo(
                vendor_id=0x113F, product_id=0,
                name="IBScan (info unavailable)",
                resolution_dpi=500, image_width=0, image_height=0,
            )

    def led_on(self, color: int) -> bool:
        from .ibscan_types import IBSU_LED_SCAN_GREEN, IBSU_LED_INIT_BLUE
        led_map = {
            LEDColor.GREEN: IBSU_LED_SCAN_GREEN,
            LEDColor.BLUE: IBSU_LED_INIT_BLUE,
            LEDColor.RED: 0x00000004,
            LEDColor.WHITE: IBSU_LED_SCAN_GREEN | IBSU_LED_INIT_BLUE,
        }
        mask = led_map.get(color, IBSU_LED_SCAN_GREEN)
        try:
            self._driver.set_leds(mask)
            return True
        except IBScanError:
            return False

    def led_off(self) -> bool:
        try:
            self._driver.set_leds(0)
            return True
        except IBScanError:
            return False

    def beep(self, duration_ms: int = 100) -> bool:
        try:
            self._driver.beeper_control(duration_ms)
            return True
        except IBScanError:
            return False

    # --- Duplicate detection for enrollment ---

    def check_duplicate_finger(
        self, image_bytes: bytes, width: int, height: int,
        finger_position: int,
    ) -> Tuple[bool, int]:
        """Check if this finger was already enrolled (anti-duplicate).

        Args:
            image_bytes: Raw grayscale image.
            width, height: Image dimensions.
            finger_position: Finger position bitmask.

        Returns:
            (is_duplicate, matched_position): True if finger matches
            a previously added image.
        """
        return self._driver.is_finger_duplicated_from_bytes(
            image_bytes, width, height, finger_position,
        )

    def register_enrolled_finger(
        self, image_bytes: bytes, width: int, height: int,
        finger_position: int,
    ) -> None:
        """Add finger to the SDK's internal duplicate-check gallery.

        Call this after successful enrollment so future enrollments
        can detect duplicates.
        """
        self._driver.add_finger_image_from_bytes(
            image_bytes, width, height, finger_position,
        )

    def clear_enrolled_finger(self, finger_position: int) -> None:
        """Remove finger from duplicate-check gallery."""
        try:
            self._driver.remove_finger_image(finger_position)
        except IBScanError:
            pass

    # --- Extended IBScanUltimate features ---

    @property
    def driver(self) -> IBScanUltimateDriver:
        """Access underlying low-level driver for advanced operations."""
        return self._driver

    @property
    def supports_spoof_detection(self) -> bool:
        return self._driver.is_spoof_supported()

    @property
    def supports_nfiq2(self) -> bool:
        return self._driver._nfiq2_lib is not None

    @property
    def supports_multi_finger(self) -> bool:
        return True

    def begin_capture_async(
        self,
        image_type: int = IBSU_ImageType.FLAT_SINGLE_FINGER,
        resolution: int = IBSU_ImageResolution.RESOLUTION_500,
        options: int = IBSU_OPTION_AUTO_CONTRAST | IBSU_OPTION_AUTO_CAPTURE,
    ) -> None:
        self._capture_event.clear()
        self._capture_result_data = None
        self._driver.begin_capture(image_type, resolution, options)

    def cancel_capture_async(self) -> None:
        self._driver.cancel_capture()

    def get_nfiq2_score(self, image_data: bytes, width: int, height: int) -> int:
        return self._driver.nfiq2_compute_score(image_data, width, height)

    def is_spoof_detected(self, image_data: bytes, width: int, height: int) -> bool:
        return self._driver.check_spoof_from_bytes(image_data, width, height)

    def enable_spoof_detection(self, enabled: bool) -> None:
        self._driver.enable_spoof(enabled)

    def set_spoof_level(self, level: int) -> None:
        self._driver.set_spoof_level(level)

    def get_device_description(self) -> dict:
        try:
            info = self._driver.get_device_description(0)
            return {
                "product_name": info.product_name,
                "serial_number": info.serial_number,
                "interface_type": info.interface_type,
                "firmware_version": info.firmware_version,
                "revision": info.revision,
                "is_locked": info.is_locked,
            }
        except IBScanError:
            return {"product_name": "Unknown", "serial_number": "N/A"}

    def export_image(
        self, image_data: bytes, width: int, height: int, format: str = "png",
    ) -> str:
        """Export to temp file and return path. Caller responsible for cleanup."""
        import tempfile
        ext = {"png": ".png", "wsq": ".wsq", "jp2": ".jp2", "bmp": ".bmp"}
        suffix = ext.get(format, ".png")
        fd, path = tempfile.mkstemp(suffix=suffix)
        import os
        os.close(fd)
        if format == "wsq":
            self._driver.save_wsq(path, image_data, width, height)
        elif format == "jp2":
            self._driver.save_jp2(path, image_data, width, height)
        else:
            self._driver.save_png(path, image_data, width, height)
        return path

    def wsq_encode_mem(
        self, image_bytes: bytes, width: int, height: int,
    ) -> bytes:
        """Encode image to WSQ in memory (no temp file)."""
        return self._driver.wsq_encode_mem(image_bytes, width, height)

    def wsq_decode_mem(self, wsq_data: bytes) -> Tuple[bytes, int, int]:
        """Decode WSQ data from memory. Returns (image_bytes, width, height)."""
        return self._driver.wsq_decode_mem(wsq_data)

    def convert_to_iso_template(
        self, image_bytes: bytes, width: int, height: int,
        finger_position: int = 0,
        standard_format: int = 0,
    ) -> bytes:
        """Convert captured image to ISO/ANSI template bytes."""
        buf = (ctypes.c_ubyte * len(image_bytes)).from_buffer_copy(image_bytes)
        img = IBSU_ImageData()
        img.Buffer = ctypes.cast(buf, ctypes.c_void_p)
        img.Width = width
        img.Height = height
        img.BitsPerPixel = 8
        img.Format = 0
        img.Pitch = width
        img.IsFinal = 1
        return self._driver.convert_image_to_iso(
            img, finger_position, standard_format,
        )

    def is_capture_active(self) -> bool:
        """Check if a capture is currently running."""
        return self._driver.is_capture_active()

    def get_rolling_info(self) -> Tuple[int, int]:
        """Get rolling capture state and line position."""
        return self._driver.get_rolling_info()

    # --- Internal ---

    def _do_capture(self, timeout: float = 15.0) -> CaptureResult:
        """Core capture logic — immediate result (for verify/identify)."""
        if not self._driver.is_open:
            return CaptureResult(success=False, error="Device not open")
        try:
            self._capture_event.clear()
            self._capture_result_data = None
            self._driver.begin_capture(
                IBSU_ImageType.FLAT_SINGLE_FINGER,
                IBSU_ImageResolution.RESOLUTION_500,
                IBSU_OPTION_AUTO_CONTRAST | IBSU_OPTION_AUTO_CAPTURE,
            )
            if not self._capture_event.wait(timeout=timeout):
                self._driver.cancel_capture()
                return CaptureResult(success=False, error="Capture timeout")

            data = self._capture_result_data
            if data is None:
                return CaptureResult(success=False, error="No capture data")

            status, img_bytes, width, height, segments, finger_count = data
            quality = _calculate_quality_fast(img_bytes)
            return CaptureResult(
                success=True,
                image_data=img_bytes,
                width=width,
                height=height,
                quality_score=quality,
                has_finger=finger_count > 0,
            )
        except IBScanError as exc:
            return CaptureResult(success=False, error=str(exc))

    def _on_capture_result(
        self, status: int, img_bytes: bytes,
        width: int, height: int,
        segments: tuple, finger_count: int,
    ) -> None:
        self._capture_result_data = (
            status, img_bytes, width, height, segments, finger_count,
        )
        self._capture_event.set()


def _calculate_quality_fast(image: bytes) -> float:
    """Fast quality metric using numpy if available, fallback to pure Python."""
    if not image or len(image) < 1000:
        return 0.0
    try:
        import numpy as np
        arr = np.frombuffer(image, dtype=np.uint8)
        return float(arr.std())
    except ImportError:
        avg = sum(image) / len(image)
        variance = sum((x - avg) ** 2 for x in image) / len(image)
        return variance ** 0.5
