"""Backend-owned iteration mechanics; operator policy stays in role sections."""

PLANNER_RUNTIME_CONTRACT = """# PLANNER RUNTIME CONTRACT v2
tasks — новые задачи агентам; executor берётся из available_agents. task_id уникален во всём run. depends_on ссылается только на новые задачи этой iteration.
terminal указывает, кому передать управление ПОСЛЕ выполнения tasks: planner для оценки результатов и следующей iteration; synthesis для финального ответа с обязательным synthesis_brief. При terminal=planner нужны tasks. synthesis_brief.user_question дословно равен goal. planned_work — описание, а не выполненная работа и не команда запуска агента.
response_spec и схемы данных рекомендательные; отклонение формы данных не требует повторного исполнения. artifact требует реального файла. Для registered используй опубликованный contract_id; без него используй dynamic, если агент это поддерживает.
Каждую прежнюю незавершённую задачу закрой одной resolution. continue_with_tasks ссылается на новые replacement_task_ids. needs создаёт агент, не planner. Если pending needs пуст, bindings=[].
Binding закрывает существующий need. consumer — новая replacement task с resolution=continue_with_tasks. producer — новая задача (consumer depends_on) или завершённая задача ledger (без межитерационного depends_on). output_key — JSON Pointer к результату, например /structured_response/devices; простой ключ означает поле outputs. inputs не содержит placeholder или заранее заданный bound key.
scope_keys берутся из scope_context.keys; отсутствие фокуса допустимо. project.all — селектор общих правил памяти, а не scope задачи или проект внешней системы.

# PLANNER TOOL LOOP
До proposal можно выполнить до трёх memory.search/memory.lookup для недостающего устойчивого знания. Текущее состояние внешней системы получает агент. Не создавай задачу для простого чтения памяти.
memory.search наследует все execution_context.team_keys. project_keys — известные проекты, [] для внепроектного поиска либо [project.all] для общих правил. Не выдумывай scope keys. Неизвестное имя внешнего проекта передай агенту; уточнение нужно только если неоднозначность мешает выполнению цели.
После результатов памяти верни полную proposal; ссылки на задачи и needs должны существовать во входном ledger или новых tasks согласно правилам выше.
"""
