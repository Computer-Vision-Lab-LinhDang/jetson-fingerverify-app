"""IBScanUltimate SDK ctypes type definitions for Python.

Maps all C structures, enums, constants, and callback types from the
IBScanUltimate v4.3.0 SDK headers to Python ctypes equivalents.

References:
    IBScanUltimateApi_defs.h  -- structures, enums, constants, callbacks
    IBScanUltimateApi_err.h   -- error and warning codes
    IBScanUltimate.h          -- IBSU_ImageData, IBSU_ImageFormat
    IBScanNFIQ2Api.h          -- NFIQ2 functions
    IBScanNFIQ2Api_err.h      -- NFIQ2 error codes
"""
import ctypes
from ctypes import (
    Structure, POINTER, CFUNCTYPE,
    c_int, c_uint, c_char, c_char_p, c_byte, c_ubyte,
    c_void_p, c_double, c_bool, c_ulong, c_short, c_ushort,
)
from enum import IntEnum


# ---------------------------------------------------------------------------
# General constants  (IBScanUltimateApi_defs.h)
# ---------------------------------------------------------------------------
IBSU_MAX_STR_LEN = 128
IBSU_MIN_CONTRAST_VALUE = 0
IBSU_MAX_CONTRAST_VALUE = 34
IBSU_MAX_SEGMENT_COUNT = 5
IBSU_MAX_SEGMENT_QUALITY_COUNT = 4
IBSU_BMP_GRAY_HEADER_LEN = 1078
IBSU_BMP_RGB24_HEADER_LEN = 54
IBSU_BMP_RGB32_HEADER_LEN = 54
IBSU_MAX_MINUTIAE_SIZE = 257  # (255 + 2)

# Capture options (bit-flags for IBSU_BeginCaptureImage)
IBSU_OPTION_AUTO_CONTRAST = 1
IBSU_OPTION_AUTO_CAPTURE = 2
IBSU_OPTION_IGNORE_FINGER_COUNT = 4

# Parallel string length for AlcorLink properties
PARALLEL_MAX_STR_LEN = 32


# ---------------------------------------------------------------------------
# LED bit definitions  (IBScanUltimateApi_defs.h)
# ---------------------------------------------------------------------------
IBSU_LED_NONE = 0x00000000
IBSU_LED_ALL = 0xFFFFFFFF
IBSU_LED_INIT_BLUE = 0x00000001
IBSU_LED_SCAN_GREEN = 0x00000002
IBSU_LED_SCAN_CURVE_RED = 0x00000010
IBSU_LED_SCAN_CURVE_GREEN = 0x00000020
IBSU_LED_SCAN_CURVE_BLUE = 0x00000040

# LED definitions for 4-finger scanners (Kojak / FSCAN)
IBSU_LED_F_BLINK_GREEN = 0x10000000
IBSU_LED_F_BLINK_RED = 0x20000000
IBSU_LED_F_LEFT_LITTLE_GREEN = 0x01000000
IBSU_LED_F_LEFT_LITTLE_RED = 0x02000000
IBSU_LED_F_LEFT_RING_GREEN = 0x04000000
IBSU_LED_F_LEFT_RING_RED = 0x08000000
IBSU_LED_F_LEFT_MIDDLE_GREEN = 0x00100000
IBSU_LED_F_LEFT_MIDDLE_RED = 0x00200000
IBSU_LED_F_LEFT_INDEX_GREEN = 0x00400000
IBSU_LED_F_LEFT_INDEX_RED = 0x00800000
IBSU_LED_F_LEFT_THUMB_GREEN = 0x00010000
IBSU_LED_F_LEFT_THUMB_RED = 0x00020000
IBSU_LED_F_RIGHT_THUMB_GREEN = 0x00040000
IBSU_LED_F_RIGHT_THUMB_RED = 0x00080000
IBSU_LED_F_RIGHT_INDEX_GREEN = 0x00001000
IBSU_LED_F_RIGHT_INDEX_RED = 0x00002000
IBSU_LED_F_RIGHT_MIDDLE_GREEN = 0x00004000
IBSU_LED_F_RIGHT_MIDDLE_RED = 0x40000000
IBSU_LED_F_RIGHT_RING_GREEN = 0x00000100
IBSU_LED_F_RIGHT_RING_RED = 0x00000200
IBSU_LED_F_RIGHT_LITTLE_GREEN = 0x00000400
IBSU_LED_F_RIGHT_LITTLE_RED = 0x00000800
IBSU_LED_F_PROGRESS_ROLL = 0x00000010
IBSU_LED_F_PROGRESS_LEFT_HAND = 0x00000020
IBSU_LED_F_PROGRESS_TWO_THUMB = 0x00000040
IBSU_LED_F_PROGRESS_RIGHT_HAND = 0x00000080


# ---------------------------------------------------------------------------
# Finger bit-masks  (IBScanUltimateApi_defs.h)
# ---------------------------------------------------------------------------
IBSU_FINGER_NONE = 0x00000000
IBSU_FINGER_LEFT_LITTLE = 0x00000001
IBSU_FINGER_LEFT_RING = 0x00000002
IBSU_FINGER_LEFT_MIDDLE = 0x00000004
IBSU_FINGER_LEFT_INDEX = 0x00000008
IBSU_FINGER_LEFT_THUMB = 0x00000010
IBSU_FINGER_RIGHT_THUMB = 0x00000020
IBSU_FINGER_RIGHT_INDEX = 0x00000040
IBSU_FINGER_RIGHT_MIDDLE = 0x00000080
IBSU_FINGER_RIGHT_RING = 0x00000100
IBSU_FINGER_RIGHT_LITTLE = 0x00000200
IBSU_FINGER_LEFT_HAND = (
    IBSU_FINGER_LEFT_INDEX | IBSU_FINGER_LEFT_MIDDLE
    | IBSU_FINGER_LEFT_RING | IBSU_FINGER_LEFT_LITTLE
)
IBSU_FINGER_RIGHT_HAND = (
    IBSU_FINGER_RIGHT_INDEX | IBSU_FINGER_RIGHT_MIDDLE
    | IBSU_FINGER_RIGHT_RING | IBSU_FINGER_RIGHT_LITTLE
)
IBSU_FINGER_BOTH_THUMBS = IBSU_FINGER_RIGHT_THUMB | IBSU_FINGER_LEFT_THUMB
IBSU_FINGER_ALL = (
    IBSU_FINGER_LEFT_HAND | IBSU_FINGER_RIGHT_HAND | IBSU_FINGER_BOTH_THUMBS
)
IBSU_FINGER_LEFT_LITTLE_RING = IBSU_FINGER_LEFT_LITTLE | IBSU_FINGER_LEFT_RING
IBSU_FINGER_LEFT_MIDDLE_INDEX = IBSU_FINGER_LEFT_MIDDLE | IBSU_FINGER_LEFT_INDEX
IBSU_FINGER_RIGHT_INDEX_MIDDLE = IBSU_FINGER_RIGHT_INDEX | IBSU_FINGER_RIGHT_MIDDLE
IBSU_FINGER_RIGHT_RING_LITTLE = IBSU_FINGER_RIGHT_RING | IBSU_FINGER_RIGHT_LITTLE


