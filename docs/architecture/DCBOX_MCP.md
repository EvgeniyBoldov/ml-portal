# DCBox через NetBox MCP

DCBox — production-экземпляр NetBox с плагинами. MCP сохраняет общий
`netbox_get_objects`/`netbox_search_objects` contract: тип объекта передается
через `object_type`, а plugin-specific маршруты выбираются из allowlist в
`mcp/netbox/server.py`.

## Текущие маршруты

Для DCBox доступны следующие canonical object types:

| `object_type` | API endpoint |
| --- | --- |
| `dcbox.capacity` | `/api/plugins/dcbox/capacitys/` |
| `dcbox.channel` | `/api/plugins/dcbox/channels/` |
| `dcbox.device_group` | `/api/plugins/dcbox/device-groups/` |
| `dcbox.infrastructure_place` | `/api/plugins/dcbox/infrastructure-places/` |
| `dcbox.interface_group` | `/api/plugins/dcbox/interface-groups/` |
| `dcbox.prefix_group` | `/api/plugins/dcbox/prefix-groups/` |
| `dcbox.vlan_mapping_group` | `/api/plugins/dcbox/vlanmappinggroup/` |

Также зарегистрированы plugin root endpoints из production списка под
`plugin.*`, например `plugin.installed_plugins` и `plugin.technical_record`.
Они предназначены для явного чтения plugin API, а не для автоматического
обхода всех неизвестных URL.

Пример вызова:

```json
{
  "object_type": "dcbox.capacity",
  "limit": 20,
  "filters": {"site": "dc1"}
}
```

MCP запросит:

```text
/api/plugins/dcbox/capacitys/?limit=20&site=dc1
```

## Как добавить endpoint

1. Получите точный production API path и проверьте его схему, фильтры и
   пагинацию.
2. Добавьте запись в `PLUGIN_ENDPOINTS` в
   `mcp/netbox/server.py`:

   ```python
   "dcbox.new_resource": "/api/plugins/dcbox/new-resources/",
   ```

3. В качестве ключа используйте стабильное MCP-имя в формате
   `plugin.resource`. Для DCBox рекомендуется `dcbox.<resource>`; реальные
   дефисы, нестандартное склонение и опечатки endpoint’а оставляйте только в
   значении URL.
4. Не добавляйте полный URL с host — значения registry должны быть только
   относительными путями `/api/...`.
5. Если endpoint является корнем отдельного plugin, используйте namespace
   `plugin`, например `plugin.change_requests`.
6. Добавьте тест на resolver и, если endpoint используется агентом,
   обновите его tool-use instructions с новым `object_type`.

Обычные NetBox-типы (`dcim.device`, `ipam.prefix`) продолжают использовать
автоматическое построение `/api/{app}/{model}s/`. Для `dcbox.*` неизвестный
тип отклоняется с ошибкой, чтобы опечатка не превратилась в запрос к
неверному стандартному маршруту.

Если `netbox_search_objects` вызван без `object_types`, MCP выполняет
ограниченный поиск только по обычным NetBox типам: `dcim.device`, `dcim.rack`,
`dcim.site`, `ipam.ipaddress` и `ipam.prefix`. Он не использует
`/api/extras/search/`: этот endpoint не является частью обязательного API
NetBox и отсутствует в production DCBox. Плагинный тип нужно передавать явно;
тогда применяется маршрут из `PLUGIN_ENDPOINTS`.


## Инструкция коллекции для агента

Правила выбора операций хранятся в `usage_rules` опубликованной версии коллекции NetBox и выводятся в карточке коллекции целиком. MCP-инструменты содержат краткое описание действия и схему аргументов. Описания операций в native tools и текстовом промпте не обрезаются по количеству символов.

Для получения списка объектов используй netbox_get_objects. Все устройства: {"collection_slug":"netbox","object_type":"dcim.device","filters":{}}. Пустые или отсутствующие filters означают список без фильтрации. Название типа выбирает категорию объектов, а не текст для поиска.
Для поиска по тексту используй netbox_search_devices(query=...) или netbox_search_objects(q=..., object_types=[...]). Текст должен быть непустым и содержать искомое имя или слово. q="device" ищет слово device внутри записей, а не перечисляет устройства. Пустая строка и * не являются способом получить все записи. Ноль совпадений означает отсутствие совпадений данного поиска, а не отсутствие устройств в NetBox.
Для точного имени устройства используй netbox_get_device(name=...). Для площадок — netbox_list_sites. Интерфейсы — netbox_get_objects(object_type="dcim.interface", filters={"device":"имя из результата"}). Для точного CIDR — ipam.prefix и filters.prefix; для IP — ipam.ipaddress и filters.address. Используй подтверждённые значения и фильтры соответствующего типа.
Каждый вызов возвращает страницу. Проверь число сохранённых строк, source_total и source_complete. Если для задачи нужны остальные записи, используй result.load с result_id; если результат не подходит, не догружай его. Читай сохранённые строки через result.read, анализируй через result.sql. Вложенные атрибуты остаются JSONB.
После ошибки аргументов исправь аргументы или выбери подходящую операцию. Не повторяй тот же ошибочный вызов без изменений. Ошибка HTTP или ошибка отдельного типа не означает пустой список. Проверь успешные типы и ошибки до вывода об отсутствии данных. Успешный поисковый вызов сам по себе не доказывает получение полного инвентаря.
