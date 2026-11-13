# DATA_CONTRACTS — контракты данных

Версия: 0.1.0

## Candle
Поля: symbol, interval, open_time (UTC epoch ms), OHLC, volume, close_time; дополнительно quote_volume, trade_count, taker_buy_base/quote при наличии.

Инварианты:
- OHLC конечные; цены положительные; volume неотрицательный.
- high >= max(open, close, low); low <= min(open, close, high).
- close_time = open_time + interval_ms - 1.
- Уникальный ключ (symbol, interval, open_time).
- Внутри выборки timestamps строго возрастают и выровнены по интервалу.

## Data Manifest
Хранить dataset_id, источник/endpoint, символы и интервалы, первый/последний timestamp, число строк, checksum, время загрузки, версии парсера/схемы и известные gaps.

## Feature Record
feature_set_version, symbol, interval, event_time, available_at, типизированные признаки, source_dataset_id и quality flags.

## Hypothesis
hypothesis_id, формулировка, измеримый критерий, рынок/таймфрейм, период формирования, признаки/параметры, механизм, критерии опровержения и статус.

## Forecast / Outcome
Forecast хранит forecast_id, created_at, decision_time, symbol, interval, horizon, вероятности сценариев, ожидаемое распределение, uncertainty, версии модели/данных/признаков.
Outcome хранит период оценки, фактическую доходность, favourable/adverse excursion, время до результата, издержки и полноту исхода.

## Временная причинность
- Признак допустим, только если available_at <= decision_time.
- Свеча доступна после подтверждённого закрытия.
- Старший таймфрейм использует только последнюю закрытую свечу.
- Outcome может смотреть вперёд, но не попадает в признаки.
- Внутри системы UTC; локальное время — только отображение UI.

## Gaps и дубликаты
Пропуски регистрируются, синтетические свечи не создаются. Исходные строки не перезаписываются молча. Неполные свечи маркируются и исключаются из закрытой выборки. Исправления создают новую версию данных.

## Хранилища
Исходные CSV/SQLite — read-only. Research DB, feature store и model artifacts — отдельно. Любой аналитический ответ возвращает provenance, диапазон времени, число строк, предупреждения и версию алгоритма.

Запрещено: использовать будущее в признаках; интерполировать OHLC без отдельной модели; смешивать биржи без маркировки источника; трактовать отсутствие данных как нулевую активность.