# ---------------------------------------------------------------------------
# Error codes  (IBScanUltimateApi_err.h)
# ---------------------------------------------------------------------------
# General (0 to -11)
IBSU_STATUS_OK = 0
IBSU_ERR_INVALID_PARAM_VALUE = -1
IBSU_ERR_MEM_ALLOC = -2
IBSU_ERR_NOT_SUPPORTED = -3
IBSU_ERR_FILE_OPEN = -4
IBSU_ERR_FILE_READ = -5
IBSU_ERR_RESOURCE_LOCKED = -6
IBSU_ERR_MISSING_RESOURCE = -7
IBSU_ERR_INVALID_ACCESS_POINTER = -8
IBSU_ERR_THREAD_CREATE = -9
IBSU_ERR_COMMAND_FAILED = -10
IBSU_ERR_LIBRARY_UNLOAD_FAILED = -11

# Low-level I/O (-100 to -107)
IBSU_ERR_CHANNEL_IO_COMMAND_FAILED = -100
IBSU_ERR_CHANNEL_IO_READ_FAILED = -101
IBSU_ERR_CHANNEL_IO_WRITE_FAILED = -102
IBSU_ERR_CHANNEL_IO_READ_TIMEOUT = -103
IBSU_ERR_CHANNEL_IO_WRITE_TIMEOUT = -104
IBSU_ERR_CHANNEL_IO_UNEXPECTED_FAILED = -105
IBSU_ERR_CHANNEL_IO_INVALID_HANDLE = -106
IBSU_ERR_CHANNEL_IO_WRONG_PIPE_INDEX = -107

# Device-related (-200 to -222)
IBSU_ERR_DEVICE_IO = -200
IBSU_ERR_DEVICE_NOT_FOUND = -201
IBSU_ERR_DEVICE_NOT_MATCHED = -202
IBSU_ERR_DEVICE_ACTIVE = -203
IBSU_ERR_DEVICE_NOT_INITIALIZED = -204
IBSU_ERR_DEVICE_INVALID_STATE = -205
IBSU_ERR_DEVICE_BUSY = -206
IBSU_ERR_DEVICE_NOT_SUPPORTED_FEATURE = -207
IBSU_ERR_INVALID_LICENSE = -208
IBSU_ERR_USB20_REQUIRED = -209
IBSU_ERR_DEVICE_ENABLED_POWER_SAVE_MODE = -210
IBSU_ERR_DEVICE_NEED_UPDATE_FIRMWARE = -211
IBSU_ERR_DEVICE_NEED_CALIBRATE_TOF = -212
IBSU_ERR_DEVICE_INVALID_CALIBRATION_DATA = -213
IBSU_ERR_DEVICE_HIGHER_SDK_REQUIRED = -214
IBSU_ERR_DEVICE_LOCK_INVALID_BUFF = -215
IBSU_ERR_DEVICE_LOCK_INFO_EMPTY = -216
IBSU_ERR_DEVICE_LOCK_INFO_NOT_MATCHED = -217
IBSU_ERR_DEVICE_LOCK_INVALID_CHECKSUM = -218
IBSU_ERR_DEVICE_LOCK_INVALID_KEY = -219
IBSU_ERR_DEVICE_LOCK_LOCKED = -220
IBSU_ERR_DEVICE_LOCK_ILLEGAL_DEVICE = -221
IBSU_ERR_DEVICE_LOCK_INVALID_SERIAL_FORMAT = -222

# Image capture (-300 to -308)
IBSU_ERR_CAPTURE_COMMAND_FAILED = -300
IBSU_ERR_CAPTURE_STOP = -301
IBSU_ERR_CAPTURE_TIMEOUT = -302
IBSU_ERR_CAPTURE_STILL_RUNNING = -303
IBSU_ERR_CAPTURE_NOT_RUNNING = -304
IBSU_ERR_CAPTURE_INVALID_MODE = -305
IBSU_ERR_CAPTURE_ALGORITHM = -306
IBSU_ERR_CAPTURE_ROLLING = -307
IBSU_ERR_CAPTURE_ROLLING_TIMEOUT = -308

# Client window (-400 to -402)
IBSU_ERR_CLIENT_WINDOW = -400
IBSU_ERR_CLIENT_WINDOW_NOT_CREATE = -401
IBSU_ERR_INVALID_OVERLAY_HANDLE = -402

# NBIS (-500 to -504)
IBSU_ERR_NBIS_NFIQ_FAILED = -500
IBSU_ERR_NBIS_WSQ_ENCODE_FAILED = -501
IBSU_ERR_NBIS_WSQ_DECODE_FAILED = -502
IBSU_ERR_NBIS_PNG_ENCODE_FAILED = -503
IBSU_ERR_NBIS_JP2_ENCODE_FAILED = -504

# Matcher (-600 to -603)
IBSU_ERR_DUPLICATE_EXTRACTION_FAILED = -600
IBSU_ERR_DUPLICATE_ALREADY_USED = -601
IBSU_ERR_DUPLICATE_SEGMENTATION_FAILED = -602
IBSU_ERR_DUPLICATE_MATCHING_FAILED = -603

# PAD (-700)
IBSU_ERR_PAD_PROPERTY_DISABLED = -700

# ISO/ANSI (-800)
IBSU_ERR_INCORRECT_STANDARD_FORMAT = -800


