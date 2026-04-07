"""
Singleton service wrapping the core VerificationPipeline.

Provides async methods for enrollment, 1:1 verification, and 1:N identification.
Designed to be initialized once at application startup and shared via FastAPI
dependency injection.

Now backed by SQLite via DatabaseManager + Repositories.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from web.backend.config import get_settings

logger = logging.getLogger(__name__)


def _iso_to_timestamp(iso_str: str) -> float:
    """Convert ISO-8601 string to Unix timestamp."""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


class EnrollResult:
    def __init__(
        self,
        user_id: str,
        finger: str,
        quality_score: float,
        template_count: int,
        success: bool = True,
        message: str = "Enrollment successful",
    ):
        self.user_id = user_id
        self.finger = finger
        self.quality_score = quality_score
        self.template_count = template_count
        self.success = success
        self.message = message


class VerifyResult:
    def __init__(
        self,
        matched: bool,
        score: float,
        threshold: float,
        user_id: str,
        latency_ms: float,
    ):
        self.matched = matched
        self.score = score
        self.threshold = threshold
        self.user_id = user_id
        self.latency_ms = latency_ms


class IdentifyResult:
    def __init__(
        self,
        user_id: str,
        employee_id: str,
        full_name: str,
        score: float,
    ):
        self.user_id = user_id
        self.employee_id = employee_id
        self.full_name = full_name
        self.score = score


# ---------------------------------------------------------------------------
# Pipeline Service (singleton)
# ---------------------------------------------------------------------------


class PipelineService:
    """Wraps core fingerprint pipeline operations behind an async interface."""

    _instance: PipelineService | None = None

    def __init__(self) -> None:
        self._settings = get_settings()
        self._active_model: str | None = None
        self._model_loaded: bool = False
        self._start_time: float = time.time()
        self._lock = asyncio.Lock()

        # Initialize database
        from mdgt_edge.database.database import DatabaseManager
        from mdgt_edge.database.repository import (
            FingerprintRepository,
            LogRepository,
            UserRepository,
        )

        db_path = str(Path(self._settings.data_dir) / "mdgt_edge.db")
        self._db = DatabaseManager(db_path)
        self._user_repo = UserRepository(self._db)
        self._fp_repo = FingerprintRepository(self._db)
        self._log_repo = LogRepository(self._db)
        logger.info("PipelineService connected to SQLite: %s", db_path)

    # -- singleton access ---------------------------------------------------

    @classmethod
    def get_instance(cls) -> PipelineService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- lifecycle ----------------------------------------------------------

    async def initialize(self) -> None:
        """Load active model and build index at startup."""
        logger.info("Initializing PipelineService ...")
        model_dir = Path(self._settings.model_dir)
        if model_dir.exists():
            trt_files = list(model_dir.glob("*.trt")) + list(model_dir.glob("*.engine"))
            onnx_files = list(model_dir.glob("*.onnx"))
            candidates = trt_files or onnx_files
            if candidates:
                self._active_model = candidates[0].name
                self._model_loaded = True
                logger.info("Loaded model: %s", self._active_model)
        logger.info("PipelineService ready.  Active model=%s", self._active_model)

    async def shutdown(self) -> None:
        logger.info("Shutting down PipelineService.")
        self._model_loaded = False

    # -- properties ---------------------------------------------------------

    @property
    def active_model(self) -> str | None:
        return self._active_model

    @property
    def is_model_loaded(self) -> bool:
        return self._model_loaded

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    # -- helpers: convert DB model → API dict -------------------------------

    def _user_to_dict(self, user: Any) -> dict[str, Any]:
        """Convert a User dataclass to the dict format expected by API."""
        from mdgt_edge.database.models import Fingerprint

        fingerprints = self._fp_repo.get_by_user_id(user.id)
        enrolled_fingers = [
            {
                "finger": str(fp.finger_index),
                "enrolled_at": _iso_to_timestamp(fp.enrolled_at),
                "quality_score": fp.quality_score,
            }
            for fp in fingerprints
        ]

        return {
            "id": str(user.id),
            "employee_id": user.employee_id,
            "full_name": user.full_name,
            "department": user.department,
            "role": user.role.value if hasattr(user.role, "value") else user.role,
            "is_active": user.is_active,
            "enrolled_fingers": enrolled_fingers,
            "created_at": _iso_to_timestamp(user.created_at),
            "updated_at": _iso_to_timestamp(user.updated_at),
        }

    # -- user management (SQLite) -------------------------------------------

    async def create_user(self, user_data: dict[str, Any]) -> dict[str, Any]:
        from mdgt_edge.database.models import User, UserRole

        role_str = user_data.get("role", "user")
        try:
            role = UserRole(role_str)
        except ValueError:
            role = UserRole.USER

        user = User(
            employee_id=user_data["employee_id"],
            full_name=user_data["full_name"],
            department=user_data.get("department", ""),
            role=role,
        )
        created = self._user_repo.create(user)
        return self._user_to_dict(created)

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return None
        user = self._user_repo.get_by_id(uid)
        if user is None:
            return None
        return self._user_to_dict(user)

    async def list_users(
        self,
        page: int = 1,
        limit: int = 20,
        search: str | None = None,
        department: str | None = None,
        role: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        if search:
            users = self._user_repo.search(search, active_only=True)
        elif department:
            users = self._user_repo.filter_by_department(department)
        elif role:
            from mdgt_edge.database.models import UserRole
            try:
                users = self._user_repo.filter_by_role(UserRole(role))
            except ValueError:
                users = self._user_repo.get_all(active_only=True)
        else:
            users = self._user_repo.get_all(active_only=True)

        # Apply additional filters that weren't the primary query
        if search and department:
            users = [u for u in users if u.department == department]
        if search and role:
            users = [u for u in users if u.role.value == role]

        total = len(users)
        start = (page - 1) * limit
        page_users = users[start : start + limit]
        return [self._user_to_dict(u) for u in page_users], total

    async def update_user(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return None

        user = self._user_repo.get_by_id(uid)
        if user is None:
            return None

        update_kwargs: dict[str, Any] = {}
        if "full_name" in updates and updates["full_name"] is not None:
            update_kwargs["full_name"] = updates["full_name"]
        if "department" in updates and updates["department"] is not None:
            update_kwargs["department"] = updates["department"]
        if "role" in updates and updates["role"] is not None:
            from mdgt_edge.database.models import UserRole
            try:
                update_kwargs["role"] = UserRole(updates["role"])
            except ValueError:
                pass
        if "employee_id" in updates and updates["employee_id"] is not None:
            update_kwargs["employee_id"] = updates["employee_id"]

        if update_kwargs:
            updated_user = user.with_updates(**update_kwargs)
            updated_user = self._user_repo.update(updated_user)
        else:
            updated_user = user

        return self._user_to_dict(updated_user)

    async def deactivate_user(self, user_id: str) -> bool:
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return False
        ok = self._user_repo.deactivate(uid)
        if ok:
            self._fp_repo.deactivate_by_user(uid)
        return ok

    # -- enrollment ---------------------------------------------------------

    async def enroll_user(
        self,
        user_id: str,
        finger: str,
        num_samples: int = 3,
    ) -> EnrollResult:
        async with self._lock:
            try:
                uid = int(user_id)
            except (ValueError, TypeError):
                return EnrollResult(
                    user_id=user_id, finger=finger,
                    quality_score=0.0, template_count=0,
                    success=False, message="Invalid user ID",
                )

            user = self._user_repo.get_by_id(uid)
            if user is None:
                return EnrollResult(
                    user_id=user_id, finger=finger,
                    quality_score=0.0, template_count=0,
                    success=False, message="User not found",
                )

            # Simulate capture + template extraction
            await asyncio.sleep(0.1)
            quality = round(0.75 + 0.2 * (hash(user_id + finger) % 100) / 100, 3)

            from mdgt_edge.database.models import Fingerprint
            try:
                finger_idx = int(finger)
            except (ValueError, TypeError):
                finger_idx = 0

            fp = Fingerprint(
                user_id=uid,
                finger_index=min(finger_idx, 9),
                quality_score=min(quality * 100, 100.0),
                image_hash="",
            )
            self._fp_repo.create(fp)

            template_count = self._fp_repo.count_by_user(uid)
            self._log_event(uid, user.employee_id, "enroll", "accept", quality, 100.0)

            return EnrollResult(
                user_id=user_id, finger=finger,
                quality_score=quality, template_count=template_count,
            )

    # -- verification (1:1) ------------------------------------------------

    async def verify_1to1(self, user_id: str) -> VerifyResult:
        start = time.perf_counter()
        threshold = self._settings.verify_threshold

        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            elapsed = (time.perf_counter() - start) * 1000
            return VerifyResult(False, 0.0, threshold, user_id, round(elapsed, 2))

        user = self._user_repo.get_by_id(uid)
        if user is None:
            elapsed = (time.perf_counter() - start) * 1000
            return VerifyResult(False, 0.0, threshold, user_id, round(elapsed, 2))

        fps = self._fp_repo.get_by_user_id(uid)
        if not fps:
            elapsed = (time.perf_counter() - start) * 1000
            return VerifyResult(False, 0.0, threshold, user_id, round(elapsed, 2))

        # Simulate capture + matching (will be replaced with real inference)
        await asyncio.sleep(0.05)
        score = round(0.4 + 0.55 * (hash(user_id + str(time.time_ns())) % 100) / 100, 4)
        matched = score >= threshold

        elapsed = (time.perf_counter() - start) * 1000
        decision = "accept" if matched else "reject"
        self._log_event(uid, user.employee_id, "verify", decision, score, round(elapsed, 2))

        return VerifyResult(matched, score, threshold, user_id, round(elapsed, 2))

    # -- identification (1:N) ----------------------------------------------

    async def identify_1toN(self, top_k: int | None = None) -> list[IdentifyResult]:
        top_k = top_k or self._settings.identify_top_k
        threshold = self._settings.identify_threshold

        await asyncio.sleep(0.08)
        results: list[IdentifyResult] = []

        users = self._user_repo.get_all(active_only=True)
        for user in users:
            fps = self._fp_repo.get_by_user_id(user.id)
            if not fps:
                continue
            score = round(0.3 + 0.65 * (hash(str(user.id) + str(time.time_ns())) % 100) / 100, 4)
            if score >= threshold:
                results.append(IdentifyResult(
                    user_id=str(user.id),
                    employee_id=user.employee_id,
                    full_name=user.full_name,
                    score=score,
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    # -- profiling ----------------------------------------------------------

    async def get_profiling(self) -> dict[str, Any]:
        return {
            "active_model": self._active_model,
            "model_loaded": self._model_loaded,
            "uptime_seconds": self.uptime_seconds,
            "total_users": self._user_repo.count(active_only=True),
            "total_templates": self._fp_repo.count(active_only=True),
            "total_logs": self._log_repo.count(),
        }

    # -- log access ---------------------------------------------------------

    async def get_logs(
        self,
        page: int = 1,
        limit: int = 50,
        user_id: str | None = None,
        action: str | None = None,
        decision: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        from mdgt_edge.database.models import VerificationDecision, VerificationMode

        uid = None
        if user_id:
            try:
                uid = int(user_id)
            except (ValueError, TypeError):
                pass

        mode = None
        if action:
            try:
                mode = VerificationMode(action)
            except ValueError:
                pass

        dec = None
        if decision:
            try:
                dec = VerificationDecision(decision.upper())
            except ValueError:
                pass

        offset = (page - 1) * limit
        logs = self._log_repo.query(
            user_id=uid, mode=mode, decision=dec,
            start_date=date_from, end_date=date_to,
            limit=limit, offset=offset,
        )

        log_dicts = [
            {
                "id": str(log.id),
                "timestamp": _iso_to_timestamp(log.timestamp),
                "user_id": str(log.matched_user_id) if log.matched_user_id else None,
                "employee_id": None,
                "action": log.mode.value,
                "decision": log.decision.value.lower(),
                "score": log.score,
                "latency_ms": log.latency_ms,
                "details": None,
            }
            for log in logs
        ]

        total = self._log_repo.count()
        return log_dicts, total

    async def get_stats(self) -> dict[str, Any]:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        stats = self._log_repo.get_stats(start_date=today_start)

        return {
            "enrolled_users": self._user_repo.count(active_only=True),
            "enrolled_fingers": self._fp_repo.count(active_only=True),
            "verifications_today": stats["total"],
            "identifications_today": 0,
            "acceptance_rate": stats["accept_rate"],
            "rejection_rate": round(1 - stats["accept_rate"], 4),
            "avg_latency_ms": stats["avg_latency_ms"],
            "uptime_seconds": self.uptime_seconds,
        }

    # -- internal log helper ------------------------------------------------

    def _log_event(
        self,
        user_id: int | None,
        employee_id: str | None,
        action: str,
        decision: str,
        score: float | None,
        latency_ms: float | None,
    ) -> None:
        from mdgt_edge.database.models import (
            VerificationDecision,
            VerificationLog,
            VerificationMode,
        )

        try:
            mode = VerificationMode(action)
        except ValueError:
            mode = VerificationMode.VERIFY

        try:
            dec = VerificationDecision(decision.upper())
        except ValueError:
            dec = VerificationDecision.REJECT

        log = VerificationLog(
            matched_user_id=user_id,
            mode=mode,
            score=score or 0.0,
            decision=dec,
            latency_ms=latency_ms or 0.0,
            device_id=self._settings.device_id,
        )
        try:
            self._log_repo.create(log)
        except Exception as e:
            logger.error("Failed to log event: %s", e)


# ---------------------------------------------------------------------------
# Dependency injection helper
# ---------------------------------------------------------------------------


def get_pipeline_service() -> PipelineService:
    return PipelineService.get_instance()
