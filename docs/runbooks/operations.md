# Runbook: эксплуатация и инциденты

## Алерт: растёт лаг загрузчика / `last_commit_timestamp` устарел

1. `kubectl -n proview logs deploy/proview-event-ingester | grep -E "failed|error"`.
2. В логе `insert failed, retrying` — проблема в ClickHouse: проверьте `kubectl get chi`, диск, Keeper. События копятся в Kafka и потеряны не будут, пока не исчерпано хранение топика (3–7 дней).
3. Ошибок нет, но лаг растёт — не хватает мощности: увеличьте реплики (до 24 = партиций) или включите KEDA.
4. После восстановления лаг уходит сам. Дублей не будет: токен дедупликации пачки.

## Алерт: обратное давление в collector (503)

1. Kafka недоступен или медленный: `kubectl get kafka`, метрики брокеров, ISR.
2. Нагрузка выше мощности: HPA должен добавить поды. Проверьте `kubectl get hpa` и лимиты квоты namespace.
3. SDK сам повторяет запросы при 503. Данные не теряются, пока очередь вкладки не превысила 500 событий.

## Алерт: устаревший пул баннеров

`proview_banner_pool_loaded_timestamp_seconds` не растёт — значит, недоступен PostgreSQL. Выдача продолжается из снимка. Проверьте `kubectl get cluster proview-pg` (CNPG failover) и Secret `proview-pg-app`.

## Ротация ключа токена показа

1. Добавьте новый ключ в `TOKEN_KEYS` collector, оставив старый: `k2:<new>,k1:<old>`. Выкатите collector.
2. Переключите banner-service: `TOKEN_KEY_ID=k2`, `TOKEN_SECRET=<new>`. Выкатите.
3. Через `TOKEN_MAX_AGE` (24 ч) удалите `k1` из `TOKEN_KEYS`.

## Разбор DLQ

```bash
kubectl -n proview exec -it proview-kafka-pool-0 -- bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic proview.events.dlq --from-beginning --property print.headers=true --max-messages 20
```

Заголовок `error` содержит причину. После исправления формата сообщения можно переотправить в `proview.events.v1`.

## Пересчёт агрегатов (новое измерение, ошибка в MV)

1. Новая миграция в event-ingester: новая таблица и MV.
2. Заполнение из raw за доступные 30 дней: `INSERT INTO proview_agg.<new> SELECT … FROM proview.events_raw WHERE event_time >= …`.
3. Переключение analytics на новую таблицу, удаление старой отдельной миграцией.

## Масштабирование Kafka

Увеличение партиций `proview.events.v1` (поле `kafka.topic.partitions` в values) выполняется без простоя. Порядок событий одного показа сохраняется для новых сообщений. Параллелизм загрузчика растёт вместе с числом партиций.