# ---------------------------------------------------------------------------
# Warning codes  (IBScanUltimateApi_err.h)
# ---------------------------------------------------------------------------
IBSU_WRN_CHANNEL_IO_FRAME_MISSING = 100
IBSU_WRN_CHANNEL_IO_CAMERA_WRONG = 101
IBSU_WRN_CHANNEL_IO_SLEEP_STATUS = 102
IBSU_WRN_OUTDATED_FIRMWARE = 200
IBSU_WRN_ALREADY_INITIALIZED = 201
IBSU_WRN_API_DEPRECATED = 202
IBSU_WRN_ALREADY_ENHANCED_IMAGE = 203
IBSU_WRN_BGET_IMAGE = 300
IBSU_WRN_ROLLING_NOT_RUNNING = 301
IBSU_WRN_NO_FINGER = 302
IBSU_WRN_INCORRECT_FINGERS = 303
IBSU_WRN_ROLLING_SMEAR = 304
IBSU_WRN_ROLLING_SHIFTED_HORIZONTALLY = IBSU_WRN_ROLLING_SMEAR | 1  # 305
IBSU_WRN_ROLLING_SHIFTED_VERTICALLY = IBSU_WRN_ROLLING_SMEAR | 2  # 306
IBSU_WRN_EMPTY_IBSM_RESULT_IMAGE = 400
IBSU_WRN_QUALITY_INVALID_AREA = 512
IBSU_WRN_QUALITY_INVALID_AREA_HORIZONTALLY = IBSU_WRN_QUALITY_INVALID_AREA | 1  # 513
IBSU_WRN_QUALITY_INVALID_AREA_VERTICALLY = IBSU_WRN_QUALITY_INVALID_AREA | 2  # 514
IBSU_WRN_INVALID_BRIGHTNESS_FINGERS = 600
IBSU_WRN_WET_FINGERS = 601
IBSU_WRN_MULTIPLE_FINGERS_DURING_ROLL = 602
IBSU_WRN_SPOOF_DETECTED = 603
IBSU_WRN_ROLLING_SLIP_DETECTED = 604
IBSU_WRN_SPOOF_INIT_FAILED = 605
IBSU_WRN_MATCHER_NO_MATCH = 700
IBSU_WRN_MATCHER_ALREADY_REGISTERED = 701


# ---------------------------------------------------------------------------
# NFIQ2 error / warning codes  (IBScanNFIQ2Api_err.h)
# ---------------------------------------------------------------------------
IBSU_NFIQ2_STATUS_OK = 0
IBSU_ERR_NFIQ2_INVALID_PARAM_VALUE = -1
IBSU_ERR_NFIQ2_MEM_ALLOC = -2
IBSU_ERR_NFIQ2_NOT_SUPPORTED = -3
IBSU_ERR_NFIQ2_FILE_OPEN = -4
IBSU_ERR_NFIQ2_FILE_READ = -5
IBSU_ERR_NFIQ2_RESOURCE_LOCKED = -6
IBSU_ERR_NFIQ2_MISSING_RESOURCE = -7
IBSU_ERR_NFIQ2_INVALID_ACCESS_POINTER = -8
IBSU_ERR_NFIQ2_THREAD_CREATE = -9
IBSU_ERR_NFIQ2_COMMAND_FAILED = -10
IBSU_ERR_NFIQ2_LIBRARY_UNLOAD_FAILED = -11
IBSU_ERR_NFIQ2_NOT_INITIALIZED = -900
IBSU_ERR_NFIQ2_FAILED = -901
IBSU_WRN_NFIQ2_ALREADY_INITIALIZED = 901
IBSU_WRN_NFIQ2_API_DEPRECATED = 902


# ---------------------------------------------------------------------------
# Enumerations  (IBScanUltimate.h / IBScanUltimateApi_defs.h)
# ---------------------------------------------------------------------------

class IBSU_ImageFormat(IntEnum):
    """IBSU_ImageFormat -- image colour formats."""
    GRAY = 0
    RGB24 = 1
    RGB32 = 2
    UNKNOWN = 3


class IBSU_ImageType(IntEnum):
    """IBSU_ImageType -- capture image types."""
    TYPE_NONE = 0
    ROLL_SINGLE_FINGER = 1
    FLAT_SINGLE_FINGER = 2
    FLAT_TWO_FINGERS = 3
    FLAT_FOUR_FINGERS = 4
    FLAT_THREE_FINGERS = 5
    FLAT_SINGLE_WRITERS_PALM = 6
    FLAT_SINGLE_UPPER_PALM = 7
    FLAT_SINGLE_LOWER_PALM = 8


class IBSU_ImageResolution(IntEnum):
    """IBSU_ImageResolution -- capture resolutions (pixels per inch)."""
    RESOLUTION_500 = 500
    RESOLUTION_1000 = 1000


class IBSU_FingerCountState(IntEnum):
    """IBSU_FingerCountState -- finger count states."""
    FINGER_COUNT_OK = 0
    TOO_MANY_FINGERS = 1
    TOO_FEW_FINGERS = 2
    NON_FINGER = 3


class IBSU_FingerQualityState(IntEnum):
    """IBSU_FingerQualityState -- finger quality states."""
    FINGER_NOT_PRESENT = 0
    QUALITY_GOOD = 1
    QUALITY_FAIR = 2
    QUALITY_POOR = 3
    INVALID_AREA_TOP = 4
    INVALID_AREA_LEFT = 5
    INVALID_AREA_RIGHT = 6
    INVALID_AREA_BOTTOM = 7


class IBSU_LEOperationMode(IntEnum):
    """IBSU_LEOperationMode -- LE film operation modes."""
    AUTO = 0
    ON = 1
    OFF = 2


class IBSU_PlatenState(IntEnum):
    """IBSU_PlatenState -- platen states."""
    CLEARED = 0
    HAS_FINGERS = 1


class IBSU_RollingState(IntEnum):
    """IBSU_RollingState -- rolling capture states."""
    NOT_PRESENT = 0
    TAKE_ACQUISITION = 1
    COMPLETE_ACQUISITION = 2
    RESULT_IMAGE = 3


class IBSU_LedType(IntEnum):
    """IBSU_LedType -- LED hardware types."""
    NONE = 0
    TSCAN = 1
    FSCAN = 2


