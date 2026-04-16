-- =============================================================
-- Restructure agents, tool releases, bindings, triage prompt
-- =============================================================
BEGIN;

-- =============================================
-- 1. Update tool_releases descriptions & routing
-- =============================================

-- rag.search
UPDATE tool_releases SET
  description_for_llm = 'Search the company knowledge base (RAG) for processes, policies, manuals, and procedures. Use when the user asks about company rules, change management, network security policy, disaster recovery, equipment operations, or any internal documentation. Returns relevant text chunks with source references.',
  routing_ops = '["search"]',
  routing_resource = 'knowledge_base',
  routing_systems = '["qdrant", "rag"]',
  routing_keywords = '["knowledge base", "policy", "procedure", "manual", "process", "change management", "disaster recovery", "security", "documentation", "how to", "company rules", "SLA", "incident", "RFC"]',
  routing_negative_keywords = '["netbox", "device", "rack", "IP address", "subnet", "VLAN"]',
  routing_risk_level = 'low',
  routing_requires_confirmation = false,
  routing_idempotent = true,
  field_hints = '{"query": "Natural language search query describing what information to find", "k": "Number of results to return (default 5, max 20)", "scope": "Search scope: tenant (default)"}',
  exec_timeout_s = 60
WHERE id = '0f503361-b8e2-4e58-9d33-027f98f63140';

-- collection.search
UPDATE tool_releases SET
  description_for_llm = 'Search structured data collections (e.g. IT tickets, incidents, assets). Supports SQL-like filtering, text search, sorting, and pagination. Use when the user asks about tickets, incidents, specific records by ID or status.',
  routing_ops = '["search", "filter"]',
  routing_resource = 'collections',
  routing_systems = '["postgresql", "collections"]',
  routing_keywords = '["ticket", "incident", "collection", "record", "filter", "search data", "find records", "status", "assigned", "priority"]',
  routing_negative_keywords = '["knowledge base", "policy", "netbox", "device", "rack"]',
  routing_risk_level = 'low',
  routing_requires_confirmation = false,
  routing_idempotent = true,
  field_hints = '{"collection": "Collection slug to search in", "query": "Text search query", "filters": "DSL filter object", "sort": "Sort field and direction", "limit": "Max results (default 20)"}',
  exec_timeout_s = 30
WHERE id = 'd7ad4a52-9214-4fb9-a249-22cf62052e3e';

-- dcbox.devices
UPDATE tool_releases SET
  description_for_llm = 'Search network devices (servers, switches, routers, firewalls) in NetBox DCIM. Returns device details: name, role, site, IP addresses, rack position, status. Use when asking about specific devices, servers, or network equipment.',
  routing_ops = '["search", "list"]',
  routing_resource = 'dcim_devices',
  routing_systems = '["netbox"]',
  routing_keywords = '["device", "server", "switch", "router", "firewall", "equipment", "hardware", "network device", "hostname"]',
  routing_negative_keywords = '["ticket", "incident", "policy", "knowledge base"]',
  routing_risk_level = 'low',
  routing_requires_confirmation = false,
  routing_idempotent = true,
  field_hints = '{"name": "Device name or pattern", "site": "Site slug", "role": "Device role", "status": "active|planned|staged|offline", "manufacturer": "Manufacturer name"}',
  exec_timeout_s = 30
WHERE id = '564c0103-50f4-4442-9b99-cc808c3ecbce';

-- dcbox.addresses
UPDATE tool_releases SET
  description_for_llm = 'Search IP addresses in NetBox IPAM. Returns IP details: address, assigned device/interface, DNS name, VRF, status. Use when asking about specific IP addresses or looking up what device has a certain IP.',
  routing_ops = '["search", "list"]',
  routing_resource = 'ipam_addresses',
  routing_systems = '["netbox"]',
  routing_keywords = '["IP address", "IP", "address", "DNS", "interface", "assigned IP"]',
  routing_negative_keywords = '["ticket", "policy", "knowledge base"]',
  routing_risk_level = 'low',
  routing_requires_confirmation = false,
  routing_idempotent = true,
  field_hints = '{"address": "IP address to search", "device": "Device name", "interface": "Interface name", "vrf": "VRF name", "status": "active|reserved|deprecated"}',
  exec_timeout_s = 30
