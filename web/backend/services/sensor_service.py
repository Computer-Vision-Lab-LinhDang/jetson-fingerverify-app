"""
Sensor Service — singleton that manages the physical sensor driver.

Provides async wrappers around the thread-safe sensor driver so FastAPI
endpoints can call sensor operations without blocking the event loop.

Driver priority:
  1. IBScanUltimateDriver  (from mdgt_edge.sensor.ibscan_driver)
  2. USBSensorDriver       (old custom SDK)
  3. MockSensorDriver      (development fallback)
"""

from __future__ import annotations

import asyncio
import base64
import logging
from functools import partial
from typing import Optional

from mdgt_edge.sensor import (
    USBSensorDriver,
    MockSensorDriver,
    SensorDriver,
    CaptureResult,
    SensorInfo,
)

logger = logging.getLogger(__name__)

# Cached last captured image for endpoints that operate on "last capture"
_last_capture: Optional[CaptureResult] = None


class SensorService:
    """Async-friendly singleton wrapping the physical sensor."""

    _instance: Optional[SensorService] = None

    def __init__(self) -> None:
        self._driver: Optional[SensorDriver] = None
        self._is_ibscan: bool = False
        # Last captured raw image bytes (set by capture_image / capture_multi_finger)
        self._last_image_data: bytes = b""
        self._last_image_width: int = 0
        self._last_image_height: int = 0
        # PAD config state
        self._spoof_enabled: bool = True
        self._spoof_level: int = 3

    @classmethod
    def get_instance(cls) -> SensorService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- lifecycle -----------------------------------------------------------

    async def initialize(
        self,
        vid: int = 0x0483,
        pid: int = 0x5720,
        sdk_path: str = "/home/binhan3/SDK-Fingerprint-sensor",
        use_mock: bool = False,
    ) -> bool:
        """Open the sensor. Returns True if hardware connected.

        Tries IBScanUltimateDriver first, then USBSensorDriver, then MockSensorDriver.
        """
        if use_mock:
            self._driver = MockSensorDriver()
            self._driver.open()
            self._is_ibscan = False
            logger.info("SensorService: using MockSensorDriver")
            return True

        # -- Try IBScanUltimate first -----------------------------------------
        try:
            from mdgt_edge.sensor.ibscan_driver import IBScanUltimateDriver  # type: ignore[import]

            ibscan_driver = IBScanUltimateDriver()
            loop = asyncio.get_running_loop()
            connected = await loop.run_in_executor(None, ibscan_driver.open)
            if connected:
                self._driver = ibscan_driver
                self._is_ibscan = True
                logger.info("SensorService: IBScanUltimate sensor connected")
                return True
            logger.warning("SensorService: IBScanUltimate found but failed to open")
        except ImportError:
            logger.debug("SensorService: IBScanUltimateDriver not available, trying USBSensorDriver")
        except Exception as exc:
            logger.warning("SensorService: IBScanUltimate init error: %s", exc)

        # -- Try legacy USB sensor -------------------------------------------
        driver = USBSensorDriver(vid=vid, pid=pid, sdk_path=sdk_path)
        loop = asyncio.get_running_loop()
        connected = await loop.run_in_executor(None, driver.open)

        if connected:
            self._driver = driver
            self._is_ibscan = False
            logger.info("SensorService: USB sensor connected")
            return True

        # -- Fall back to mock -----------------------------------------------
        logger.warning(
            "SensorService: no hardware found, falling back to MockSensorDriver"
        )
        self._driver = MockSensorDriver()
        self._driver.open()
        self._is_ibscan = False
        return False

    async def shutdown(self) -> None:
        if self._driver is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._driver.close)
            self._driver = None
            logger.info("SensorService: shut down")

    # -- properties ----------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._driver is not None and self._driver.is_connected()

    @property
    def is_real_hardware(self) -> bool:
        return isinstance(self._driver, (USBSensorDriver,)) or self._is_ibscan

    @property
    def is_ibscan(self) -> bool:
        return self._is_ibscan

    # -- async wrappers (run blocking SDK calls in thread pool) ---------------

    async def capture_image(self) -> CaptureResult:
        if self._driver is None:
            return CaptureResult(success=False, error="Sensor not initialized")
        loop = asyncio.get_running_loop()
        result: CaptureResult = await loop.run_in_executor(None, self._driver.capture_image)
        if result.success and result.image_data:
            self._last_image_data = result.image_data
            self._last_image_width = result.width
            self._last_image_height = result.height
        return result

    async def check_finger(self) -> bool:
        if self._driver is None:
            return False
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._driver.check_finger)

    async def get_info(self) -> Optional[SensorInfo]:
        if self._driver is None:
            return None
        return self._driver.get_info()

    async def led_on(self, color: int) -> bool:
        if self._driver is None:
            return False
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self._driver.led_on, color))

    async def led_off(self) -> bool:
        if self._driver is None:
            return False
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._driver.led_off)

    async def beep(self, duration_ms: int = 100) -> bool:
        if self._driver is None:
            return False
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, partial(self._driver.beep, duration_ms)
        )

    # -- hardware matching (USB sensor only) ---------------------------------

    async def add_user(self, user_id: Optional[int] = None) -> tuple[bool, int]:
        if not isinstance(self._driver, USBSensorDriver):
            return False, 0
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, partial(self._driver.add_user, user_id)
        )

    async def match_fingerprint(
        self, timeout_sec: float = 5.0
    ) -> tuple[bool, int]:
        if not isinstance(self._driver, USBSensorDriver):
            return False, 0
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, partial(self._driver.match_fingerprint, timeout_sec)
        )

    async def delete_user(self, user_id: int) -> bool:
        if not isinstance(self._driver, USBSensorDriver):
            return False
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, partial(self._driver.delete_user, user_id)
        )

    async def delete_all(self) -> bool:
        if not isinstance(self._driver, USBSensorDriver):
            return False
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._driver.delete_all)

    async def get_user_count(self) -> int:
        if not isinstance(self._driver, USBSensorDriver):
            return -1
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._driver.get_user_count)

    async def get_compare_level(self) -> int:
        if not isinstance(self._driver, USBSensorDriver):
            return -1
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._driver.get_compare_level)

    # -- IBScanUltimate-specific methods -------------------------------------

    async def get_devices(self) -> list[dict]:
        """List all connected IBScan devices."""
        if not self._is_ibscan:
            return []
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, self._driver.get_devices)  # type: ignore[union-attr]
            return result if isinstance(result, list) else []
        except AttributeError:
            logger.warning("get_devices: driver does not support this method")
            return []
        except Exception as exc:
            logger.error("get_devices error: %s", exc)
            return []

    async def get_device_info(self, device_index: int = 0) -> dict:
        """Get detailed device description (serial, firmware, product, etc.)."""
        if not self._is_ibscan:
            info = await self.get_info()
            if info is None:
                return {}
            return {
                "index": 0,
                "serial_number": info.serial_number,
                "product_name": info.name,
                "interface_type": "USB",
                "firmware_version": info.firmware_version,
                "revision": "",
                "is_locked": False,
                "is_open": self.is_connected,
            }
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None, partial(self._driver.get_device_info, device_index)  # type: ignore[union-attr]
            )
            return result if isinstance(result, dict) else {}
        except AttributeError:
            logger.warning("get_device_info: driver does not support this method")
            return {}
        except Exception as exc:
            logger.error("get_device_info error: %s", exc)
            return {}

    async def capture_multi_finger(
        self,
        image_type: str = "flat_single",
        resolution: int = 500,
        auto_capture: bool = True,
    ) -> dict:
        """Capture with IBScan options. Returns image + segments + quality.

        Falls back to single capture on non-IBScan drivers.
        """
        if not self._is_ibscan:
            # Graceful fallback: use standard single capture
            result = await self.capture_image()
            if not result.success:
                return {
                    "success": False,
                    "error": result.error,
                    "image_base64": None,
                    "width": 0,
                    "height": 0,
                    "resolution": float(resolution),
                    "quality_score": 0.0,
                    "nfiq2_score": 0,
                    "is_spoof": None,
                    "finger_count": 0,
                    "segments": [],
                }
            b64 = base64.b64encode(result.image_data).decode("ascii")
            return {
                "success": True,
                "image_base64": b64,
                "width": result.width,
                "height": result.height,
                "resolution": float(resolution),
                "quality_score": result.quality_score,
                "nfiq2_score": 0,
                "is_spoof": None,
                "finger_count": 1,
                "segments": [],
            }

        loop = asyncio.get_running_loop()
        try:
            raw = await loop.run_in_executor(
                None,
                partial(
                    self._driver.capture_multi_finger,  # type: ignore[union-attr]
                    image_type,
                    resolution,
                    auto_capture,
                ),
            )
            if isinstance(raw, dict) and raw.get("success"):
                # Cache the main image for subsequent spoof/nfiq2 calls
                img_b64 = raw.get("image_base64", "")
                if img_b64:
                    try:
                        self._last_image_data = base64.b64decode(img_b64)
                        self._last_image_width = raw.get("width", 0)
                        self._last_image_height = raw.get("height", 0)
                    except Exception:
                        pass
            return raw if isinstance(raw, dict) else {"success": False, "error": "Invalid driver response"}
        except AttributeError:
            logger.warning("capture_multi_finger: driver does not support this method; falling back")
            return await self.capture_multi_finger.__wrapped__(self, image_type, resolution, auto_capture)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.error("capture_multi_finger error: %s", exc)
            return {"success": False, "error": str(exc)}

    async def check_spoof(
        self, image_data: bytes, width: int, height: int
    ) -> dict:
        """Run PAD check on captured image. Returns {is_spoof: bool, score: float}."""
        if not self._is_ibscan:
            return {"is_spoof": False, "score": 0.0, "supported": False}
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                partial(self._driver.check_spoof, image_data, width, height),  # type: ignore[union-attr]
            )
            return result if isinstance(result, dict) else {"is_spoof": False, "score": 0.0}
        except AttributeError:
            logger.warning("check_spoof: driver does not support PAD")
            return {"is_spoof": False, "score": 0.0, "supported": False}
        except Exception as exc:
            logger.error("check_spoof error: %s", exc)
            return {"is_spoof": False, "score": 0.0, "error": str(exc)}

    async def get_nfiq2_score(
        self, image_data: bytes, width: int, height: int
    ) -> dict:
        """Compute NFIQ2 quality score. Returns {score: int, level: str}."""
        if not self._is_ibscan:
            return {"score": 0, "level": "poor", "supported": False}
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                partial(self._driver.get_nfiq2_score, image_data, width, height),  # type: ignore[union-attr]
            )
            return result if isinstance(result, dict) else {"score": 0, "level": "poor"}
        except AttributeError:
            logger.warning("get_nfiq2_score: driver does not support NFIQ2")
            return {"score": 0, "level": "poor", "supported": False}
        except Exception as exc:
            logger.error("get_nfiq2_score error: %s", exc)
            return {"score": 0, "level": "poor", "error": str(exc)}

    async def export_image(
        self,
        image_data: bytes,
        width: int,
        height: int,
        format: str = "png",
    ) -> bytes:
        """Export image in WSQ/PNG/JP2 format. Returns encoded bytes."""
        if not self._is_ibscan:
            # For non-IBScan, return raw bytes as-is (caller handles encoding)
            return image_data
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                partial(self._driver.export_image, image_data, width, height, format),  # type: ignore[union-attr]
            )
            return result if isinstance(result, bytes) else image_data
        except AttributeError:
            logger.warning("export_image: driver does not support format export")
            return image_data
        except Exception as exc:
            logger.error("export_image error: %s", exc)
            return b""

    async def set_spoof_config(self, enabled: bool, level: int = 3) -> dict:
        """Configure PAD settings."""
        self._spoof_enabled = enabled
        self._spoof_level = max(1, min(5, level))

        if not self._is_ibscan:
            return {
                "enabled": self._spoof_enabled,
                "level": self._spoof_level,
                "supported": False,
            }
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                partial(self._driver.set_spoof_config, enabled, self._spoof_level),  # type: ignore[union-attr]
            )
            return result if isinstance(result, dict) else {
                "enabled": self._spoof_enabled,
                "level": self._spoof_level,
                "supported": True,
            }
        except AttributeError:
            return {
                "enabled": self._spoof_enabled,
                "level": self._spoof_level,
                "supported": False,
            }
        except Exception as exc:
            logger.error("set_spoof_config error: %s", exc)
            return {
                "enabled": self._spoof_enabled,
                "level": self._spoof_level,
                "error": str(exc),
            }

    async def get_spoof_config(self) -> dict:
        """Get current PAD configuration."""
        if not self._is_ibscan:
            return {
                "enabled": self._spoof_enabled,
                "level": self._spoof_level,
                "supported": False,
            }
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, self._driver.get_spoof_config)  # type: ignore[union-attr]
            if isinstance(result, dict):
                # Sync local state with driver state
                self._spoof_enabled = result.get("enabled", self._spoof_enabled)
                self._spoof_level = result.get("level", self._spoof_level)
            return result if isinstance(result, dict) else {
                "enabled": self._spoof_enabled,
                "level": self._spoof_level,
                "supported": True,
            }
        except AttributeError:
            return {
                "enabled": self._spoof_enabled,
                "level": self._spoof_level,
                "supported": False,
            }
        except Exception as exc:
            logger.error("get_spoof_config error: %s", exc)
            return {
                "enabled": self._spoof_enabled,
                "level": self._spoof_level,
                "error": str(exc),
            }

    # -- helper: access to last captured image data -------------------------

    def get_last_image(self) -> tuple[bytes, int, int]:
        """Return (image_data, width, height) from the most recent capture."""
        return self._last_image_data, self._last_image_width, self._last_image_height


def get_sensor_service() -> SensorService:
    return SensorService.get_instance()