class IBSU_BeeperType(IntEnum):
    """IBSU_BeeperType -- beeper hardware types."""
    NONE = 0
    MONOTONE = 1


class IBSU_BeepPattern(IntEnum):
    """IBSU_BeepPattern -- beep patterns."""
    GENERIC = 0
    REPEAT = 1


class IBSU_EncryptionMode(IntEnum):
    """IBSU_EncryptionMode -- encryption key modes."""
    RANDOM = 0
    CUSTOM = 1
    DEFAULT = 2


class IBSU_OverlayShapePattern(IntEnum):
    """IBSU_OverlayShapePattern -- overlay shape patterns."""
    RECTANGLE = 0
    ELLIPSE = 1
    CROSS = 2
    ARROW = 3


class IBSU_CombineImageWhichHand(IntEnum):
    """IBSU_CombineImageWhichHand -- hand selection for combined images."""
    LEFT_HAND = 0
    RIGHT_HAND = 1


class IBSU_HashType(IntEnum):
    """IBSU_HashType -- hash types for customer key."""
    SHA256 = 0
    RESERVED = 1


class IBSU_Events(IntEnum):
    """IBSU_Events -- callback event types."""
    DEVICE_COUNT = 0
    COMMUNICATION_BREAK = 1
    PREVIEW_IMAGE = 2
    TAKING_ACQUISITION = 3
    COMPLETE_ACQUISITION = 4
    RESULT_IMAGE = 5
    FINGER_QUALITY = 6
    FINGER_COUNT = 7
    INIT_PROGRESS = 8
    CLEAR_PLATEN_AT_CAPTURE = 9
    ASYNC_OPEN_DEVICE = 10
    NOTIFY_MESSAGE = 11
    RESULT_IMAGE_EX = 12
    KEYBUTTON = 13


class IBSU_PropertyId(IntEnum):
    """IBSU_PropertyId -- device property identifiers.

    Values match the C enum IBSU_PropertyId exactly.
    """
    PRODUCT_ID = 0
    SERIAL_NUMBER = 1
    VENDOR_ID = 2
    IBIA_VENDOR_ID = 3
    IBIA_VERSION = 4
    IBIA_DEVICE_ID = 5
    FIRMWARE = 6
    REVISION = 7
    PRODUCTION_DATE = 8
    SERVICE_DATE = 9
    IMAGE_WIDTH = 10
    IMAGE_HEIGHT = 11
    IGNORE_FINGER_TIME = 12
    RECOMMENDED_LEVEL = 13
    POLLINGTIME_TO_BGETIMAGE = 14
    ENABLE_POWER_SAVE_MODE = 15
    RETRY_WRONG_COMMUNICATION = 16
    CAPTURE_TIMEOUT = 17
    ROLL_MIN_WIDTH = 18
    ROLL_MODE = 19
    ROLL_LEVEL = 20
    CAPTURE_AREA_THRESHOLD = 21
    ENABLE_DECIMATION = 22
    ENABLE_CAPTURE_ON_RELEASE = 23
    DEVICE_INDEX = 24
    DEVICE_ID = 25
    SUPER_DRY_MODE = 26
    MIN_CAPTURE_TIME_IN_SUPER_DRY_MODE = 27
    ROLLED_IMAGE_WIDTH = 28
    ROLLED_IMAGE_HEIGHT = 29
    NO_PREVIEW_IMAGE = 30
    ROLL_IMAGE_OVERRIDE = 31
    WARNING_MESSAGE_INVALID_AREA = 32
    ENABLE_WET_FINGER_DETECT = 33
    WET_FINGER_DETECT_LEVEL = 34
    WET_FINGER_DETECT_LEVEL_THRESHOLD = 35
    START_POSITION_OF_ROLLING_AREA = 36
    START_ROLL_WITHOUT_LOCK = 37
    ENABLE_TOF = 38
    ENABLE_ENCRYPTION = 39
    IS_SPOOF_SUPPORTED = 40
    ENABLE_SPOOF = 41
    SPOOF_LEVEL = 42
    VIEW_ENCRYPTION_IMAGE_MODE = 43
    FINGERPRINT_SEGMENTATION_MODE = 44
    ROLL_METHOD = 45
    RENEWAL_OPPOSITE_IMAGE_LEVEL = 46
    PREVIEW_IMAGE_QUALITY_FOR_KOJAK = 47
    ADAPTIVE_CAPTURE_MODE = 48
    ENABLE_KOJAK_BEHAVIOR_2_6 = 49
    DISABLE_SEGMENT_ROTATION = 50
    DR_MODE_ZOOM_IN = 51
    # Reserved properties
    RESERVED_1 = 200
    RESERVED_2 = 201
    RESERVED_100 = 202
    RESERVED_IMAGE_PROCESS_THRESHOLD = 400
    RESERVED_ENABLE_TOF_FOR_ROLL = 401
    RESERVED_CAPTURE_BRIGHTNESS_THRESHOLD_FOR_FLAT = 402
    RESERVED_CAPTURE_BRIGHTNESS_THRESHOLD_FOR_ROLL = 403
    RESERVED_ENHANCED_RESULT_IMAGE = 404
    RESERVED_ENHANCED_RESULT_IMAGE_LEVEL = 405
    RESERVED_ENABLE_SLIP_DETECTION = 406
    RESERVED_SLIP_DETECTION_LEVEL = 407
    RESERVED_ENABLE_TRICK_CAPTURE = 408
    RESERVED_ENABLE_CBP_MODE = 409
    RESERVED_RAW_IMAGE_WIDTH = 410
    RESERVED_RAW_IMAGE_HEIGHT = 411
    RESERVED_TFT_NOISE_REMOVAL = 412
    RESERVED_LINE_BLACK_FILL = 413
    RESERVED_RECALCILATE_BRIGHTNESS = 414
    RESERVED_LINE_RESTORE = 415
    RESERVED_SW_UNIFORMITY = 416
    RESERVED_SET_ROLL_TEST_MODE = 417


class IBSU_ClientWindowPropertyId(IntEnum):
    """IBSU_ClientWindowPropertyId -- client window property identifiers."""
    BK_COLOR = 0
    ROLL_GUIDE_LINE = 1
    DISP_INVALID_AREA = 2
    SCALE_FACTOR = 3
    LEFT_MARGIN = 4
    TOP_MARGIN = 5
    ROLL_GUIDE_LINE_WIDTH = 6
    SCALE_FACTOR_EX = 7
    KEEP_REDRAW_LAST_IMAGE = 8
    ROLL_GUIDE_LINE_COLOR = 9