WHERE id = 'd02f171d-d276-4955-9a36-2f423830da1e';

-- dcbox.prefixes
UPDATE tool_releases SET
  description_for_llm = 'Search IP prefixes (subnets) in NetBox IPAM. Returns prefix details: CIDR, VLAN, VRF, site, utilization. Use when asking about network subnets, VLANs, or IP ranges.',
  routing_ops = '["search", "list"]',
  routing_resource = 'ipam_prefixes',
  routing_systems = '["netbox"]',
  routing_keywords = '["prefix", "subnet", "VLAN", "network", "CIDR", "IP range", "VRF"]',
  routing_negative_keywords = '["ticket", "policy", "knowledge base"]',
  routing_risk_level = 'low',
  routing_requires_confirmation = false,
  routing_idempotent = true,
  field_hints = '{"prefix": "CIDR notation", "site": "Site slug", "vlan_id": "VLAN number", "vrf": "VRF name", "status": "active|reserved|deprecated|container"}',
  exec_timeout_s = 30
WHERE id = '5c138604-87e0-476e-b905-ad5b7e852168';

-- dcbox.racks
UPDATE tool_releases SET
  description_for_llm = 'Search server racks in NetBox DCIM. Returns rack details: name, site, height, device count, location. Use when asking about physical rack locations or capacity.',
  routing_ops = '["search", "list"]',
  routing_resource = 'dcim_racks',
  routing_systems = '["netbox"]',
  routing_keywords = '["rack", "cabinet", "server room", "data center rack", "rack unit", "U"]',
  routing_negative_keywords = '["ticket", "policy", "knowledge base"]',
  routing_risk_level = 'low',
  routing_requires_confirmation = false,
  routing_idempotent = true,
  field_hints = '{"site": "Site slug", "status": "active|reserved|deprecated", "role": "Rack role"}',
  exec_timeout_s = 30
WHERE id = 'b81d1e8c-fae2-4343-9095-8203a95394d0';

-- dcbox.sites
UPDATE tool_releases SET
  description_for_llm = 'Search data center sites in NetBox DCIM. Returns site details: name, address, region, facility info. Use when asking about physical locations, data centers, offices.',
  routing_ops = '["search", "list"]',
  routing_resource = 'dcim_sites',
  routing_systems = '["netbox"]',
  routing_keywords = '["site", "data center", "location", "office", "facility", "DC"]',
  routing_negative_keywords = '["ticket", "policy", "knowledge base"]',
  routing_risk_level = 'low',
  routing_requires_confirmation = false,
  routing_idempotent = true,
  field_hints = '{"name": "Site name", "region": "Region name", "status": "active|planned|retired"}',
  exec_timeout_s = 30
WHERE id = 'dee790b8-317b-4319-a65d-768419c373ac';

-- =============================================
-- 2. Create releases for tools without active releases
-- =============================================

-- collection.aggregate release
INSERT INTO tool_releases (id, tool_id, version, backend_release_id, status, description_for_llm, routing_ops, routing_resource, routing_systems, routing_keywords, routing_negative_keywords, routing_risk_level, routing_requires_confirmation, routing_idempotent, field_hints, exec_timeout_s)
VALUES (
  gen_random_uuid(),
  '86bb5ef6-e323-4f52-8ccb-d7ebda2ac2bf',
  1,
  '7a3b09cd-7a50-493a-91c4-7bed7bb92ccd',
  'active',
  'Aggregate and compute statistics over structured data collections. Supports count, sum, avg, min, max with group_by and time_bucket. Use for analytics queries like "how many tickets per status" or "average resolution time".',
  '["aggregate", "stats"]',
  'collections',
  '["postgresql", "collections"]',
  '["aggregate", "statistics", "count", "average", "sum", "group by", "analytics", "report", "how many", "total"]',
  '["knowledge base", "netbox", "device"]',
  'low',
  false,
  true,
  '{"collection": "Collection slug", "operation": "count|sum|avg|min|max", "field": "Field to aggregate", "group_by": "Field to group by", "filters": "DSL filter object"}',
  30
);

