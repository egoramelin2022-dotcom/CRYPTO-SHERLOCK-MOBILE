# TESTING_REQUIREMENTS — требования к тестированию

Версия: 0.1.0

## Правила
Каждый модуль имеет unit tests; каждый дефект — regression test. Тесты не изменяют пользовательские CSV/SQLite. CI использует временные БД и синтетические фикстуры. Сетевые ответы Binance мокируются. Случайные процессы фиксируют seed.

## Уровни
- Unit: свечи, интервалы, признаки, gaps, labels, similarity, clustering, метрики, калибровка, сериализация.
- Integration: read-only БД, manifest, feature/outcome pipeline, experiment ledger, registry и API Core.
- Temporal/leakage: признаки не используют время позже decision_time; незакрытые свечи исключены; старший TF только закрытый; labels не попадают в features; purge/embargo работает.
- Statistical: baseline, устойчивость по окнам, чувствительность параметров, overlap аналоги, интервалы неопределённости и sanity checks на случайных данных.
- Performance: время выборки и поиска, RAM, диск, resume после прерывания, работа без GPU.
- End-to-end: данные → признаки → гипотеза → эксперимент → отчёт → память; forecast → outcome → evaluation; Paper-only без внешних ордеров.

## Инварианты безопасности
Тестовая конфигурация без торговых ключей; код текущего этапа не имеет пути отправки реальных ордеров; исходные данные read-only; тесты на копиях/временных БД; ошибки качества не маскируются заполнением.

## Release gate
Полный regression suite, dependency/security scan, конфигурация без секретов, backup/restore, read-only verification, end-to-end paper-only и ручная проверка отчётов.