# ---------------------------------------------------------------------------
# Matcher enumerations  (IBScanUltimateApi_defs.h)
# ---------------------------------------------------------------------------

class IBSM_ImageFormat(IntEnum):
    """IBSM_ImageFormat -- image formats for matcher."""
    NO_BIT_PACKING = 0
    BIT_PACKED = 1
    WSQ = 2
    JPEG_LOSSY = 3
    JPEG2000_LOSSY = 4
    JPEG2000_LOSSLESS = 5
    PNG = 6
    UNKNOWN = 7


class IBSM_ImpressionType(IntEnum):
    """IBSM_ImpressionType -- image impression types for matcher."""
    LIVE_SCAN_PLAIN = 0
    LIVE_SCAN_ROLLED = 1
    NONLIVE_SCAN_PLAIN = 2
    NONLIVE_SCAN_ROLLED = 3
    LATENT_IMPRESSION = 4
    LATENT_TRACING = 5
    LATENT_PHOTO = 6
    LATENT_LIFT = 7
    LIVE_SCAN_SWIPE = 8
    LIVE_SCAN_VERTICAL_ROLL = 9
    LIVE_SCAN_PALM = 10
    NONLIVE_SCAN_PALM = 11
    LATENT_PALM_IMPRESSION = 12
    LATENT_PALM_TRACING = 13
    LATENT_PALM_PHOTO = 14
    LATENT_PALM_LIFT = 15
    LIVE_SCAN_OPTICAL_CONTACTLESS_PLAIN = 24
    LIVE_SCAN_OPTICAL_CONTACTLESS_ROLLED = 25
    OTHER = 28
    UNKNOWN = 29
    MOVING_SUBJECT_CONTACTLESS_PLAIN = 41
    MOVING_SUBJECT_CONTACTLESS_ROLLED = 42


class IBSM_FingerPosition(IntEnum):
    """IBSM_FingerPosition -- finger position identifiers."""
    UNKNOWN = 0
    RIGHT_THUMB = 1
    RIGHT_INDEX_FINGER = 2
    RIGHT_MIDDLE_FINGER = 3
    RIGHT_RING_FINGER = 4
    RIGHT_LITTLE_FINGER = 5
    LEFT_THUMB = 6
    LEFT_INDEX_FINGER = 7
    LEFT_MIDDLE_FINGER = 8
    LEFT_RING_FINGER = 9
    LEFT_LITTLE_FINGER = 10
    PLAIN_RIGHT_FOUR_FINGERS = 13
    PLAIN_LEFT_FOUR_FINGERS = 14
    PLAIN_THUMBS = 15
    UNKNOWN_PALM = 20
    RIGHT_FULL_PALM = 21
    RIGHT_WRITERS_PALM = 22
    LEFT_FULL_PALM = 23
    LEFT_WRITERS_PALM = 24
    RIGHT_LOWER_PALM = 25
    RIGHT_UPPER_PALM = 26
    LEFT_LOWER_PALM = 27
    LEFT_UPPER_PALM = 28
    RIGHT_OTHER = 29
    LEFT_OTHER = 30
    RIGHT_INTERDIGITAL = 31
    RIGHT_THENAR = 32
    RIGHT_HYPOTHENAR = 33
    LEFT_INTERDIGITAL = 34
    LEFT_THENAR = 35
    LEFT_HYPOTHENAR = 36
    RIGHT_INDEX_AND_MIDDLE = 40
    RIGHT_MIDDLE_AND_RING = 41
    RIGHT_RING_AND_LITTLE = 42
    LEFT_INDEX_AND_MIDDLE = 43
    LEFT_MIDDLE_AND_RING = 44
    LEFT_RING_AND_LITTLE = 45
    RIGHT_INDEX_AND_LEFT_INDEX = 46
    RIGHT_INDEX_AND_MIDDLE_AND_RING = 47
    RIGHT_MIDDLE_AND_RING_AND_LITTLE = 48
    LEFT_INDEX_AND_MIDDLE_AND_RING = 49
    LEFT_MIDDLE_AND_RING_AND_LITTLE = 50


class IBSM_CaptureDeviceTechID(IntEnum):
    """IBSM_CaptureDeviceTechID -- capture device technology IDs."""
    UNKNOWN_OR_UNSPECIFIED = 0
    WHITE_LIGHT_OPTICAL_TIR = 1
    WHITE_LIGHT_OPTICAL_DIRECT_VIEW_ON_PLATEN = 2
    WHITE_LIGHT_OPTICAL_TOUCHLESS = 3
    MONOCHROMATIC_VISIBLE_OPTICAL_TIR = 4
    MONOCHROMATIC_VISIBLE_OPTICAL_DIRECT_VIEW_ON_PLATEN = 5
    MONOCHROMATIC_VISIBLE_OPTICAL_TOUCHLESS = 6
    MONOCHROMATIC_IR_OPTICAL_TIR = 7
    MONOCHROMATIC_IR_OPTICAL_DIRECT_VIEW_ON_PLATEN = 8
    MONOCHROMATIC_IR_OPTICAL_TOUCHLESS = 9
    MULTISPECTRAL_OPTICAL_TIR = 10
    MULTISPECTRAL_OPTICAL_DIRECT_VIEW_ON_PLATEN = 11
    MULTISPECTRAL_OPTICAL_TOUCHLESS = 12
    ELECTRO_LUMINESCENT = 13
    SEMICONDUCTOR_CAPACITIVE = 14
    SEMICONDUCTOR_RF = 15
    SEMICONDUCTOR_THERMAL = 16
    PRESSURE_SENSITIVE = 17
    ULTRASOUND = 18
    MECHANICAL = 19
    GLASS_FIBER = 20


class IBSM_CaptureDeviceTypeID(IntEnum):
    """IBSM_CaptureDeviceTypeID -- supported device type IDs."""
    UNKNOWN = 0x0000
    CURVE = 0x1004
    WATSON = 0x1005
    SHERLOCK = 0x1010
    WATSON_MINI = 0x1020
    COLUMBO = 0x1100
    HOLMES = 0x1200
    KOJAK = 0x1300
    FIVE0 = 0x1500
    DANNO = 0x1600
    MANNIX = 0x1D00


