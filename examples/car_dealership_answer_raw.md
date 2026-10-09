**Предварительный DWH-проект для сети автосалонов**

---

**Предпосылки:**  
- Три автосалона, ежедневная загрузка, единая валюта.  
- Гранулярность фактов — событийные и линейные идентификаторы.  
- Все остатки — по салону, продукту (автомобиль), партии (VIN), дате.  
- Возвраты, отмены, trade-in — отражаются как отдельные события.  
- Срок нахождения — от даты поступления до даты продажи/выхода.  
- Маржа — разница между ценой продажи и себестоимостью (закупочная цена + скидка).  

---

**Факты (с гранулярностью):**

| Факт | Измерения | Гранулярность |
|------|----------|---------------|
| `sales_fact` | выручка, маржа, количество проданных автомобилей | `sale_id + vin + sale_date` |
| `return_fact` | сумма возврата, возврат по VIN | `return_id + vin + return_date` |
| `trade_in_fact` | стоимость trade-in, выручка от возврата | `trade_in_id + vin + trade_in_date` |
| `inventory_snapshot_fact` | остатки автомобилей | `location_id + vin + batch_id + snapshot_date` |
| `service_work_fact` | стоимость работ, количество работ | `work_order_id + vin + service_date` |
| `service_part_fact` | стоимость запчастей | `part_order_id + vin + part_date` |

---

**Конформные измерения:**  
- `location_dim` (salon_id, address, city)  
- `vehicle_dim` (vin, model_id, year, make, price, discount)  
- `customer_dim` (customer_id, name, phone)  
- `employee_dim` (employee_id, name, role)  
- `sales_stage_dim` (stage_id, stage_name, stage_type)  
- `test_drive_dim` (test_drive_id, customer_id, vin, date)  

**Связи:**  
- `sales_fact` → `vehicle_dim`, `customer_dim`, `sales_stage_dim`  
- `return_fact` → `vehicle_dim`, `customer_dim`  
- `trade_in_fact` → `vehicle_dim`, `customer_dim`  
- `service_work_fact` → `vehicle_dim`, `employee_dim`  
- `service_part_fact` → `vehicle_dim`, `part_dim`  

---

**Ключевые показатели:**  
1. **Продажи по воронке** = количество клиентов, прошедших этапы (от обращения до продажи)  
2. **Маржа на продажу** = (выручка – себестоимость) / выручка  
3. **Срок нахождения на складе** = `sale_date – arrival_date` (для продажи)  
4. **Остатки по салонам** = `inventory_snapshot_fact` по `location_id` и `vin`  

---

**Качество и бизнес-правила:**  
- Отмена сделки — отражается в `sales_fact` как `status = 'canceled'`, не включается в воронку.  
- Trade-in — включается в выручку сервиса, но не в продажи.  
- Возврат — уменьшает остатки, увеличивает `return_fact`.  
- Остатки — не суммируются по датам, а хранятся как snapshot.  
- **Вопросы:**  
  - Как определить себестоимость автомобиля (закупочная цена + скидка)?  
  - Как обрабатывать отмены и возвраты в воронке?  
  - Как определить "срок нахождения" при trade-in или возврате?  
  - Какие критерии "сроков" — по дате поступления или по дате продажи?