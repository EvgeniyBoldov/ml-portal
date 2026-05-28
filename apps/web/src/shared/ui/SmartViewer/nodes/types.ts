export type ParsedNodeType =
  | 'object'
  | 'array'
  | 'embedded_json'
  | 'multiline'
  | 'string'
  | 'number'
  | 'boolean'
  | 'null';

export interface ObjectParsedNode {
  type: 'object';
  entries: Array<{ key: string; node: ParsedNode }>;
}

export interface ArrayParsedNode {
  type: 'array';
  items: ParsedNode[];
}

export interface EmbeddedJsonParsedNode {
  type: 'embedded_json';
  parsed: ParsedNode;
  raw: string;
}

export interface MultilineParsedNode {
  type: 'multiline';
  lines: string[];
}

export interface StringParsedNode {
  type: 'string';
  value: string;
}

export interface NumberParsedNode {
  type: 'number';
  value: number;
}

export interface BooleanParsedNode {
  type: 'boolean';
  value: boolean;
}

export interface NullParsedNode {
  type: 'null';
}

export type ParsedNode =
  | ObjectParsedNode
  | ArrayParsedNode
  | EmbeddedJsonParsedNode
  | MultilineParsedNode
  | StringParsedNode
  | NumberParsedNode
  | BooleanParsedNode
  | NullParsedNode;