class IBSM_CaptureDeviceVendorID(IntEnum):
    """IBSM_CaptureDeviceVendorID -- capture device vendor IDs."""
    UNREPORTED = 0x0000
    INTEGRATED_BIOMETRICS = 0x113F


class IBSM_StandardFormat(IntEnum):
    """IBSM_StandardFormat -- standard template format types."""
    ISO_19794_2_2005 = 0
    ISO_19794_4_2005 = 1
    ISO_19794_2_2011 = 2
    ISO_19794_4_2011 = 3
    ANSI_INCITS_378_2004 = 4
    ANSI_INCITS_381_2004 = 5
    ISO_39794_4_2019 = 6


class IBSM_TemplateVersion(IntEnum):
    """IBSM_TemplateVersion -- template versions."""
    IBISDK_0 = 0x00
    IBISDK_1 = 0x01
    IBISDK_2 = 0x02
    IBISDK_3 = 0x03
    NEW_0 = 0x10


# ---------------------------------------------------------------------------
# ctypes Structures  (IBScanUltimate.h / IBScanUltimateApi_defs.h)
# ---------------------------------------------------------------------------

class IBSU_ImageData(Structure):
    """Container for image data and metadata.

    Mirrors the C ``IBSU_ImageData`` struct.  DWORD is mapped to c_ulong,
    BYTE to c_ubyte, BOOL to c_int (Win32 convention).
    """
    _fields_ = [
        ("Buffer", c_void_p),
        ("Width", c_ulong),
        ("Height", c_ulong),
        ("ResolutionX", c_double),
        ("ResolutionY", c_double),
        ("FrameTime", c_double),
        ("Pitch", c_int),
        ("BitsPerPixel", c_ubyte),
        ("Format", c_int),       # IBSU_ImageFormat
        ("IsFinal", c_int),      # BOOL
        ("ProcessThres", c_ulong),
    ]


class IBSU_SdkVersion(Structure):
    """Container for SDK version strings."""
    _fields_ = [
        ("Product", c_char * IBSU_MAX_STR_LEN),
        ("File", c_char * IBSU_MAX_STR_LEN),
    ]


class IBSU_DeviceDesc(Structure):
    """Basic device description.

    The Linux (non-Android) layout does NOT include devID.
    """
    _fields_ = [
        ("serialNumber", c_char * IBSU_MAX_STR_LEN),
        ("productName", c_char * IBSU_MAX_STR_LEN),
        ("interfaceType", c_char * IBSU_MAX_STR_LEN),
        ("fwVersion", c_char * IBSU_MAX_STR_LEN),
        ("devRevision", c_char * IBSU_MAX_STR_LEN),
        ("handle", c_int),
        ("IsHandleOpened", c_int),  # BOOL
        ("IsDeviceLocked", c_int),  # BOOL
        ("customerString", c_char * IBSU_MAX_STR_LEN),
    ]


class IBSU_SegmentPosition(Structure):
    """Coordinates of a finger segment (quadrilateral)."""
    _fields_ = [
        ("x1", c_short), ("y1", c_short),
        ("x2", c_short), ("y2", c_short),
        ("x3", c_short), ("y3", c_short),
        ("x4", c_short), ("y4", c_short),
    ]


class IBSM_ImageData(Structure):
    """Matcher image data container."""
    _fields_ = [
        ("ImageFormat", c_int),            # IBSM_ImageFormat
        ("ImpressionType", c_int),         # IBSM_ImpressionType
        ("FingerPosition", c_int),         # IBSM_FingerPosition
        ("CaptureDeviceTechID", c_int),    # IBSM_CaptureDeviceTechID
        ("CaptureDeviceVendorID", c_ushort),
        ("CaptureDeviceTypeID", c_ushort),
        ("ScanSamplingX", c_ushort),
        ("ScanSamplingY", c_ushort),
        ("ImageSamplingX", c_ushort),
        ("ImageSamplingY", c_ushort),
        ("ImageSizeX", c_ushort),
        ("ImageSizeY", c_ushort),
        ("ScaleUnit", c_ubyte),
        ("BitDepth", c_ubyte),
        ("ImageDataLength", c_uint),
        ("ImageData", c_void_p),
    ]


class IBSM_Template(Structure):
    """Matcher template container."""
    _fields_ = [
        ("Version", c_int),               # IBSM_TemplateVersion
        ("FingerPosition", c_uint),
        ("ImpressionType", c_int),         # IBSM_ImpressionType
        ("CaptureDeviceTechID", c_int),    # IBSM_CaptureDeviceTechID
        ("CaptureDeviceVendorID", c_ushort),
        ("CaptureDeviceTypeID", c_ushort),
        ("ImageSamplingX", c_ushort),
        ("ImageSamplingY", c_ushort),
        ("ImageSizeX", c_ushort),
        ("ImageSizeY", c_ushort),
        ("Minutiae", c_uint * IBSU_MAX_MINUTIAE_SIZE),
        ("Reserved", c_uint),
    ]


class IBSM_StandardFormatData(Structure):
    """ISO/ANSI standard format data container."""
    _fields_ = [
        ("Data", c_void_p),
        ("DataLength", c_ulong),
        ("Format", c_int),  # IBSM_StandardFormat
    ]


# ---------------------------------------------------------------------------
# Callback function-pointer types  (IBScanUltimateApi_defs.h)
# ---------------------------------------------------------------------------
# On Linux CALLBACK is empty, so calling convention is cdecl (CFUNCTYPE).

IBSU_Callback = CFUNCTYPE(
    None,  # void
    c_int,      # deviceHandle
    c_void_p,   # pContext
)

IBSU_CallbackPreviewImage = CFUNCTYPE(
    None,
    c_int,          # deviceHandle
    c_void_p,       # pContext
    IBSU_ImageData,  # image (passed by value)
)

IBSU_CallbackFingerCount = CFUNCTYPE(
    None,
    c_int,     # deviceHandle
    c_void_p,  # pContext
    c_int,     # fingerCountState (IBSU_FingerCountState)
)

