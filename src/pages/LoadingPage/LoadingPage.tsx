import spinner from '../DepositPage/assets/obrabotka-zaloga.svg';
import './LoadingPage.css';

export default function LoadingPage() {
  return <main className="loading-page" aria-label="Загрузка приложения" aria-busy="true">
    <div className="loading-page__spinner"><img src={spinner} alt="" /></div>
    <p className="loading-page__title" role="status">Загрузка<span className="loading-page__dots" aria-hidden="true">...</span></p>
    <p className="loading-page__caption">Закупаем подарки...</p>
    <span className="loading-page__year">2026</span>
  </main>;
}
