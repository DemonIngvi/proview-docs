# Runbook: установка в Kubernetes

## 1. Требования к кластеру

- Kubernetes ≥ 1.29, StorageClass с SSD (`fast-ssd` в prod-профиле), ≥ 3 узла в разных зонах для prod.
- Ingress-контроллер (ingress-nginx), cert-manager. Prometheus Operator — по желанию.

## 2. Операторы (один раз на кластер)

```bash
# Strimzi (Kafka, KRaft)
helm repo add strimzi https://strimzi.io/charts/
helm upgrade --install strimzi strimzi/strimzi-kafka-operator -n strimzi --create-namespace \
  --set watchAnyNamespace=true

# CloudNativePG
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm upgrade --install cnpg cnpg/cloudnative-pg -n cnpg-system --create-namespace

# Altinity ClickHouse operator (ClickHouse + Keeper)
helm repo add altinity https://docs.altinity.com/clickhouse-operator/
helm upgrade --install clickhouse-operator altinity/altinity-clickhouse-operator -n clickhouse-operator --create-namespace

# опционально: KEDA (масштабирование загрузчика по лагу)
helm repo add kedacore https://kedacore.github.io/charts
helm upgrade --install keda kedacore/keda -n keda --create-namespace
```

Версии операторов закрепите в своём GitOps-репозитории. Проверено по схемам CRD: Strimzi `kafka.strimzi.io/v1beta2`, CNPG `postgresql.cnpg.io/v1`, Altinity `clickhouse.altinity.com/v1` и `clickhouse-keeper.altinity.com/v1`.

## 3. Секреты (prod)

Создайте Secret `proview-secrets` в namespace `proview` через External Secrets, Sealed Secrets или Vault. Ключи:

| Ключ | Кто использует |
|---|---|
| `TOKEN_SECRET` (≥ 32 символа) | banner-service: подпись |
| `TOKEN_KEYS` = `k1:<TOKEN_SECRET>[,k0:<старый>]` | event-collector: проверка |
| `BANNER_ADMIN_TOKEN` | banner-service (API пула), analytics (имена баннеров) |
| `ADMIN_PASSWORD` | analytics (если без SSO) |
| `CLICKHOUSE_PASSWORD` | ingester, пользователь `proview` в CHI |
| `CLICKHOUSE_RO_PASSWORD` | analytics, пользователь `proview_ro` в CHI |

DSN PostgreSQL берётся из Secret `proview-pg-app`, который создаёт CloudNativePG.

## 4. Установка

```bash
helm upgrade --install proview oci://ghcr.io/demoningvi/charts/proview --version 0.1.0 \
  -n proview --create-namespace -f values-prod.yaml   # на основе proview-deploy/helm/proview/values-prod.yaml
kubectl -n proview get kafka,kafkatopic,cluster,chi,chk          # инфраструктура готова?
kubectl -n proview get deploy,hpa,pdb -l app.kubernetes.io/part-of=proview
```

Порядок старта не важен. Сервисы ждут инфраструктуру с ретраями и не проходят readiness, пока она не готова. Миграции выполняются Job-хуками (`post-install,pre-upgrade`) с ретраями.

## 5. Проверка

```bash
kubectl -n proview port-forward svc/proview-web 8080:8080 &
curl -A "Mozilla/5.0 Chrome/130" "http://localhost:8080/v1/banner?placement=home_top"   # 200 + token
# e2e против кластера:
E2E_WEB_URL=https://demo.example.com E2E_ANALYTICS_URL=... E2E_BANNER_ADMIN_URL=... \
  go test -tags e2e ./e2e/...
```

## 6. Обновление и откат

`helm upgrade` с новой версией чарта. Выкладка без простоя: `maxUnavailable: 0`, PDB. Миграции только аддитивные (`IF NOT EXISTS`). Откат: `helm rollback proview <ревизия>`. Схема БД при откате не откатывается, поэтому совместимость миграций назад обязательна.
