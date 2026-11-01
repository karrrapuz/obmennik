import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

const api = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');
const resources = { users: 'Пользователи', loans: 'Займы', trades: 'Обмены', accounts: 'Счета', ledger: 'Проводки', readiness: 'Диагностика' };
type Resource = keyof typeof resources;
type Page = { items: Record<string, unknown>[]; next_offset: number | null };
type Overview = { counts: Record<string, number>; admin_user_id: string };
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
function isOverview(value: unknown): value is Overview {
  return record(value) && typeof value.admin_user_id === 'string' && record(value.counts)
    && Object.values(value.counts).every(count => typeof count === 'number' && Number.isSafeInteger(count) && count >= 0);
}
function isPage(value: unknown): value is Page {
  return record(value) && Array.isArray(value.items) && value.items.length <= 100 && value.items.every(record)
    && (value.next_offset === null || typeof value.next_offset === 'number' && Number.isSafeInteger(value.next_offset) && value.next_offset >= 0 && value.next_offset <= 10000);
}
const labels: Record<string, string> = {
  users: 'Пользователи', active_loans: 'Активные займы', repaid_loans: 'Погашенные',
  open_quotes: 'Котировки', executed_trades: 'Обмены', ledger_transactions: 'Операции',
  id: 'ID', user_id: 'Пользователь', revision: 'Версия', gift_id: 'Подарок', status: 'Статус',
  principal_nano: 'Выдано, TON', repayment_nano: 'Возврат, TON', balance_nano: 'Баланс, TON',
  amount_nano: 'Сумма, TON', created_at: 'Создан', due_at: 'Срок', expires_at: 'Истекает',
  autopay: 'Автоплатёж', kind: 'Тип', created_at_ns: 'Время', postings: 'Проводки',
};

function display(key: string, value: unknown): string {
  if (key.endsWith('_nano') && typeof value === 'string' && /^-?\d+$/.test(value)) {
    const negative = value.startsWith('-');
    const digits = (negative ? value.slice(1) : value).padStart(10, '0');
    const fraction = digits.slice(-9).replace(/0+$/, '');
    return `${negative ? '-' : ''}${digits.slice(0, -9)}${fraction ? '.' + fraction : ''}`;
  }
  if ((key.endsWith('_at') || key === 'created_at_ns') && value != null) {
    if (!/^\d{1,20}$/.test(String(value))) return '—';
    const seconds = key === 'created_at_ns' ? Number(BigInt(String(value)) / 1000000000n) : Number(value);
    const date = new Date(seconds * 1000);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('ru-RU');
  }
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет';
  if (typeof value === 'object' && value !== null) return JSON.stringify(value);
  return String(value ?? '—');
}

export default function AdminPanel({ token, onClose }: { token: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [resource, setResource] = useState<Resource>('users');
  const [offset, setOffset] = useState(0);
  const [revision, refresh] = useState(0);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [data, setData] = useState<Page | null>(null);
  const [diagnostics, setDiagnostics] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const node = dialog.current;
    const focus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    node?.showModal();
    return () => { node?.close(); focus?.focus(); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timer = window.setTimeout(() => controller.abort(), 30000);
    setLoading(true); setError(''); setData(null); setDiagnostics(null);
    async function request(path: string, allowUnready = false) {
      const response = await fetch(`${api}${path}`, {
        headers: { Authorization: `Bearer ${token}` }, signal: controller.signal,
        credentials: 'omit', redirect: 'error', cache: 'no-store',
      });
      const body: unknown = await response.json();
      if (!response.ok && !(allowUnready && response.status === 503 && body && typeof body === 'object' && 'checks' in body)) {
        throw new Error(response.status === 401 || response.status === 403 ? 'Доступ закрыт. Перезайдите в приложение.' : 'Не удалось загрузить данные.');
      }
      return body;
    }
    Promise.all([
      request('/api/admin/overview'),
      request(`/api/admin/${resource}${resource === 'readiness' ? '' : `?limit=25&offset=${offset}`}`, resource === 'readiness'),
    ]).then(([summary, result]) => {
      if (!active) return;
      if (!isOverview(summary)) throw new Error('Некорректный ответ сервера.');
      setOverview(summary);
      if (resource === 'readiness') {
        if (!record(result) || !record(result.checks) || typeof result.operational_ready !== 'boolean' || typeof result.live_ready !== 'boolean') throw new Error('Некорректная диагностика.');
        setDiagnostics(result);
      } else {
        if (!isPage(result)) throw new Error('Некорректный список.');
        setData(result);
      }
    }).catch(reason => { if (active) setError(reason instanceof Error && reason.name !== 'AbortError' ? reason.message : 'Время ожидания истекло.'); })
      .finally(() => { window.clearTimeout(timer); if (active) setLoading(false); });
    return () => { active = false; controller.abort(); window.clearTimeout(timer); };
  }, [token, resource, offset, revision]);
  const fields = data?.items[0] ? Object.keys(data.items[0]) : [];
  return createPortal(<dialog className="admin-panel" ref={dialog} onCancel={event => { event.preventDefault(); onClose(); }} aria-labelledby="admin-title">
    <header><div><h1 id="admin-title">Администрирование</h1><span>DEMO_TON · Только просмотр</span></div><button type="button" onClick={onClose}>Закрыть</button></header>
    <div className="admin-panel__stats">{overview && Object.entries(overview.counts).map(([key, value]) => <div key={key}><span>{labels[key] ?? key}</span><strong>{value}</strong></div>)}</div>
    <nav aria-label="Раздел администрирования">{Object.entries(resources).map(([key, title]) => <button type="button" key={key} aria-pressed={resource === key} onClick={() => { setResource(key as Resource); setOffset(0); }}>{title}</button>)}</nav>
    <div className="admin-panel__toolbar"><strong>{resources[resource]}</strong><button type="button" disabled={loading} onClick={() => refresh(value => value + 1)}>Обновить</button></div>
    {loading && <p role="status">Загрузка...</p>}
    {error && <p role="alert">{error}</p>}
    {data && <><div className="admin-panel__table" tabIndex={0} role="region" aria-label={resources[resource]}><table><thead><tr>{fields.map(key => <th scope="col" key={key}>{labels[key] ?? key}</th>)}</tr></thead><tbody>{data.items.map((item, index) => <tr key={String(item.id ?? item.user_id ?? index) + index}>{fields.map(key => <td key={key}>{display(key, item[key])}</td>)}</tr>)}</tbody></table>{data.items.length === 0 && <p>Пусто</p>}</div><footer><button type="button" disabled={loading || offset === 0} onClick={() => setOffset(value => Math.max(0, value - 25))}>Назад</button><span>{offset + (data.items.length ? 1 : 0)}–{offset + data.items.length}</span><button type="button" disabled={loading || data.next_offset === null} onClick={() => { if (data.next_offset !== null) setOffset(data.next_offset); }}>Далее</button></footer></>}
    {diagnostics && <section className="admin-panel__checks"><p>Сервис: {diagnostics.operational_ready ? 'готов' : 'требует внимания'}. Реальные операции: {diagnostics.live_ready ? 'готовы' : 'не подключены'}.</p><dl>{Object.entries((diagnostics.checks ?? {}) as Record<string, unknown>).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{display(key, value)}</dd></div>)}</dl></section>}
  </dialog>, document.body);
}
