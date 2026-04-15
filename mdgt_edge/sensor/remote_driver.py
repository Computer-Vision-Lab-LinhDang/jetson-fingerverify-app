"""
Remote sensor driver.

Allows this backend to use a sensor hosted by another MDGT backend
over HTTP (`/api/v1/sensor/*` endpoints).
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Optional

import httpx

from .base import CaptureResult, SensorDriver, SensorInfo


class RemoteSensorDriver(SensorDriver):
    """SensorDriver implementation backed by a remote HTTP sensor API."""

    def __init__(self, base_url: str, timeout_sec: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout_sec)
        self._logger = logging.getLogger("RemoteSensorDriver")
        self._connected = False
        self._info: Optional[SensorInfo] = None

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        try:
            response = self._client.request(method, self._url(path), json=payload)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                return data
            self._logger.warning("Remote response is not JSON object: %s", type(data).__name__)
            return None
        except Exception as exc:
            self._logger.warning("Remote sensor request failed: %s %s (%s)", method, path, exc)
            return None

    def _get_status_data(self) -> Optional[dict[str, Any]]:
        envelope = self._request_json("GET", "status")
        if not envelope:
            return None
        data = envelope.get("data")
        if isinstance(data, dict):
            return data
        return None

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _update_info_from_status(self, status: dict[str, Any]) -> None:
        vendor_id = self._to_int(status.get("vendor_id"))
        product_id = self._to_int(status.get("product_id"))
        self._info = SensorInfo(
            vendor_id=vendor_id,
            product_id=product_id,
            name=f"Remote Sensor {vendor_id:04x}:{product_id:04x}",
            resolution_dpi=self._to_int(status.get("resolution_dpi"), 500),
            image_width=192,
            image_height=192,
            firmware_version=status.get("firmware_version") or "",
            serial_number=status.get("serial_number") or "",
        )

    # -- SensorDriver interface --------------------------------------------

    def open(self) -> bool:
        status = self._get_status_data()
        if status is None:
            self._connected = False
            return False

        connected = bool(status.get("connected"))
        is_real_hardware = bool(status.get("is_real_hardware"))

        # Only treat as connected when remote side reports real hardware.
        self._connected = connected and is_real_hardware
        self._update_info_from_status(status)
        return self._connected

    def close(self) -> None:
        self._connected = False
        self._client.close()

    def is_connected(self) -> bool:
        return self._connected

    def capture_image(self) -> CaptureResult:
        envelope = self._request_json("POST", "capture")
        if not envelope:
            return CaptureResult(success=False, error="Remote capture request failed")

        data = envelope.get("data")
        if not isinstance(data, dict):
            return CaptureResult(success=False, error="Remote capture response missing data")

        success = bool(envelope.get("success")) and bool(data.get("success"))
        if not success:
            error = envelope.get("error") or data.get("message") or "Remote capture failed"
            return CaptureResult(success=False, error=str(error))

        image_base64 = data.get("image_base64") or ""
        if not image_base64:
            return CaptureResult(success=False, error="Remote capture returned empty image")

        try:
            image_bytes = base64.b64decode(image_base64)
        except Exception as exc:
            return CaptureResult(success=False, error=f"Invalid base64 from remote: {exc}")

        return CaptureResult(
            success=True,
            image_data=image_bytes,
            width=self._to_int(data.get("width"), 192),
            height=self._to_int(data.get("height"), 192),
            quality_score=self._to_float(data.get("quality_score"), 0.0),
            has_finger=bool(data.get("has_finger")),
        )

    def check_finger(self) -> bool:
        capture = self.capture_image()
        return capture.success and capture.has_finger

    def get_info(self) -> SensorInfo:
        status = self._get_status_data()
        if status is not None:
            self._update_info_from_status(status)
        if self._info is not None:
            return self._info
        return SensorInfo(
            vendor_id=0,
            product_id=0,
            name="Remote Sensor",
            resolution_dpi=500,
            image_width=192,
            image_height=192,
        )

    def led_on(self, color: int) -> bool:
        envelope = self._request_json("POST", "led", {"color": str(color), "duration_ms": 1000})
        return bool(envelope and envelope.get("success"))

    def led_off(self) -> bool:
        envelope = self._request_json("POST", "led", {"color": "off", "duration_ms": 0})
        return bool(envelope and envelope.get("success"))

    def beep(self, duration_ms: int = 100) -> bool:
        # Remote /sensor API currently has no explicit beep endpoint.
        _ = duration_ms
        return False

    # -- Optional methods used by SensorService status endpoint ------------

    def get_user_count(self) -> int:
        status = self._get_status_data()
        if status is None:
            return -1
        value = status.get("user_count")
        return self._to_int(value, -1) if value is not None else -1

    def get_compare_level(self) -> int:
        status = self._get_status_data()
        if status is None:
            return -1
        value = status.get("compare_level")
        return self._to_int(value, -1) if value is not None else -1
