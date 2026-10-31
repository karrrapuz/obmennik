| Папка / файл | Назначение |
| --- | --- |
| `src/main.tsx`, `src/App.tsx` | Точка входа, инициализация Telegram, загрузочный экран |
| `src/pages/HomePage/` | Переключение разделов, общий баланс, открытие пополнения |
| `src/components/layout/PageHeader/` | Общий хедер обмена и залога, баланс и плюсик |
| `src/components/layout/PageFooter/` | Нижняя навигация и её стили |
| `src/components/layout/AppShell/` | Внешний контейнер приложения |
| `src/components/gifts/GiftArtwork/` | Модель, фон и символ подарка |
| `src/services/giftPresentation.ts`, `backend/app/gift_presentation.py` | Декоративные фоны без изменения настоящих атрибутов и стоимости подарков |
| `src/components/feedback/SlideNotice/` | Анимация уведомлений |
| `src/hooks/` | Анимация баланса, блокировка прокрутки за модалкой |
| `src/styles/` | Глобальные стили, оболочка, общий эффект нажатия |
| `src/assets/` | Общие аватар, TON и плюсик |
| `src/services/telegram.ts` | Цвета Telegram, разворачивание, запрет свайпа сворачивания |
| `src/pages/ExchangePage/` | Обмен; styles разбиты по блокам, components содержит модалки |
| `src/pages/ExchangePage/hooks/useTradeQuote.ts` | Котировка API, срок цены и восстановление подтверждения обмена |
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
| `backend/app/gift_provider.py` | Заменяемая заглушка подарков и режим отключения интеграции |
| `backend/app/pricing.py` | Точные цены, версия источника и наценка |
| `backend/app/trades.py`, `backend/app/trade_models.py` | Серверные котировки и атомарный обмен |
| `docs/DEMO_TRADES.md` | Тарифы, API обмена, срок котировки и ограничения |
| `docs/GIFT_PROVIDER.md` | Настройка заглушки и порядок подключения реальных подарков |
| `docs/DEMO_LOANS.md` | Правила и ограничения демонстрационных займов |
| `backend/app/` | Авторизация, пользователи и общий тестовый инвентарь |
| `backend/migrations/` | Версии схемы базы данных |
| `backend/tests/` | Проверки авторизации, владения и операций тестового инвентаря |
| `backend/data/` | Серверные шаблоны тестовых подарков |
| `backend/scripts/telegram_catalog.py`, `backend/scripts/telegram_login.ps1` | Локальный вход Telethon и проверка каталога без торговых операций |
| `backend/requirements-telegram.txt`, `backend/telegram.credentials.example` | Необязательные зависимости и шаблон локальных ключей Telegram |
| `docs/TELEGRAM_CATALOG.md` | Подготовка, команды и защита пользовательской сессии |
| `backend/scripts/telegram_import.py` | Возобновляемый импорт публичных типов, моделей, символов, фонов и изображений Telegram |
| `backend/app/catalog.py`, `backend/app/grant_models.py` | Проверка каталога и однократные сезонные примеры без финансовой стоимости |
| `src/services/telegramCatalog.ts` | Загрузка каталога Telegram и варианты фильтров |
| `backend/app/catalog_index.py`, `docs/CATALOG_API.md` | Публичный поиск коллекций и атрибутов по устойчивым ID с пагинацией |
| `backend/app/catalog_labels.py`, `backend/data/catalog-labels.json`, `public/gifts/telegram/labels.json` | Общие описательные названия подарков без официального имени |
| `scripts/check-catalog-filters.mjs` | Полнота вариантов фильтров, коллизии имён и совместимость старого инвентаря |
| `backend/scripts/telegram_prices.py` | Локальное чтение рыночных предложений в TON без пересчёта Stars |
| `backend/app/market_prices.py`, `backend/data/market-prices.json` | Проверка справочных рыночных цен коллекций для API |
| `src/services/telegramPrices.ts`, `src/hooks/useTelegramPrices.ts`, `src/components/gifts/GiftPrice.tsx` | Загрузка и единое отображение TON-ориентиров, проверка актуальности |
| `public/gifts/telegram/prices.json`, `docs/MARKET_PRICES.md` | Публичный снимок цен и правила его обновления |
| `public/gifts/telegram/`, `backend/data/catalog-telegram.json` | Публичные изображения, атрибуты и серверные карточки Telegram |
| `src/inventory/` | Общий инвентарь и синхронизация разделов с API |
| `src/wallet/` | Сохраняемый тестовый баланс, точные суммы и история |
| `docs/DEMO_WALLET.md` | API тестового баланса и правила денежного учёта |
| `render.yaml` | Настройки бесплатного тестового API на Render |
| `docs/AUTH_DEPLOYMENT.md` | Запуск сервера и подключение Neon, Render и Vercel |
| `docs/BACKEND_PLAN.md` | План бэкенда, критерии этапов и замечания ревьюеров |
