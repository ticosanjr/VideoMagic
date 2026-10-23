export type RecipeFieldKind = "boolean" | "number" | "enum" | "text" | "color" | "path" | "json";

export interface RecipeField {
  path: string[];
  id: string;
  label: string;
  kind: RecipeFieldKind;
  options: string[];
  minimum?: number;
  maximum?: number;
  step?: number;
  integer: boolean;
  required: boolean;
  format: string;
  pattern: string;
  placeholder: string;
  help: string;
  value: unknown;
}

export interface RecipeFieldGroup {
  path: string[];
  label: string;
  fields: RecipeField[];
}

type Schema = Record<string, unknown>;

function resolve(schema: Schema, root: Schema): Schema {
  const ref = schema.$ref;
  if (typeof ref === "string" && ref.startsWith("#/")) {
    let current: unknown = root;
    for (const part of ref.slice(2).split("/")) {
      current = (current as Record<string, unknown> | undefined)?.[part];
    }
    if (current && typeof current === "object") return current as Schema;
  }
  const variants = schema.anyOf ?? schema.oneOf;
  if (Array.isArray(variants)) {
    const nonNull = variants.find((item) => {
      if (!item || typeof item !== "object") return false;
      return (item as Schema).type !== "null";
    });
    if (nonNull && typeof nonNull === "object") {
      return resolve({ ...schema, ...(nonNull as Schema), anyOf: undefined, oneOf: undefined }, root);
    }
  }
  return schema;
}

export function getPath(source: unknown, path: string[]): unknown {
  let current: unknown = source;
  for (const key of path) {
    if (!current || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[key];
  }
  return current;
}

export function setPath(source: Record<string, unknown>, path: string[], value: unknown): Record<string, unknown> {
  if (path.length === 0) return source;
  const [head, ...rest] = path;
  const current = source[head];
  if (rest.length === 0) return { ...source, [head]: value };
  const child = current && typeof current === "object" && !Array.isArray(current)
    ? { ...(current as Record<string, unknown>) }
    : {};
  return { ...source, [head]: setPath(child, rest, value) };
}

export function humanize(key: string): string {
  return key
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function kindFor(key: string, schema: Schema, resolved: Schema): RecipeFieldKind {
  const type = resolved.type;
  const enumValues = resolved.enum;
  if (type === "boolean") return "boolean";
  if (type === "number" || type === "integer") return "number";
  if (Array.isArray(enumValues) && enumValues.length) return "enum";
  if (/(^|_)color$/i.test(key)) return "color";
  if (/(_path|_dir|^path|^file)$/i.test(key)) return "path";
  return "text";
}

function buildField(
  key: string,
  schema: Schema,
  root: Schema,
  params: unknown,
  path: string[],
  required: boolean
): RecipeField | null {
  const resolved = resolve(schema, root);
  const type = resolved.type;
  if (type === "object") return null;
  if (type === "array") {
    return {
      path,
      id: path.join("."),
      label: humanize(key),
      kind: "json",
      options: [],
      minimum: undefined,
      maximum: undefined,
      step: undefined,
      integer: false,
      required,
      format: "",
      pattern: "",
      placeholder: "JSON array",
      help: typeof resolved.description === "string" ? resolved.description : "",
      value: getPath(params, path) ?? resolved.default ?? []
    };
  }
  if (!["boolean", "number", "integer", "string"].includes(String(type))) return null;
  const enumValues = Array.isArray(resolved.enum)
    ? resolved.enum.map((value) => String(value))
    : [];
  const kind = kindFor(key, schema, resolved);
  const minimum = typeof resolved.minimum === "number" ? resolved.minimum : undefined;
  const maximum = typeof resolved.maximum === "number" ? resolved.maximum : undefined;
  const description = typeof resolved.description === "string" ? resolved.description : "";
  return {
    path,
    id: path.join("."),
    label: humanize(key),
    kind,
    options: enumValues,
    minimum,
    maximum,
    step: type === "integer" ? 1 : undefined,
    integer: type === "integer",
    required,
    format: typeof resolved.format === "string" ? resolved.format : "",
    pattern: typeof resolved.pattern === "string" ? resolved.pattern : "",
    placeholder: description || (kind === "path" ? "/path/to/file" : ""),
    help: description,
    value: getPath(params, path) ?? resolved.default
  };
}

export function fieldGroups(schema: unknown, params: unknown): RecipeFieldGroup[] {
  const root = (schema ?? {}) as Schema;
  const properties = (root.properties ?? {}) as Record<string, Schema>;
  const required = new Set(Array.isArray(root.required) ? root.required.map(String) : []);
  const groups: RecipeFieldGroup[] = [];
  const rootGroup: RecipeFieldGroup = { path: [], label: "Parameters", fields: [] };
  for (const [key, raw] of Object.entries(properties)) {
    const resolved = resolve(raw, root);
    if (resolved.type === "object") {
      const nestedProperties = (resolved.properties ?? {}) as Record<string, Schema>;
      if (!Object.keys(nestedProperties).length) continue;
      const nestedRequired = new Set(
        Array.isArray(resolved.required) ? resolved.required.map(String) : []
      );
      const nested: RecipeFieldGroup = {
        path: [key],
        label: typeof resolved.title === "string" ? resolved.title : humanize(key),
        fields: []
      };
      for (const [childKey, childSchema] of Object.entries(nestedProperties)) {
        const field = buildField(
          childKey,
          childSchema,
          root,
          params,
          [key, childKey],
          nestedRequired.has(childKey)
        );
        if (field) nested.fields.push(field);
      }
      if (nested.fields.length) groups.push(nested);
      continue;
    }
    const field = buildField(key, raw, root, params, [key], required.has(key));
    if (field) rootGroup.fields.push(field);
  }
  if (rootGroup.fields.length) groups.unshift(rootGroup);
  return groups;
}

export function validateField(field: RecipeField): string | null {
  const value = field.value;
  if (field.required && (value === undefined || value === null || value === "")) {
    return "Required";
  }
  if (value === undefined || value === null || value === "") return null;
  if (field.kind === "enum" && !field.options.includes(String(value))) {
    return `Choose one of: ${field.options.join(", ")}`;
  }
  if (field.kind === "number") {
    const number = Number(value);
    if (!Number.isFinite(number)) return "Enter a number";
    if (field.integer && !Number.isInteger(number)) return "Enter an integer";
    if (field.minimum !== undefined && number < field.minimum) {
      return `Minimum ${field.minimum}`;
    }
    if (field.maximum !== undefined && number > field.maximum) {
      return `Maximum ${field.maximum}`;
    }
  }
  if (field.kind === "color" && !/^#[0-9a-f]{6}$/i.test(String(value))) {
    return "Use #RRGGBB";
  }
  if (field.format === "uri" || /(^|_)url$/i.test(field.id)) {
    try {
      const parsed = new URL(String(value));
      if (!["http:", "https:"].includes(parsed.protocol)) return "Use http:// or https://";
    } catch {
      return "Invalid URL";
    }
  }
  if (field.pattern) {
    try {
      if (!new RegExp(field.pattern).test(String(value))) return "Invalid format";
    } catch {
      // Ignore an invalid server-provided pattern.
    }
  }
  return null;
}

export function validateParams(schema: unknown, params: unknown): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const group of fieldGroups(schema, params)) {
    for (const field of group.fields) {
      const error = validateField(field);
      if (error) errors[field.id] = error;
    }
  }
  return errors;
}
