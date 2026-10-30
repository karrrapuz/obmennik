# Размещение авторизации

## Бесплатный тестовый вариант

- Frontend: текущий Vercel-проект.
- Backend: Render Free, конфигурация `render.yaml` в репозитории.
- Database: Neon Free PostgreSQL. Локально можно SQLite, на Render она непригодна:
  файлы стираются при перезапуске.

Render Free засыпает через 15 минут без запросов. Пробуждение может занять
около минуты. Это тестовый вариант; на фронте предусмотрено ожидание сервера.
У Neon Free есть лимиты ресурсов, но нет фиксированного 30-дневного срока
как у бесплатной базы Render. Проверено по официальным страницам 30.10.2026:
https://render.com/docs/free и https://neon.com/pricing.

## Шаги владельца аккаунта

1. Войти/зарегистрироваться на https://console.neon.tech через свой GitHub.
2. Создать Free-проект `giftmoney`, взять PostgreSQL connection string с SSL.
   Пароль базы хранить в секретах, не в Git и не в чате.
3. Войти на https://dashboard.render.com через свой аккаунт.
4. New -> Blueprint -> `karrrapuz/obmennik` -> ветка с реализацией.
5. Перед запуском задать TELEGRAM_BOT_TOKEN из локального backend/.env и
   DATABASE_URL из Neon. Проверить план Free, не подключать платные ресурсы.
6. Дождаться health endpoint `https://<render-host>/api/health` со status ok.
7. В Vercel Settings -> Environment Variables добавить VITE_API_URL со значением
   `https://<render-host>` (без /api). Пересобрать frontend.
8. Открыть приложение именно из тестового бота: токен сервера должен принадлежать
   тому же боту. Проверить имя/фото, профиль, переключение вкладок, перезагрузку.

Без входа владельца в Neon/Render размещение ещё не завершено.
Не публикуйте авторизующий frontend до готовности API и VITE_API_URL:
иначе Telegram-вход будет показывать ошибку.

## Локальный запуск

Из корня проекта:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
```

Из backend:

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:application --factory --host 127.0.0.1 --port 8000
```

В другом терминале из корня: `npm ci`, затем `npm run dev`.
Vite проксирует /api на localhost:8000. Браузер без Telegram запускает demo-профиль;
это не серверный вход и не доступ к защищённым API.

Тесты: `backend/.venv/Scripts/python.exe -m pytest backend/tests -q`.

## Границы этого этапа

POST /api/auth/telegram проверяет HMAC, структуру и свежесть initData (5 минут,
допуск часов 30 секунд). Один подписанный запуск повторно выдаёт ту же сессию;
отозванный/просроченный запуск не восстанавливает её. Срок сессии — сутки от
auth_date. После выхода нужно заново открыть Mini App. Данные запуска являются
учётными данными: не логировать и не передавать посторонним.

Bearer хранится только в памяти вкладки; в БД хранится его SHA-256.
GET /api/me защищён; POST /api/auth/logout отзывает текущую сессию.
initData и бот-токен не возвращаются API и не печатаются в логах.
photo_url может отсутствовать из-за настроек приватности; тогда видны инициалы.

Денежные операции и инвентарь всё ещё демо. Авторизация сама по себе не делает
пополнение, обмен и займы серверными операциями.