-- collection.get release
INSERT INTO tool_releases (id, tool_id, version, backend_release_id, status, description_for_llm, routing_ops, routing_resource, routing_systems, routing_keywords, routing_negative_keywords, routing_risk_level, routing_requires_confirmation, routing_idempotent, field_hints, exec_timeout_s)
VALUES (
  gen_random_uuid(),
  '4be8c52a-cf0b-4ce4-bc46-d88faacd83c6',
  1,
  'd3d29105-ad35-4408-90b1-d93aac2c4f3a',
  'active',
  'Get a single record by its primary key from a structured data collection. Use when you know the exact record ID and need full details.',
  '["get"]',
  'collections',
  '["postgresql", "collections"]',
  '["get record", "by ID", "lookup", "details", "specific record"]',
  '["search", "list", "netbox", "knowledge base"]',
  'low',
  false,
  true,
  '{"collection": "Collection slug", "id": "Record primary key value", "id_field": "Primary key field name (default: id)"}',
  15
);

-- =============================================
-- 3. Delete old assistant agent (cascade deletes bindings via agent_versions)
-- =============================================
DELETE FROM agents WHERE slug = 'assistant';

-- =============================================
-- 4. Update existing agents
-- =============================================

-- Update rag-search agent
UPDATE agents SET
  name = 'Process & Policy Search',
  description = 'Searches the company knowledge base for processes, policies, manuals, and operational procedures. Use for questions about how things work in the company, change management, security policies, disaster recovery plans, equipment operation guides.',
  category = 'knowledge',
  tags = ARRAY['rag', 'knowledge', 'policy', 'process']
WHERE slug = 'rag-search';

-- Update rag-search active version prompt
UPDATE agent_versions SET
  identity = 'You are a Knowledge Base Search Agent specializing in finding company processes, policies, and operational documentation.',
  mission = 'Search the company knowledge base (RAG) and provide accurate, detailed answers based on found documents. Always cite sources.',
  scope = 'Company internal documentation: change management, network security policy, disaster recovery, equipment operations, engineering manuals.',
  rules = 'Always search the knowledge base before answering. If documents are found, synthesize the answer from them and cite the source document names. If nothing is found, clearly state that no relevant documentation was found. Answer in the user''s language.',
  tool_use_rules = 'Always call rag.search with a clear, specific query. Use k=5 for general questions, k=10 for broad topics. Rephrase the user query to maximize search relevance.',
  output_format = 'Provide a structured answer with: 1) Direct answer to the question, 2) Key details from documents, 3) Source references. Use markdown formatting.',
  temperature = 0.3
WHERE id = 'baacf9f8-e6d6-4792-a124-bb87a583b8d0';

-- Update data-analyst agent
UPDATE agents SET
  name = 'Collection Data Analyst',
  description = 'Searches and analyzes structured data collections (IT tickets, incidents, assets). Can filter, sort, aggregate, and summarize data from collections.',
  category = 'data',
  tags = ARRAY['collection', 'data', 'tickets', 'analytics']
WHERE slug = 'data-analyst';

-- Update data-analyst active version prompt
UPDATE agent_versions SET
  identity = 'You are a Data Analyst Agent specializing in structured data collections — IT tickets, incidents, asset records.',
  mission = 'Search, filter, aggregate, and analyze data in collections. Provide clear data-driven answers with statistics when relevant.',
  scope = 'Structured data collections: IT tickets, incidents, change requests, asset inventory.',
  rules = 'Use collection.search for finding specific records or filtering. Use collection.aggregate for statistics and counts. Use collection.get for looking up specific records by ID. Always specify the collection slug. Answer in the user''s language.',
  tool_use_rules = 'Start with collection.search to find relevant data. Use filters for specific queries (status, priority, assignee). Use collection.aggregate for "how many", "average", "total" questions.',
  output_format = 'Present data clearly: use tables for multiple records, bullet points for details, numbers for statistics.',
  temperature = 0.3