IBSU_CallbackFingerQuality = CFUNCTYPE(
    None,
    c_int,           # deviceHandle
    c_void_p,        # pContext
    POINTER(c_int),  # pQualityArray (IBSU_FingerQualityState*)
    c_int,           # qualityArrayCount
)

IBSU_CallbackDeviceCount = CFUNCTYPE(
    None,
    c_int,     # detectedDevices
    c_void_p,  # pContext
)

IBSU_CallbackInitProgress = CFUNCTYPE(
    None,
    c_int,     # deviceIndex
    c_void_p,  # pContext
    c_int,     # progressValue
)

IBSU_CallbackTakingAcquisition = CFUNCTYPE(
    None,
    c_int,     # deviceHandle
    c_void_p,  # pContext
    c_int,     # imageType (IBSU_ImageType)
)

IBSU_CallbackCompleteAcquisition = CFUNCTYPE(
    None,
    c_int,     # deviceHandle
    c_void_p,  # pContext
    c_int,     # imageType (IBSU_ImageType)
)

IBSU_CallbackResultImage = CFUNCTYPE(
    None,
    c_int,                    # deviceHandle
    c_void_p,                 # pContext
    IBSU_ImageData,           # image
    c_int,                    # imageType (IBSU_ImageType)
    POINTER(IBSU_ImageData),  # pSplitImageArray
    c_int,                    # splitImageArrayCount
)

IBSU_CallbackResultImageEx = CFUNCTYPE(
    None,
    c_int,                          # deviceHandle
    c_void_p,                       # pContext
    c_int,                          # imageStatus
    IBSU_ImageData,                 # image
    c_int,                          # imageType (IBSU_ImageType)
    c_int,                          # detectedFingerCount
    c_int,                          # segmentImageArrayCount
    POINTER(IBSU_ImageData),        # pSegmentImageArray
    POINTER(IBSU_SegmentPosition),  # pSegmentPositionArray
)

IBSU_CallbackClearPlatenAtCapture = CFUNCTYPE(
    None,
    c_int,     # deviceHandle
    c_void_p,  # pContext
    c_int,     # platenState (IBSU_PlatenState)
)

IBSU_CallbackAsyncOpenDevice = CFUNCTYPE(
    None,
    c_int,     # deviceIndex
    c_void_p,  # pContext
    c_int,     # deviceHandle
    c_int,     # errorCode
)

IBSU_CallbackNotifyMessage = CFUNCTYPE(
    None,
    c_int,     # deviceHandle
    c_void_p,  # pContext
    c_int,     # notifyMessage
)

IBSU_CallbackKeyButtons = CFUNCTYPE(
    None,
    c_int,     # deviceHandle
    c_void_p,  # pContext
    c_int,     # pressedKeyButtons
)


