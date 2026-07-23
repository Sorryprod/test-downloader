import { useCallback, useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";

import {
  getJob,
  startDownloadJob,
  subscribeJobEvents,
  type JobProgress,
} from "../api/client";

const ACTIVE_STATUSES = new Set(["pending", "running", "waiting_rate_limit"]);

export function Layout() {
  const location = useLocation();
  const [progress, setProgress] = useState<JobProgress | null>(null);
  const [isStarting, setIsStarting] = useState(false);
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

  const isBusy =
    isStarting || (progress !== null && ACTIVE_STATUSES.has(progress.status));

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

        <button
          type="button"
          className="btn btn-primary"
          onClick={handleDownload}
          disabled={isBusy}
        >
          {isBusy ? "Скачивание…" : "Скачать данные"}
        </button>
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
                <> (всего за сессию: {progress.total_downloaded})</>
              )}
            </p>
          )}
          {error && <p className="error-text">{error}</p>}
        </section>
      )}

      <main className="page">
        <Outlet context={{ refreshToken: progress?.total_downloaded ?? 0 }} />
      </main>
    </div>
  );
}