WHERE id = '39be89bf-c25a-4a31-b796-d36814c2cab9';

-- =============================================
-- 5. Create new agents
-- =============================================

-- 5a. netbox-inventory agent
INSERT INTO agents (id, slug, name, description, category, tags, created_at, updated_at)
VALUES (
  'a1b2c3d4-0001-4000-8000-000000000001',
  'netbox-inventory',
  'Network Inventory (NetBox)',
  'Queries NetBox for network infrastructure: devices, IP addresses, subnets, racks, sites. Use for questions about network equipment, IP allocation, data center locations, rack capacity.',
  'infrastructure',
  ARRAY['netbox', 'network', 'inventory', 'dcim', 'ipam'],
  now(), now()
);

INSERT INTO agent_versions (id, agent_id, version, status, identity, mission, scope, rules, tool_use_rules, output_format, temperature, created_at, updated_at)
VALUES (
  'a1b2c3d4-0001-4000-8000-100000000001',
  'a1b2c3d4-0001-4000-8000-000000000001',
  1,
  'active',
  'You are a Network Inventory Agent with access to NetBox — the source of truth for network infrastructure.',
  'Query NetBox to find information about network devices, IP addresses, subnets, racks, and data center sites. Provide accurate infrastructure data.',
  'NetBox DCIM and IPAM: devices (servers, switches, routers), IP addresses, prefixes/subnets, VLANs, racks, sites.',
  'Use the appropriate dcbox tool for each query type. For devices use dcbox.devices, for IPs use dcbox.addresses, for subnets use dcbox.prefixes, for racks use dcbox.racks, for sites use dcbox.sites. Always provide structured output with key fields. Answer in the user''s language.',
  'Choose the right tool based on the entity type being asked about. Use name/address filters when the user specifies particular items. For broad queries, use status=active to filter relevant results.',
  'Present infrastructure data in structured format: tables for lists, key-value pairs for single items. Include: name, status, site, IP addresses where applicable.',
  0.2,
  now(), now()
);

UPDATE agents SET current_version_id = 'a1b2c3d4-0001-4000-8000-100000000001' WHERE id = 'a1b2c3d4-0001-4000-8000-000000000001';

-- 5b. work-validator agent
INSERT INTO agents (id, slug, name, description, category, tags, created_at, updated_at)
VALUES (
  'a1b2c3d4-0002-4000-8000-000000000002',
  'work-validator',
  'Work Validator',
  'Validates planned work by cross-referencing change management procedures from the knowledge base with actual infrastructure data from NetBox. Checks if proposed changes comply with policies and if referenced devices/networks exist.',
  'operations',
  ARRAY['validation', 'compliance', 'change-management', 'audit'],
  now(), now()
);

INSERT INTO agent_versions (id, agent_id, version, status, identity, mission, scope, rules, tool_use_rules, output_format, temperature, created_at, updated_at)
VALUES (
  'a1b2c3d4-0002-4000-8000-100000000002',
  'a1b2c3d4-0002-4000-8000-000000000002',
  1,
  'active',
  'You are a Work Validation Agent that cross-references company procedures with infrastructure data to validate planned changes.',
  'Validate work requests by checking: 1) compliance with company change management and security policies (from RAG), 2) existence and status of referenced infrastructure (from NetBox), 3) potential risks and prerequisites.',
  'Change management validation using knowledge base policies and NetBox infrastructure data.',
  'Always check both sources: RAG for policies/procedures AND NetBox for infrastructure verification. First search RAG for relevant policies, then verify infrastructure details in NetBox. Provide a clear validation verdict. Answer in the user''s language.',
  'Step 1: Use rag.search to find relevant change management policies and procedures. Step 2: Use dcbox.devices/addresses/prefixes to verify referenced infrastructure exists and is in the expected state. Step 3: Synthesize a validation report.',
  'Provide a structured validation report: 1) Compliance status (PASS/WARN/FAIL), 2) Relevant policies found, 3) Infrastructure verification results, 4) Risks and recommendations.',
  0.3,
  now(), now()
);

