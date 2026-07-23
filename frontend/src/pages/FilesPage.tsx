import { useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";

import {
  calculateStats,
  listFiles,
  type CalculateResponse,
  type FileItem,
} from "../api/client";

type OutletContext = {
  refreshToken: number;
  activeJobId: number | null;
};

type SelectionMode = "none" | "page" | "all" | "session";

function formatDateTime(value: string): string {
  const date = new Date(value);
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "medium",
    timeZone: "Asia/Novosibirsk",
  }).format(date);
}

export function FilesPage() {
  const { refreshToken, activeJobId } = useOutletContext<OutletContext>();
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [items, setItems] = useState<FileItem[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [selectionMode, setSelectionMode] = useState<SelectionMode>("none");
  const [stats, setStats] = useState<CalculateResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isCalculating, setIsCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (nextPage: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await listFiles(nextPage, pageSize);
      setItems(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
      setPage(data.page);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void load(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshToken]);

  const pageIds = useMemo(() => items.map((item) => item.id), [items]);
  const isPageFullySelected =
    selectionMode !== "all" &&
    selectionMode !== "session" &&
    pageIds.length > 0 &&
    pageIds.every((id) => selectedIds.has(id));

  const toggleOne = (id: number) => {
    setSelectionMode("none");
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const togglePage = () => {
    setSelectionMode("page");
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (isPageFullySelected) {
        pageIds.forEach((id) => next.delete(id));
      } else {
        pageIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const toggleAllCatalog = () => {
    const enable = selectionMode !== "all";
    setSelectionMode(enable ? "all" : "none");
    setSelectedIds(enable ? new Set(pageIds) : new Set());
  };

  const toggleSession = () => {
    if (!activeJobId) {
      setError("Нет активной сессии скачивания — сначала запустите «Скачать данные»");
      return;
    }
    const enable = selectionMode !== "session";
    setSelectionMode(enable ? "session" : "none");
    setSelectedIds(new Set());
    setError(null);
  };

  const handleCalculate = async () => {
    if (selectionMode === "none" && selectedIds.size === 0) {
      setError("Выберите хотя бы один файл");
      return;
    }
    if (selectionMode === "session" && !activeJobId) {
      setError("Нет job_id сессии для расчёта");
      return;
    }

    setIsCalculating(true);
    setError(null);
    try {
      const result = await calculateStats({
        file_ids:
          selectionMode === "all" || selectionMode === "session"
            ? []
            : Array.from(selectedIds),
        select_all: selectionMode === "all",
        select_session: selectionMode === "session",
        job_id: selectionMode === "session" ? activeJobId : null,
      });
      setStats(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsCalculating(false);
    }
  };

  const selectionLabel =
    selectionMode === "all"
      ? `все в каталоге (${total})`
      : selectionMode === "session"
        ? `все за сессию #${activeJobId}`
        : String(selectedIds.size);

  const digitKeys = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
  const bulkSelected = selectionMode === "all" || selectionMode === "session";

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h1>Скачанные файлы</h1>
          <p className="lead">Сортировка по времени скачивания (новые сверху).</p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleCalculate}
          disabled={isCalculating || total === 0}
        >
          {isCalculating ? "Считаем…" : "Произвести расчёты"}
        </button>
      </div>

      <div className="selection-bar">
        <label>
          <input
            type="checkbox"
            checked={isPageFullySelected}
            onChange={togglePage}
            disabled={items.length === 0 || bulkSelected}
          />
          Все на странице
        </label>
        <label>
          <input
            type="checkbox"
            checked={selectionMode === "all"}
            onChange={toggleAllCatalog}
            disabled={total === 0}
          />
          Вообще все ({total})
        </label>
        <label>
          <input
            type="checkbox"
            checked={selectionMode === "session"}
            onChange={toggleSession}
            disabled={!activeJobId}
          />
          Все за сессию{activeJobId ? ` (#${activeJobId})` : ""}
        </label>
        <span className="muted">Выбрано: {selectionLabel}</span>
      </div>

      {error && <p className="error-text">{error}</p>}
      {isLoading && <p className="muted">Загрузка…</p>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th></th>
              <th>Имя файла</th>
              <th>Сессия</th>
              <th>Время скачивания (НСК)</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={bulkSelected || selectedIds.has(item.id)}
                    onChange={() => toggleOne(item.id)}
                    disabled={bulkSelected}
                  />
                </td>
                <td>
                  <code>{item.filename}</code>
                </td>
                <td className="muted">{item.job_id ?? "—"}</td>
                <td>{formatDateTime(item.downloaded_at)}</td>
              </tr>
            ))}
            {!isLoading && items.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  Файлов пока нет — сначала выполните скачивание.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <button
          type="button"
          className="btn"
          disabled={page <= 1}
          onClick={() => void load(page - 1)}
        >
          Назад
        </button>
        <span>
          Стр. {totalPages === 0 ? 0 : page} из {totalPages} (всего {total})
        </span>
        <button
          type="button"
          className="btn"
          disabled={totalPages === 0 || page >= totalPages}
          onClick={() => void load(page + 1)}
        >
          Вперёд
        </button>
      </div>

      {stats && (
        <section className="stats">
          <h2>Общая статистика ({stats.files_processed} файл.)</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {digitKeys.map((digit) => (
                    <th key={digit}>{digit}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  {digitKeys.map((digit) => (
                    <td key={digit}>{stats.overall[digit] ?? 0}</td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>

          <h2>Статистика по файлам</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Файл</th>
                  {digitKeys.map((digit) => (
                    <th key={digit}>{digit}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {stats.per_file.map((row) => (
                  <tr key={row.file_id}>
                    <td>
                      <code>{row.filename}</code>
                    </td>
                    {digitKeys.map((digit) => (
                      <td key={digit}>{row.counts[digit] ?? 0}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </section>
  );
}
