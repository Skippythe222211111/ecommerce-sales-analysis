# Проверка на PostgreSQL

Дата прогона: 2026-11-04. Версия: PostgreSQL 18.6 (Windows x64).
Данные: официальный файл UCI `Online Retail.xlsx` (541 909 строк), полученный
скриптом `scripts/run_analysis.py --download`.

## Что выполнялось

```powershell
psql -d ecommerce_retail -f sql\00_schema.sql
psql -d ecommerce_retail -c "\copy retail.online_retail_raw(...) FROM 'data/online_retail_for_postgres.csv' WITH (FORMAT csv, HEADER true, NULL '')"
psql -d ecommerce_retail -f sql\01_analysis.sql
psql -d ecommerce_retail -f sql\02_validation.sql
python scripts\verify_sql_parity.py --dsn "host=127.0.0.1 port=55432 user=postgres dbname=ecommerce_retail"
```

## Результаты

- `00_schema.sql`: схема и представление созданы без ошибок.
- Загрузка: `COPY 541909` — столько же строк, сколько в исходном файле.
- `01_analysis.sql`: выполнился целиком, все 5 секций.
- `02_validation.sql`: `SQL validation passed` — инварианты классификации и
  дедупликации выполняются.
- `verify_sql_parity.py`: `PASS` по всем трём таблицам (13 месяцев, 10 товаров,
  10 стран), расхождений с Python нет.

## Ключевые числа (SQL = Python)

| Метрика | Значение |
|---|---:|
| Строк после дедупликации | 536 641 |
| Положительные продажи | £10 642 110,80 |
| Заказы с положительной продажей | 19 960 |
| Средний чек | £533,17 |
| Единицы товара | 5 572 420 |
| Клиенты с известным ID | 4 338 |
| Отмены (строки / сумма) | 9 251 / £893 979,73 |
| Возвраты и корректировки (строки) | 1 336 |
| Стран / кодов товара | 38 / 3 922 |

## Что было исправлено по итогам прогона

1. `00_schema.sql`: NULL-цена больше не попадает в `nonpositive_price` —
   поведение совпадает с Python (`invalid_transaction`).
2. `01_analysis.sql`: сумма отмен обёрнута в `COALESCE(..., 0)`, чтобы при
   отсутствии отмен возвращался 0, а не NULL.
3. `01_analysis.sql`: набор месяцев строится по строкам продаж, возвраты и
   отмены присоединяются слева — как в Python-экспорте.
4. `01_analysis.sql`: топ-товары и топ-страны сортируются по неокруглённой
   сумме, чтобы порядок совпадал с Python.
