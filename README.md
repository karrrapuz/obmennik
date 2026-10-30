| Папка / файл | Назначение |
| --- | --- |
| `src/main.tsx`, `src/App.tsx` | Точка входа, инициализация Telegram, загрузочный экран |
| `src/pages/HomePage/` | Переключение разделов, общий баланс, открытие пополнения |
| `src/components/layout/PageHeader/` | Общий хедер обмена и залога, баланс и плюсик |
| `src/components/layout/PageFooter/` | Нижняя навигация и её стили |
| `src/components/layout/AppShell/` | Внешний контейнер приложения |
| `src/components/gifts/GiftArtwork/` | Модель, фон и символ подарка |
| `src/components/feedback/SlideNotice/` | Анимация уведомлений |
| `src/hooks/` | Анимация баланса, блокировка прокрутки за модалкой |
| `src/styles/` | Глобальные стили, оболочка, общий эффект нажатия |
| `src/assets/` | Общие аватар, TON и плюсик |
| `src/services/telegram.ts` | Цвета Telegram, разворачивание, запрет свайпа сворачивания |
| `src/pages/ExchangePage/` | Обмен; styles разбиты по блокам, components содержит модалки |
| `src/pages/DepositPage/` | Залог, оформление, продление, информация о займе |
| `src/pages/ProfilePage/` | Профиль, пополнение, вывод, рефералка |
| `src/pages/LoadingPage/` | Стартовый экран |
| `public/gifts/` | Изображения демонстрационного каталога |
| `scripts/` | Импорт и проверка демонстрационного каталога |
| `src/auth/` | Общая сессия Telegram и текущий пользователь |
| `src/boot/` | Единый стартовый экран до окончания загрузки данных |
| `src/loans/` | Серверные условия займов и согласование снимков состояния |
| `src/services/snapshotRevision.ts` | Защита от устаревших ответов API |
| `backend/app/loans.py`, `backend/app/loan_models.py` | Выдача, погашение, продление и автоплатёж займов |
| `backend/app/ledger.py` | Общий транзакционный денежный учёт |
| `docs/DEMO_LOANS.md` | Правила и ограничения демонстрационных займов |
| `backend/app/` | Авторизация, пользователи и общий тестовый инвентарь |
| `backend/migrations/` | Версии схемы базы данных |
| `backend/tests/` | Проверки авторизации, владения и операций тестового инвентаря |
| `backend/data/` | Серверные шаблоны тестовых подарков |
| `src/inventory/` | Общий инвентарь и синхронизация разделов с API |
| `src/wallet/` | Сохраняемый тестовый баланс, точные суммы и история |
| `docs/DEMO_WALLET.md` | API тестового баланса и правила денежного учёта |
| `render.yaml` | Настройки бесплатного тестового API на Render |
| `docs/AUTH_DEPLOYMENT.md` | Запуск сервера и подключение Neon, Render и Vercel |
| `docs/BACKEND_PLAN.md` | План бэкенда, критерии этапов и замечания ревьюеров |
