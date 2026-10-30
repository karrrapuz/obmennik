import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import LoadingPage from '../pages/LoadingPage/LoadingPage';

type Entry = { loading: boolean; error: boolean; retry: () => void };
const Context = createContext<(key: string, entry: Entry) => void>(() => {});
const Ready = createContext(false);
export function BootProvider({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState<Record<string, Entry>>({});
  const [minimum, setMinimum] = useState(false);
  const [completed, setCompleted] = useState(false);
  useEffect(() => { const timer = setTimeout(() => setMinimum(true), 5000); return () => clearTimeout(timer); }, []);
  const [report] = useState(() => (key: string, entry: Entry) => setEntries((current) => ({ ...current, [key]: entry })));
  const initialReady = minimum && ['auth', 'inventory', 'wallet', 'loans'].every((key) => entries[key] && !entries[key].loading && !entries[key].error);
  useEffect(() => { if (initialReady) setCompleted(true); }, [initialReady]);
  const ready = completed || initialReady;
  return <Context.Provider value={report}><Ready.Provider value={ready}>{children}</Ready.Provider>{!ready && <BootScreen entries={entries} minimum={minimum} />}</Context.Provider>;
}
function BootScreen({ entries, minimum }: { entries: Record<string, Entry>; minimum: boolean }) {
  const failed = Object.values(entries).filter((entry) => entry.error);
  if (!minimum || (!failed.length && ['auth', 'inventory', 'wallet', 'loans'].some((key) => !entries[key] || entries[key].loading))) return <LoadingPage />;
  if (failed.length) return <main className="auth-error"><p role="alert">{entries.auth?.error ? 'Не удалось войти через Telegram.' : 'Не удалось загрузить данные. Повторите попытку.'}</p><button onClick={() => failed.forEach((entry) => entry.retry())}>Повторить</button></main>;
  return null;
}
export function useBootReport(key: string, loading: boolean, error: boolean, retry: () => void) {
  const report = useContext(Context);
  useEffect(() => { report(key, { loading, error, retry }); }, [report, key, loading, error, retry]);
}
export function BootContent({ children }: { children: ReactNode }) { return useContext(Ready) ? children : null; }