UPDATE agents SET current_version_id = 'a1b2c3d4-0002-4000-8000-100000000002' WHERE id = 'a1b2c3d4-0002-4000-8000-000000000002';

-- =============================================
-- 6. Create agent bindings (agent_version ↔ tool)
-- =============================================

-- rag-search bindings (keep existing, they work)
-- Already has rag.search bound

-- data-analyst bindings (keep existing collection.search, add aggregate and get)
INSERT INTO agent_bindings (id, agent_version_id, tool_id, credential_strategy, created_at)
SELECT gen_random_uuid(), '39be89bf-c25a-4a31-b796-d36814c2cab9', '86bb5ef6-e323-4f52-8ccb-d7ebda2ac2bf', 'inherit', now()
WHERE NOT EXISTS (SELECT 1 FROM agent_bindings WHERE agent_version_id = '39be89bf-c25a-4a31-b796-d36814c2cab9' AND tool_id = '86bb5ef6-e323-4f52-8ccb-d7ebda2ac2bf');

INSERT INTO agent_bindings (id, agent_version_id, tool_id, credential_strategy, created_at)
SELECT gen_random_uuid(), '39be89bf-c25a-4a31-b796-d36814c2cab9', '4be8c52a-cf0b-4ce4-bc46-d88faacd83c6', 'inherit', now()
WHERE NOT EXISTS (SELECT 1 FROM agent_bindings WHERE agent_version_id = '39be89bf-c25a-4a31-b796-d36814c2cab9' AND tool_id = '4be8c52a-cf0b-4ce4-bc46-d88faacd83c6');

-- netbox-inventory bindings: all dcbox tools
INSERT INTO agent_bindings (id, agent_version_id, tool_id, credential_strategy, created_at) VALUES
  (gen_random_uuid(), 'a1b2c3d4-0001-4000-8000-100000000001', '0c571258-d8a0-4d8a-9314-a0878fc9ba22', 'inherit', now()),  -- dcbox.devices
  (gen_random_uuid(), 'a1b2c3d4-0001-4000-8000-100000000001', '0bd29579-0aaf-419b-bf04-ba59f733ece6', 'inherit', now()),  -- dcbox.addresses
  (gen_random_uuid(), 'a1b2c3d4-0001-4000-8000-100000000001', '377cdb87-43b3-4dc4-8d50-1b00cfae0512', 'inherit', now()),  -- dcbox.prefixes
  (gen_random_uuid(), 'a1b2c3d4-0001-4000-8000-100000000001', 'eaa39898-2af0-4572-b34e-77d6896f8c2c', 'inherit', now()),  -- dcbox.racks
  (gen_random_uuid(), 'a1b2c3d4-0001-4000-8000-100000000001', '01722e2e-1cf1-402f-af0e-46d1a980a552', 'inherit', now());  -- dcbox.sites

-- work-validator bindings: rag.search + dcbox.devices + dcbox.addresses + dcbox.prefixes
INSERT INTO agent_bindings (id, agent_version_id, tool_id, credential_strategy, created_at) VALUES
  (gen_random_uuid(), 'a1b2c3d4-0002-4000-8000-100000000002', 'd5a2c918-c792-4f4c-b11e-1882b4b5f0c8', 'inherit', now()),  -- rag.search
  (gen_random_uuid(), 'a1b2c3d4-0002-4000-8000-100000000002', '0c571258-d8a0-4d8a-9314-a0878fc9ba22', 'inherit', now()),  -- dcbox.devices
  (gen_random_uuid(), 'a1b2c3d4-0002-4000-8000-100000000002', '0bd29579-0aaf-419b-bf04-ba59f733ece6', 'inherit', now()),  -- dcbox.addresses
  (gen_random_uuid(), 'a1b2c3d4-0002-4000-8000-100000000002', '377cdb87-43b3-4dc4-8d50-1b00cfae0512', 'inherit', now());  -- dcbox.prefixes

