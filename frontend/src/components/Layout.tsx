import { useCallback, useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";

import {
  getJob,
  pauseDownloadJob,
  resumeDownloadJob,
  startDownloadJob,
  subscribeJobEvents,
  type JobProgress,
} from "../api/client";

const ACTIVE_STATUSES = new Set(["pending", "running", "waiting_rate_limit"]);

export function Layout() {
  const location = useLocation();
  const [progress, setProgress] = useState<JobProgress | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isPausing, setIsPausing] = useState(false);
  const [isResuming, setIsResuming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unsubscribeRef = useRef<(() => void) | null>(null);

  const attachToJob = useCallback((jobId: number) => {
    unsubscribeRef.current?.();
    unsubscribeRef.current = subscribeJobEvents(
      jobId,
      (next) => {
        setProgress(next);
        setError(next.error);
      },
      (err) => setError(err.message),
    );
  }, []);

  useEffect(() => {
    return () => unsubscribeRef.current?.();
  }, []);

  const handleDownload = async () => {
    if (progress && ACTIVE_STATUSES.has(progress.status)) {
      return;
    }

    setIsStarting(true);
    setError(null);
    try {
      const created = await startDownloadJob();
      const current = await getJob(created.job_id);
      setProgress(current);
      attachToJob(created.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsStarting(false);
    }
  };

  const handlePause = async () => {
    if (!progress || !ACTIVE_STATUSES.has(progress.status)) {
      return;
    }
    setIsPausing(true);
    setError(null);
    try {
      const updated = await pauseDownloadJob(progress.job_id);
      setProgress(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsPausing(false);
    }
  };

  const handleResume = async () => {
    if (!progress || progress.status !== "paused") {
      return;
    }
    setIsResuming(true);
    setError(null);
    try {
      const updated = await resumeDownloadJob(progress.job_id);
      setProgress(updated);
      attachToJob(updated.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsResuming(false);
    }
  };

  const isBusy =
    isStarting || (progress !== null && ACTIVE_STATUSES.has(progress.status));
  const canPause = Boolean(progress && ACTIVE_STATUSES.has(progress.status));
  const canResume = progress?.status === "paused";

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">FD</span>
          <div>
            <p className="brand-title">Files Downloader</p>
            <p className="brand-subtitle">скачивание и анализ каталога</p>
          </div>
        </div>

        <nav className="nav">
          <Link className={location.pathname === "/" ? "active" : ""} to="/">
            Скачивание
          </Link>
          <Link
            className={location.pathname.startsWith("/files") ? "active" : ""}
            to="/files"
          >
            Файлы и расчёты
          </Link>
        </nav>

        <div className="topbar-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleDownload}
            disabled={isBusy || canResume}
          >
            {isBusy ? "Скачивание…" : "Скачать данные"}
          </button>
          <button
            type="button"
            className="btn"
            onClick={handlePause}
            disabled={!canPause || isPausing}
          >
            {isPausing ? "Пауза…" : "Стоп"}
          </button>
          <button
            type="button"
            className="btn btn-accent"
            onClick={handleResume}
            disabled={!canResume || isResuming}
          >
            {isResuming ? "Продолжаем…" : "Продолжить"}
          </button>
        </div>
      </header>

      {(progress || error) && (
        <section className="status-panel" aria-live="polite">
          {progress?.started_at_nsk && (
            <p>
              Старт процесса: <strong>{progress.started_at_nsk}</strong>
            </p>
          )}
          {progress && progress.names_received > 0 && (
            <p>
              Получено <strong>{progress.names_received}</strong> названий файлов,
              скачиваю / скачано{" "}
              <strong>
                {progress.downloaded_in_batch} из {progress.names_received}
              </strong>
            </p>
          )}
          {progress && (
            <p className="status-message">
              Статус: <code>{progress.status}</code> — {progress.message}
              {progress.total_downloaded > 0 && (
                <> (уникальных за сессию: {progress.total_downloaded})</>
              )}
            </p>
          )}
          {error && <p className="error-text">{error}</p>}
        </section>
      )}

      <main className="page">
        <Outlet
          context={{
            refreshToken: progress?.total_downloaded ?? 0,
            activeJobId: progress?.job_id ?? null,
          }}
        />
      </main>
    </div>
  );
}
