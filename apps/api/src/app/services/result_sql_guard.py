"""Restrict agent SQL to the authorized virtual result relations."""
from sqlglot import exp, parse
from sqlglot.optimizer.scope import Scope, traverse_scope


def referenced_results(query: str, available: set[str]) -> set[str]:
    statements = parse(query, read="postgres")
    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        raise ValueError("Only one SELECT query is allowed")
    statement = statements[0]
    aliases = {cte.alias_or_name.lower() if not cte.args['alias'].this.args.get('quoted')
               else cte.alias_or_name for cte in statement.find_all(exp.CTE)}
    if aliases & available or '_agent_query' in aliases:
        raise ValueError("CTE names must not shadow result tables")
    for node in statement.walk():
        if isinstance(node, exp.Dot) and isinstance(node.expression, exp.Func):
            raise ValueError("Schema-qualified SQL functions are not supported")
        if isinstance(node, (exp.DML, exp.DDL, exp.Into, exp.Lock, exp.Command)):
            raise ValueError("Only read-only SELECT queries are allowed")
        if isinstance(node, exp.Anonymous) and node.name.lower() not in {
            'to_jsonb', 'jsonb_typeof', 'jsonb_array_length', 'jsonb_extract_path',
            'jsonb_extract_path_text', 'jsonb_build_object', 'jsonb_build_array',
            'jsonb_object_keys', 'jsonb_array_elements', 'jsonb_array_elements_text',
            'jsonb_agg', 'json_agg', 'jsonb_object_agg',
        }:
            raise ValueError(f"Unsupported SQL function: {node.name}")
        if isinstance(node, exp.Func) and not isinstance(node, exp.Anonymous) and node.sql_name() not in {
            'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'ARRAY_AGG', 'GROUP_CONCAT',
            'COALESCE', 'NULLIF', 'CAST', 'TRY_CAST', 'LOWER', 'UPPER',
            'STR_POSITION', 'LENGTH', 'CHAR_LENGTH', 'SUBSTRING', 'TRIM',
            'LTRIM', 'RTRIM', 'REPLACE', 'CONCAT', 'CONCAT_WS', 'ROUND',
            'ABS', 'CEIL', 'FLOOR', 'MOD', 'POWER', 'SQRT', 'ROW_NUMBER',
            'RANK', 'DENSE_RANK', 'LAG', 'LEAD', 'FIRST_VALUE', 'LAST_VALUE',
            'JSON_EXTRACT', 'JSON_EXTRACT_SCALAR', 'JSONB_EXTRACT',
            'JSONB_EXTRACT_SCALAR', 'JSONB_CONTAINS', 'JSONB_CONTAINS_ANY_TOP_KEYS',
            'JSONB_CONTAINS_ALL_TOP_KEYS', 'JSONB_EXISTS', 'CASE', 'IF',
        }:
            raise ValueError(f"Unsupported SQL function: {node.sql_name()}")
    references = set()
    for scope in traverse_scope(statement):
        for table, source in scope.selected_sources.values():
            if isinstance(source, Scope):
                continue
            if not isinstance(table, exp.Table):
                raise ValueError("Only virtual result tables are accessible")
            if table.db or table.catalog or not isinstance(table.this, exp.Identifier):
                raise ValueError("Only virtual result tables are accessible")
            name = table.name if table.this.args.get('quoted') else table.name.lower()
            if name in available:
                references.add(name)
            else:
                raise ValueError(f"Unknown or inaccessible result table: {name}")
    return references
