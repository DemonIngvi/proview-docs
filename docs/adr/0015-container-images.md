# ADR-0015. Образы: distroless static nonroot и nginx-unprivileged

- **Статус:** принято
- **Дата:** 2026-11-06

## Контекст

Минимальная поверхность атаки и размер образа, запуск без root и с read-only FS по best practices Kubernetes (Pod Security Standards restricted).

## Решение

Go-сервисы: multi-stage сборка `golang:1.26-alpine` → `gcr.io/distroless/static-debian12:nonroot` (~24–30 МБ); сайт — `nginxinc/nginx-unprivileged`. Сборка multi-arch (amd64/arm64) с SBOM и provenance, проверка Trivy.

## Обоснование

- Нет оболочки и пакетного менеджера — нечего эксплуатировать; CVE-поверхность минимальна.
- UID 65532, readOnlyRootFilesystem, drop ALL — соответствует профилю restricted.
- arm64 позволяет запускать на дешёвых Graviton/Ampere-узлах.

## Рассмотренные альтернативы

| Вариант | Плюсы | Минусы | Почему не выбран |
|---|---|---|---|
| alpine | есть shell для отладки | musl, пакеты = CVE | отладка через ephemeral containers |
| scratch | минимально | нет CA-сертификатов, tzdata, /etc/passwd | distroless включает необходимое |
| Debian/Ubuntu | привычно | сотни МБ и пакетов | избыточно |

## Последствия

- ✅ Образы 24–30 МБ, быстрый pull при масштабировании.
- ⚠️ Нет shell: отладка через `kubectl debug`.

## Когда пересмотреть

Не требуется.
