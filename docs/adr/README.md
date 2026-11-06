# Architecture Decision Records

Каждое техническое решение ProView: контекст, решение, обоснование, рассмотренные альтернативы и почему они не выбраны, последствия и условие пересмотра.

Источник: `tools/adr_data.py` → `python tools/gen_adr.py`.

| № | Решение | Альтернативы |
|---|---|---|
| [0001](0001-go-for-services.md) | Go для всех серверных сервисов | Rust, Java/Kotlin (Spring/Quarkus), Node.js |
| [0002](0002-stdlib-http.md) | net/http стандартной библиотеки вместо веб-фреймворка | gin / echo / chi, fasthttp / fiber, gRPC |
| [0003](0003-kafka.md) | Apache Kafka как буфер и журнал событий | Прямая вставка в ClickHouse из collector, ClickHouse async_insert, RabbitMQ, NATS JetStream, Redpanda, Apache Pulsar |
| [0004](0004-franz-go.md) | Клиент Kafka: franz-go | confluent-kafka-go, IBM/sarama, segmentio/kafka-go |
| [0005](0005-clickhouse.md) | ClickHouse как аналитическое хранилище | Apache Druid / Pinot, PostgreSQL + TimescaleDB, Elasticsearch/OpenSearch, BigQuery / Snowflake |
| [0006](0006-own-ingester.md) | Собственный Go-загрузчик Kafka → ClickHouse | Kafka table engine ClickHouse + MV, Kafka Connect + ClickHouse Sink, Vector / Fluent Bit, ClickPipes (ClickHouse Cloud) |
| [0007](0007-aggregates-materialized-views.md) | База-агрегатор: MV в AggregatingMergeTree внутри ClickHouse | Отдельная БД-агрегатор (PostgreSQL) + пакетная джоба, Агрегация в потоке (Kafka Streams / Flink), Только сырые данные + projections, SummingMergeTree |
| [0008](0008-delivery-semantics.md) | Семантика доставки: at-least-once + идемпотентная вставка | Exactly-once транзакции Kafka + Connect EOS, Синхронный ответ после ack Kafka, ReplacingMergeTree по event_id, At-most-once |
| [0009](0009-banner-pool-postgres-snapshot.md) | Пул баннеров: PostgreSQL + неизменяемый снимок в памяти | Запрос в PostgreSQL на каждый показ, Redis как основное хранилище, Конфигурационный файл / ConfigMap, LISTEN/NOTIFY для мгновенного обновления |
| [0010](0010-impression-token.md) | Подписанный HMAC-токен показа | JWT, Реестр показов в Redis, Без проверки |
| [0011](0011-event-format-json.md) | Формат событий: версионированный JSON с контрактными тестами | Protobuf + Schema Registry, Avro + Schema Registry, MessagePack/CBOR |
| [0012](0012-dashboard-stack.md) | Админка: ES-модули + ECharts, встроенные в Go-бинарник | React/Vite SPA, Grafana с плагином ClickHouse, Apache Superset / Metabase, CDN-подключение ECharts |
| [0013](0013-helm-and-operators.md) | Helm-чарт на сервис + umbrella; инфраструктура через операторы | Kustomize, Bitnami-чарты Kafka/PostgreSQL/ClickHouse, Управляемые облачные сервисы (MSK, Cloud SQL, ClickHouse Cloud), Argo CD ApplicationSet без Helm |
| [0014](0014-observability.md) | Наблюдаемость: Prometheus-метрики и JSON-логи | Access-log на каждый запрос, OpenTelemetry (трейсы + метрики), StatsD / push-метрики |
| [0015](0015-container-images.md) | Образы: distroless static nonroot и nginx-unprivileged | alpine, scratch, Debian/Ubuntu |
| [0016](0016-autoscaling.md) | Автомасштабирование: HPA по CPU, KEDA по лагу Kafka | Фиксированное число реплик, HPA по RPS (custom metrics), VPA |
| [0017](0017-admin-auth.md) | Доступ к админке: Basic-auth или SSO на ingress | Встроенный OIDC-клиент, Без аутентификации, только сеть |
| [0018](0018-browser-sdk.md) | SDK: ES-модуль без зависимостей, IntersectionObserver и sendBeacon | Пиксель-изображение (GET), Google Tag Manager / сторонний счётчик, Сборка (TypeScript + бандлер) |
| [0019](0019-repos-and-ci.md) | Репозиторий на сервис, GitHub Actions, GHCR | Монорепозиторий, Общая Go-библиотека proview-kit, GitLab CI / Jenkins |