# ---------------------------------------------------------------------------
# Error-code to human-readable name mapping (convenience)
# ---------------------------------------------------------------------------
_ERROR_CODE_NAMES: dict[int, str] = {
    IBSU_STATUS_OK: "IBSU_STATUS_OK",
    IBSU_ERR_INVALID_PARAM_VALUE: "IBSU_ERR_INVALID_PARAM_VALUE",
    IBSU_ERR_MEM_ALLOC: "IBSU_ERR_MEM_ALLOC",
    IBSU_ERR_NOT_SUPPORTED: "IBSU_ERR_NOT_SUPPORTED",
    IBSU_ERR_FILE_OPEN: "IBSU_ERR_FILE_OPEN",
    IBSU_ERR_FILE_READ: "IBSU_ERR_FILE_READ",
    IBSU_ERR_RESOURCE_LOCKED: "IBSU_ERR_RESOURCE_LOCKED",
    IBSU_ERR_MISSING_RESOURCE: "IBSU_ERR_MISSING_RESOURCE",
    IBSU_ERR_INVALID_ACCESS_POINTER: "IBSU_ERR_INVALID_ACCESS_POINTER",
    IBSU_ERR_THREAD_CREATE: "IBSU_ERR_THREAD_CREATE",
    IBSU_ERR_COMMAND_FAILED: "IBSU_ERR_COMMAND_FAILED",
    IBSU_ERR_LIBRARY_UNLOAD_FAILED: "IBSU_ERR_LIBRARY_UNLOAD_FAILED",
    IBSU_ERR_CHANNEL_IO_COMMAND_FAILED: "IBSU_ERR_CHANNEL_IO_COMMAND_FAILED",
    IBSU_ERR_CHANNEL_IO_READ_FAILED: "IBSU_ERR_CHANNEL_IO_READ_FAILED",
    IBSU_ERR_CHANNEL_IO_WRITE_FAILED: "IBSU_ERR_CHANNEL_IO_WRITE_FAILED",
    IBSU_ERR_CHANNEL_IO_READ_TIMEOUT: "IBSU_ERR_CHANNEL_IO_READ_TIMEOUT",
    IBSU_ERR_CHANNEL_IO_WRITE_TIMEOUT: "IBSU_ERR_CHANNEL_IO_WRITE_TIMEOUT",
    IBSU_ERR_CHANNEL_IO_UNEXPECTED_FAILED: "IBSU_ERR_CHANNEL_IO_UNEXPECTED_FAILED",
    IBSU_ERR_CHANNEL_IO_INVALID_HANDLE: "IBSU_ERR_CHANNEL_IO_INVALID_HANDLE",
    IBSU_ERR_CHANNEL_IO_WRONG_PIPE_INDEX: "IBSU_ERR_CHANNEL_IO_WRONG_PIPE_INDEX",
    IBSU_ERR_DEVICE_IO: "IBSU_ERR_DEVICE_IO",
    IBSU_ERR_DEVICE_NOT_FOUND: "IBSU_ERR_DEVICE_NOT_FOUND",
    IBSU_ERR_DEVICE_NOT_MATCHED: "IBSU_ERR_DEVICE_NOT_MATCHED",
    IBSU_ERR_DEVICE_ACTIVE: "IBSU_ERR_DEVICE_ACTIVE",
    IBSU_ERR_DEVICE_NOT_INITIALIZED: "IBSU_ERR_DEVICE_NOT_INITIALIZED",
    IBSU_ERR_DEVICE_INVALID_STATE: "IBSU_ERR_DEVICE_INVALID_STATE",
    IBSU_ERR_DEVICE_BUSY: "IBSU_ERR_DEVICE_BUSY",
    IBSU_ERR_DEVICE_NOT_SUPPORTED_FEATURE: "IBSU_ERR_DEVICE_NOT_SUPPORTED_FEATURE",
    IBSU_ERR_INVALID_LICENSE: "IBSU_ERR_INVALID_LICENSE",
    IBSU_ERR_USB20_REQUIRED: "IBSU_ERR_USB20_REQUIRED",
    IBSU_ERR_DEVICE_ENABLED_POWER_SAVE_MODE: "IBSU_ERR_DEVICE_ENABLED_POWER_SAVE_MODE",
    IBSU_ERR_DEVICE_NEED_UPDATE_FIRMWARE: "IBSU_ERR_DEVICE_NEED_UPDATE_FIRMWARE",
    IBSU_ERR_DEVICE_NEED_CALIBRATE_TOF: "IBSU_ERR_DEVICE_NEED_CALIBRATE_TOF",
    IBSU_ERR_DEVICE_INVALID_CALIBRATION_DATA: "IBSU_ERR_DEVICE_INVALID_CALIBRATION_DATA",
    IBSU_ERR_DEVICE_HIGHER_SDK_REQUIRED: "IBSU_ERR_DEVICE_HIGHER_SDK_REQUIRED",
    IBSU_ERR_DEVICE_LOCK_INVALID_BUFF: "IBSU_ERR_DEVICE_LOCK_INVALID_BUFF",
    IBSU_ERR_DEVICE_LOCK_INFO_EMPTY: "IBSU_ERR_DEVICE_LOCK_INFO_EMPTY",
    IBSU_ERR_DEVICE_LOCK_INFO_NOT_MATCHED: "IBSU_ERR_DEVICE_LOCK_INFO_NOT_MATCHED",
    IBSU_ERR_DEVICE_LOCK_INVALID_CHECKSUM: "IBSU_ERR_DEVICE_LOCK_INVALID_CHECKSUM",
    IBSU_ERR_DEVICE_LOCK_INVALID_KEY: "IBSU_ERR_DEVICE_LOCK_INVALID_KEY",
    IBSU_ERR_DEVICE_LOCK_LOCKED: "IBSU_ERR_DEVICE_LOCK_LOCKED",
    IBSU_ERR_DEVICE_LOCK_ILLEGAL_DEVICE: "IBSU_ERR_DEVICE_LOCK_ILLEGAL_DEVICE",
    IBSU_ERR_DEVICE_LOCK_INVALID_SERIAL_FORMAT: "IBSU_ERR_DEVICE_LOCK_INVALID_SERIAL_FORMAT",
    IBSU_ERR_CAPTURE_COMMAND_FAILED: "IBSU_ERR_CAPTURE_COMMAND_FAILED",
    IBSU_ERR_CAPTURE_STOP: "IBSU_ERR_CAPTURE_STOP",
    IBSU_ERR_CAPTURE_TIMEOUT: "IBSU_ERR_CAPTURE_TIMEOUT",
    IBSU_ERR_CAPTURE_STILL_RUNNING: "IBSU_ERR_CAPTURE_STILL_RUNNING",
    IBSU_ERR_CAPTURE_NOT_RUNNING: "IBSU_ERR_CAPTURE_NOT_RUNNING",
    IBSU_ERR_CAPTURE_INVALID_MODE: "IBSU_ERR_CAPTURE_INVALID_MODE",
    IBSU_ERR_CAPTURE_ALGORITHM: "IBSU_ERR_CAPTURE_ALGORITHM",
    IBSU_ERR_CAPTURE_ROLLING: "IBSU_ERR_CAPTURE_ROLLING",
    IBSU_ERR_CAPTURE_ROLLING_TIMEOUT: "IBSU_ERR_CAPTURE_ROLLING_TIMEOUT",
    IBSU_ERR_CLIENT_WINDOW: "IBSU_ERR_CLIENT_WINDOW",
    IBSU_ERR_CLIENT_WINDOW_NOT_CREATE: "IBSU_ERR_CLIENT_WINDOW_NOT_CREATE",
    IBSU_ERR_INVALID_OVERLAY_HANDLE: "IBSU_ERR_INVALID_OVERLAY_HANDLE",
    IBSU_ERR_NBIS_NFIQ_FAILED: "IBSU_ERR_NBIS_NFIQ_FAILED",
    IBSU_ERR_NBIS_WSQ_ENCODE_FAILED: "IBSU_ERR_NBIS_WSQ_ENCODE_FAILED",
    IBSU_ERR_NBIS_WSQ_DECODE_FAILED: "IBSU_ERR_NBIS_WSQ_DECODE_FAILED",
    IBSU_ERR_NBIS_PNG_ENCODE_FAILED: "IBSU_ERR_NBIS_PNG_ENCODE_FAILED",
    IBSU_ERR_NBIS_JP2_ENCODE_FAILED: "IBSU_ERR_NBIS_JP2_ENCODE_FAILED",
    IBSU_ERR_DUPLICATE_EXTRACTION_FAILED: "IBSU_ERR_DUPLICATE_EXTRACTION_FAILED",
    IBSU_ERR_DUPLICATE_ALREADY_USED: "IBSU_ERR_DUPLICATE_ALREADY_USED",
    IBSU_ERR_DUPLICATE_SEGMENTATION_FAILED: "IBSU_ERR_DUPLICATE_SEGMENTATION_FAILED",
    IBSU_ERR_DUPLICATE_MATCHING_FAILED: "IBSU_ERR_DUPLICATE_MATCHING_FAILED",
    IBSU_ERR_PAD_PROPERTY_DISABLED: "IBSU_ERR_PAD_PROPERTY_DISABLED",
    IBSU_ERR_INCORRECT_STANDARD_FORMAT: "IBSU_ERR_INCORRECT_STANDARD_FORMAT",
    IBSU_ERR_NFIQ2_NOT_INITIALIZED: "IBSU_ERR_NFIQ2_NOT_INITIALIZED",
    IBSU_ERR_NFIQ2_FAILED: "IBSU_ERR_NFIQ2_FAILED",
}


def error_code_to_name(code: int) -> str:
    """Return the symbolic name for an IBScanUltimate error / warning code."""
    return _ERROR_CODE_NAMES.get(code, f"UNKNOWN_CODE({code})")
