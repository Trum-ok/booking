# Booking service

Стек: **FastAPI** (async) + **TaskIQ** + **Redis** (broker/result backend) +
**PostgreSQL** (SQLAlchemy 2.0 async, миграции через Alembic).

## API

| Метод и путь            | Назначение                                                                                                                |
|-------------------------|---------------------------------------------------------------------------------------------------------------------------|
| `POST /bookings`        | Создать бронь (`name`, `datetime`, `service_type`) → `201`, статус `pending`                                              |
| `GET /bookings/{id}`    | Статус брони (`pending` / `confirmed` / `failed`); `404`, если нет                                                        |
| `GET /bookings`         | Список с фильтром `?status=` и keyset-пагинацией `?limit=&cursor=` (в ответе `next_cursor`, `null` на последней странице) |
| `DELETE /bookings/{id}` | Отмена брони — только в статусе `pending`, иначе `409`; `404`, если нет                                                   |

## Запуск сервиса

Нужен только Docker. Поднять весь стек одной командой:

```bash
docker compose up --build
```

Команда поднимает `postgres`, `redis`, прогоняет миграции (сервис `migrate`),
затем стартует `api` и `worker`.

- API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>
- Healthcheck: <http://localhost:8000/health>

Переменные окружения в `.env` (шаблон в [`.env.example`](.env.example)).
В Docker значения берутся из `docker-compose.yaml`, файл `.env` для compose не обязателен.

### Пример

```bash
# создать бронь
curl -X POST http://localhost:8000/bookings \
  -H 'Content-Type: application/json' \
  -d '{"name": "Alice", "datetime": "2030-01-01T10:00:00+00:00", "service_type": "haircut"}'

# проверить статус (через мгновение станет confirmed или failed)
curl http://localhost:8000/bookings/<id>
```

## Запуск тестов

Поднимать стек сервиса (`docker-compose up`) для тестов не нужно — Postgres поднимает сам `testcontainers`, очередь
работает на in-memory брокере TaskIQ. Требуется только доступный Docker-демон:

```bash
uv sync
make test          # или: uv run pytest
```

## Локальная разработка

Инфраструктура в Docker, приложение с авто-перезагрузкой:

```bash
make dev           # postgres + redis в Docker, alembic upgrade, uvicorn --reload
make worker        # в отдельном терминале TaskIQ воркер
```

Линт и типы:

```bash
make lint
```

## Технические решения

### Почему FastAPI + TaskIQ

В ТЗ async-связка FastAPI + TaskIQ отмечена как плюс, и она органична: весь путь запроса — асинхронный (FastAPI →
SQLAlchemy async/asyncpg), а TaskIQ — нативно async-очередь, в отличие от синхронного Celery. Redis выступает и
брокером, и result backend. Это убирает смешение sync/async-кода и лишние пулы потоков.

### Структура задачи

`POST /bookings` создаёт строку в статусе `pending` и сразу ставит задачу
`confirm_booking(booking_id)` в очередь. Воркер:

1. блокирует строку (`SELECT ... FOR UPDATE`);
2. имитирует вызов внешнего сервиса (с вероятностью `CONFIRM_FAILURE_RATE`
   бросает исключение);
3. при успехе → `confirmed` + mock-уведомление в лог;
4. при сбое → retry с экспоненциальным backoff (`SmartRetryMiddleware`);
   после исчерпания попыток статус становится `failed`.

Бизнес-логика вынесена в чистую функцию `process_confirmation(...)`, а
taskiq-обёртка лишь вычисляет «последняя ли это попытка» из контекста задачи —
это делает логику тестируемой без поднятого брокера.

**Известное ограничение (dual-write):** `POST /bookings` сначала коммитит
строку, затем ставит задачу в очередь — это две отдельные операции. Если
постановка в очередь упадёт (например, Redis недоступен), клиент получит `500`,
а бронь останется в `pending` без обработки: автоматической реконсиляции нет.
В проде это решалось бы transactional outbox или периодическим добором
«висящих» `pending`; для объёма задания осознанно опущено.

### Идемпотентность

Задача обрабатывает только брони в статусе `pending`: при повторной доставке
или повторном запуске над уже `confirmed`/`failed`/удалённой бронью она делает
ранний выход — не создаёт дубль, не перетирает терминальный статус и не шлёт
повторное уведомление. Блокировка строки исключает гонку между параллельными
воркерами.

### Тесты

Тесты идут против **настоящего Postgres** — того же движка, что и в проде, — который поднимает `testcontainers`. Это
сознательный выбор: на SQLite ключевые для сервиса вещи не проверяются по-настоящему (`SELECT ... FOR UPDATE` там no-op,
а нативный `Enum` подменяется на `VARCHAR`).

Требование ТЗ «тесты запускаются без поднятого Docker, `pytest` из корня» трактуется как «не нужно вручную поднимать
стек сервиса»: `testcontainers` сам управляет жизненным циклом контейнера, прогон — по-прежнему одной командой `pytest`.
Очередь при этом подменяется на `InMemoryBroker` (выполняет задачи инлайн), Redis для тестов не нужен.

Покрытие: все 4 эндпоинта (happy path + граничные кейсы — 404/409/422, фильтр и пагинация) и логика воркера с моком
внешнего вызова (успех, перманентный сбой, retry, идемпотентность).

### Прочее

- **Structured logging**: все логи — в JSON (`app/core/logging.py`), события задачи
  снабжены `event`/`booking_id`.
- **Rate limiting**: fixed-window по IP на Redis для `POST /bookings`
  (`RATE_LIMIT_*`), в тестах отключается флагом.

## Переменные окружения

| Переменная                  | Назначение                        | По умолчанию               | 
|-----------------------------|-----------------------------------|----------------------------|
| `DATABASE_URL`              | DSN PostgreSQL (asyncpg)          | см. `.env.example`         |
| `REDIS_URL`                 | Redis для TaskIQ                  | `redis://localhost:6379/0` |
| `CONFIRM_FAILURE_RATE`      | Вероятность сбоя внешнего сервиса | `0.15`                     |
| `CONFIRM_MAX_RETRIES`       | Максимум попыток подтверждения    | `5`                        |
| `CONFIRM_RETRY_DELAY`       | Базовая задержка backoff, сек     | `1.0`                      |
| `RATE_LIMIT_TIMES`          | Запросов на окно                  | `10`                       |
| `RATE_LIMIT_WINDOW_SECONDS` | Длина окна, сек                   | `60`                       |
| `LOG_LEVEL`                 | Уровень логирования               | `INFO`                     |
