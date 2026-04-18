"""Background embedding extraction worker.

Enrollment saves the raw image + a placeholder DB row synchronously (fast),
then enqueues a job here.  This worker thread consumes the queue, runs the
inference model, updates the DB row with the encrypted embedding, and adds
the vector to the live FAISS index.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingJob:
    """One pending inference job for a freshly enrolled sample."""

    fp_id: int
    raw: bytes
    width: int
    height: int


class EmbeddingWorker(threading.Thread):
    """Single-consumer queue worker that runs inference off the UI thread."""

    def __init__(
        self,
        inference_provider: Callable[[], Optional[Any]],
        fp_repo: Any,
        faiss_index: Any,
        preprocess_fn: Callable[[bytes, int, int], np.ndarray],
        on_done: Optional[Callable[[int, np.ndarray], None]] = None,
        on_error: Optional[Callable[[int, Exception], None]] = None,
    ) -> None:
        super().__init__(name="EmbeddingWorker", daemon=True)
        self._inference_provider = inference_provider
        self._fp_repo = fp_repo
        self._faiss = faiss_index
        self._preprocess = preprocess_fn
        self._on_done = on_done
        self._on_error = on_error
        self._q: queue.Queue[Optional[EmbeddingJob]] = queue.Queue()
        self._stop_evt = threading.Event()
        self._faiss_lock = threading.Lock()

    @property
    def pending(self) -> int:
        """Approximate number of queued jobs (not including the one in flight)."""
        return self._q.qsize()

    def enqueue(self, fp_id: int, raw: bytes, width: int, height: int) -> None:
        """Queue a new fingerprint for embedding extraction."""
        self._q.put(EmbeddingJob(fp_id=fp_id, raw=raw, width=width, height=height))
        logger.debug("queued fp_id=%s (pending=%d)", fp_id, self._q.qsize())

    def set_faiss_index(self, faiss_index: Any) -> None:
        """Swap the FAISS index reference (e.g. after a rebuild)."""
        with self._faiss_lock:
            self._faiss = faiss_index

    def stop(self, timeout: float = 3.0) -> None:
        """Signal the worker to exit and wait for it to finish."""
        self._stop_evt.set()
        self._q.put(None)
        if self.is_alive():
            self.join(timeout=timeout)

    def run(self) -> None:
        logger.info("EmbeddingWorker started")
        while not self._stop_evt.is_set():
            try:
                job = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            if job is None:
                break
            self._process(job)
        logger.info("EmbeddingWorker stopped")

    def _process(self, job: EmbeddingJob) -> None:
        inference = self._inference_provider()
        if inference is None:
            logger.warning(
                "no inference engine loaded; fp_id=%s left without embedding",
                job.fp_id,
            )
            if self._on_error is not None:
                self._on_error(job.fp_id, RuntimeError("no inference engine"))
            return

        try:
            tensor = self._preprocess(job.raw, job.width, job.height)
            embedding = inference.infer_image(tensor)

            fp = self._fp_repo.get_by_id(job.fp_id)
            if fp is None:
                logger.warning("fp_id=%s disappeared from DB before embedding", job.fp_id)
                return
            updated = fp.with_updates(embedding_enc=embedding.tobytes())
            self._fp_repo.update(updated)

            with self._faiss_lock:
                self._faiss.add(embedding, job.fp_id)

            logger.info(
                "fp_id=%s embedded (norm=%.4f, remaining=%d)",
                job.fp_id,
                float(np.linalg.norm(embedding)),
                self._q.qsize(),
            )
            if self._on_done is not None:
                self._on_done(job.fp_id, embedding)
        except Exception as exc:
            logger.exception("embedding failed for fp_id=%s", job.fp_id)
            if self._on_error is not None:
                self._on_error(job.fp_id, exc)
