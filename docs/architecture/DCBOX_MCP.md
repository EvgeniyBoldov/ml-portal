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