-- =============================================
-- 7. Update current_version_id for existing agents
-- =============================================
UPDATE agents SET current_version_id = 'baacf9f8-e6d6-4792-a124-bb87a583b8d0' WHERE slug = 'rag-search';
UPDATE agents SET current_version_id = '39be89bf-c25a-4a31-b796-d36814c2cab9' WHERE slug = 'data-analyst';

-- =============================================
-- 8. Update triage prompt with new agents
-- =============================================
UPDATE system_llm_roles SET
  identity = 'You are an intelligent request router. You analyze user messages and decide the best execution path. You MUST return valid JSON matching the exact schema below. No markdown, no extra text — only raw JSON.',
  mission = 'Analyze the user message and conversation context. Decide one of four actions:
- "final": You can answer directly without any tools (greetings, general knowledge, simple questions, explanations)
- "agent": The request needs a specialized agent with tools
- "plan": Complex multi-step task requiring multiple agents/tools sequentially
- "ask_user": You need more information before proceeding',
  rules = 'Decision rules:
1. type="final" — for greetings, chitchat, general knowledge, explanations, opinions. If the user asks "what is X" about a general topic, answer directly.
2. type="agent" — when the user asks about company-specific information, needs to query systems, or work with data. Pick the BEST matching agent.
3. type="plan" — for complex tasks that need multiple data sources (e.g., "validate this change" needs both RAG and NetBox).
4. type="ask_user" — when the request is too ambiguous to route.

Available agents (use exact slugs):
- "rag-search" — search company knowledge base: processes, policies, manuals, change management, security policy, disaster recovery, equipment guides. Use for ANY question about company procedures or internal documentation.
- "data-analyst" — search and analyze structured data collections: IT tickets, incidents, assets. Use for questions about specific tickets, incident statistics, data filtering.
- "netbox-inventory" — query network infrastructure from NetBox: devices, IP addresses, subnets, racks, data center sites. Use for questions about network equipment, IPs, server locations.
- "work-validator" — validate planned changes against company policies and infrastructure. Use when the user wants to check if a planned change is compliant.

IMPORTANT: When type="agent", always set agent_slug and goal. When type="final", always set answer with a complete, helpful response. When type="ask_user", always set questions.',
  output_requirements = 'Return ONLY valid JSON (no markdown, no backticks, no extra text). Exact schema:
{
  "type": "final" | "agent" | "plan" | "ask_user",
  "confidence": 0.0-1.0,
  "reason": "short explanation of routing decision",
  "answer": "complete helpful answer (ONLY if type=final)",
  "agent_slug": "agent slug (ONLY if type=agent)",
  "goal": "task description for agent (if type=agent or plan)",
  "inputs": {},
  "questions": ["question1"] 
}',
  updated_at = now()
WHERE role_type = 'triage';

-- =============================================
-- 9. Update planner prompt to know about new agents
-- =============================================
UPDATE system_llm_roles SET
  rules = 'Rules:
1. Each step must use exactly one tool from the available_tools list.
2. Use the exact tool slug and operation from available_tools.
3. If previous_observations exist in session_state, review them. Do NOT repeat a tool call that already returned results.
4. If a tool returned empty results or an error, either try a different query or return a "kind": "llm" step with a summary answer.
5. For the FINAL answer step, use kind="llm" with a descriptive title containing the answer.
6. Keep plans minimal — 1-3 steps maximum.
7. Return ONLY valid JSON (no markdown, no backticks).',
  updated_at = now()
WHERE role_type = 'planner';

-- =============================================
-- 10. Update ragdocuments status to 'ready' since pipeline completed
-- =============================================
UPDATE ragdocuments SET status = 'ready' WHERE status = 'uploaded';

COMMIT;
