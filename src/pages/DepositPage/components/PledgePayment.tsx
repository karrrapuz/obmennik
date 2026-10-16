import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import { pledgeStore } from '../services/pledgeStore';
import { useModalScrollLock } from '../../../hooks/useModalScrollLock';
import gift from '../../ExchangePage/assets/obmen_gift_active.svg';
import GiftArtwork from '../../../components/gifts/GiftArtwork/GiftArtwork';
import arrow from '../assets/gift-expand-active.svg';
import time from '../assets/zalog-gift-time.svg';
import ton from '../../../assets/ton.svg';
import close from '../../ExchangePage/components/FilterModal/assets/Union.svg';
import success from '../../ProfilePage/assets/yspeh_galoshka.svg';
import error from '../../ProfilePage/assets/oshibka_krestik.svg';
import spinner from '../assets/obrabotka-zaloga.svg';
import './PledgePayment.css';

export default function PledgePayment({ ids, onClose, onTopUp }: { ids: number[]; onClose: () => void; onTopUp: () => void }) {
  const state = useSyncExternalStore(pledgeStore.subscribe, pledgeStore.getSnapshot);
  const [selected] = useState(ids);
  const [expandedGifts, setExpandedGifts] = useState<number[]>([]);
  const [collapsed, setCollapsed] = useState(false);
  const [stage, setStage] = useState<'review' | 'pending' | 'success' | 'error'>('review');
  const [expanded, setExpanded] = useState(false);
  const [visible, setVisible] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const busy = useRef(false);
  const alive = useRef(true);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const items = state.pledges.filter((item) => selected.includes(item.gift.id));
  const quote = pledgeStore.quote(selected);
  useModalScrollLock(true);
  useEffect(() => {
    alive.current = true;
    dialog.current?.showModal();
    if (dialog.current) dialog.current.scrollTop = 0;
    let next = 0;
    const frame = requestAnimationFrame(() => { next = requestAnimationFrame(() => { if (dialog.current) dialog.current.scrollTop = 0; setVisible(true); }); });
    return () => { alive.current = false; cancelAnimationFrame(frame); cancelAnimationFrame(next); clearTimeout(timer.current); };
  }, []);
  const dismiss = () => { if (busy.current) return; clearTimeout(timer.current); setVisible(false); timer.current = setTimeout(onClose, 420); };
  const pay = async () => {
    if (busy.current || !selected.length) return;
    busy.current = true; setStage('pending');
    try { const ok = await pledgeStore.extend(selected); if (alive.current) setStage(ok ? 'success' : 'error'); }
    catch { if (alive.current) setStage('error'); }
    finally { busy.current = false; }
  };
  const count = items.length;
  const noun = count % 100 >= 11 && count % 100 <= 14 ? 'подарков' : count % 10 === 1 ? 'подарок' : count % 10 >= 2 && count % 10 <= 4 ? 'подарка' : 'подарков';
  const dates = [...new Set(items.map((item) => new Date(item.dueAt).toLocaleDateString('ru-RU')))];
  return createPortal(<dialog ref={dialog} className="pledge-pay-dialog" data-visible={visible} onCancel={(event) => { event.preventDefault(); dismiss(); }} onClick={(event) => { if (event.target === event.currentTarget) dismiss(); }} aria-label="Продлить займ">
    <div className="pledge-pay-dialog__scrim" aria-hidden="true" onClick={dismiss} />
    <section className="pledge-pay" data-stage={stage}>
      <span className="pledge-pay__handle" /><button autoFocus className="pledge-pay__close" onClick={dismiss} disabled={stage === 'pending'} aria-label="Закрыть"><img src={close} alt="" /></button>
      <h2>{stage === 'review' ? 'Продлить займ' : stage === 'pending' ? 'Обработка...' : stage === 'success' ? 'Успешно!' : 'Ошибка'}</h2>
      {stage === 'review' ? <>
        <p className="pledge-pay__subtitle">Оплачивайте проценты по займу, чтобы продолжить использование заемных средств</p>
        <div className="pledge-pay__balance"><i><span><img src={ton} alt="" /></span></i><div><small>Ваш баланс</small><strong>{state.balance.toFixed(2)}</strong></div><button onClick={onTopUp}>Пополнить</button></div>
        <div className="pledge-pay__toolbar"><div className="pledge-pay__count"><i><img src={gift} alt="" /></i>{count} {noun}</div><button aria-label={collapsed ? 'Показать подарки' : 'Скрыть подарки'} aria-expanded={!collapsed} onClick={() => setCollapsed(!collapsed)}><img src={arrow} alt="" /></button></div>
        <div className="pledge-pay__content"><div className="pledge-pay__list" data-collapsed={collapsed} inert={collapsed}>{items.map((item) => <article key={item.gift.id} data-expanded={expandedGifts.includes(item.gift.id)}>
          <div className="pledge-pay__art"><GiftArtwork gift={item.gift} /></div>
          <strong className="pledge-pay__name">{item.gift.name}</strong><div className="pledge-pay__model"><span>{item.gift.modelName ?? 'Модель'}</span><span>{item.gift.model}</span></div>
          <div className="pledge-pay__loan"><i><img src={time} alt="" /></i><div><span>Занято {item.principal.toFixed(3)} TON</span><span>до {new Date(item.dueAt).toLocaleDateString('ru-RU')}</span></div></div>
          <button className="pledge-pay__expand" aria-label={`Платеж по ${item.gift.name}`} aria-expanded={expandedGifts.includes(item.gift.id)} onClick={() => setExpandedGifts((current) => current.includes(item.gift.id) ? current.filter((id) => id !== item.gift.id) : [...current, item.gift.id])}><img src={arrow} alt="" /></button>
          <div className="pledge-pay__gift-details"><p><span>Следующий платеж</span><span>{new Date(item.dueAt).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })}</span></p><p><span>Проценты по займу</span><strong>{(item.repayment - item.principal).toFixed(3)} TON</strong></p></div>
        </article>)}
          {!items.length && <p>Подарки не выбраны</p>}
        </div><div className="pledge-pay__explanation"><strong>Вы совершаете регулярный платеж</strong><p>Ваши займы будут продлены, а следующий платеж будет запланирован в течение следующих 14 дней</p></div>
        </div>
        <footer><div className="pledge-pay__total" data-expanded={expanded}><button aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}><span>Итого к оплате</span><strong>{quote.total.toFixed(3)} TON</strong><img src={arrow} alt="" /></button><div><p><span>Проценты по займу</span><span>{quote.interest.toFixed(3)} TON</span></p><p><span>Комиссия сети</span><span>{quote.fee.toFixed(2)} TON</span></p></div></div><button className="pledge-pay__action" disabled={!items.length} onClick={pay}>Оплатить</button></footer>
      </> : <div className="pledge-pay__result"><div className="pledge-pay__result-icon"><img className={stage === 'pending' ? 'pledge-pay__spinner' : ''} src={stage === 'pending' ? spinner : stage === 'success' ? success : error} alt="" /></div><p role="status">{stage === 'pending' ? 'Пожалуйста подождите...' : stage === 'success' ? `Вы успешно продлили займ до ${dates.join(', ')}!` : 'Недостаточно средств'}</p>{stage !== 'pending' && <button className="pledge-pay__action" onClick={() => stage === 'error' ? setStage('review') : dismiss()}>{stage === 'success' ? 'Вернуться назад' : 'Попробовать снова'}</button>}</div>}
    </section>
  </dialog>, document.body);
}
