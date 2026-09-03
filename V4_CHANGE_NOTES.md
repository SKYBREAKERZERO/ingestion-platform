# v4 - Taxonomy + JSON Project Output Routing

## 1. 外部词库驱动式样分类

新增：

```text
config/specification_taxonomy.yaml
```

`SpecificationClassifier` 不再依赖 Python 内部硬编码分类列表。词库负责：

- `region_scope`
- `spec_type`
- `spec_subtype`
- 区域 + 式样编号 + 正式名称的 exact rule
- 通用别名 / 复合词匹配

第一版词库按提供的 21MM 目录整理：

- NA：23 条 exact catalog rules
- EXCEPT_NA：136 条第一批高置信 exact catalog rules
- 其余不安全项保留在 `specification_taxonomy_unresolved_v1.txt`，不强制猜测

正文默认不参与式样身份分类，避免 `Refer to HMI/Bluetooth/...` 之类引用污染当前式样类型。

示例：

```text
550_Bluetooth Audio Function Spec
-> region_scope = EXCEPT_NA
-> spec_type = BT
-> spec_subtype = BLUETOOTH_AUDIO

555_NA_21MM_Virtual_Assistant_Spec[NA]
-> region_scope = NA
-> spec_type = VIRTUAL_ASSISTANT

555_VUI Function Spec
-> region_scope = EXCEPT_NA
-> spec_type = VUI
```

## 2. JSON-only 模式按项目自动分目录

当：

```text
Generate JSON = ON
Save to PostgreSQL = OFF
```

选择任意输出根目录，例如：

```text
output/
```

程序自动保证存在：

```text
output/
├── 21MM/
└── 24MM/
```

用户选择 `21MM` 后处理的 JSON：

```text
output/21MM/<file>.json
```

用户选择 `24MM` 后处理的 JSON：

```text
output/24MM/<file>.json
```

当 `Save to PostgreSQL = ON` 时保持原有 JSON 输出路径行为，不改变现有工作流。

## 3. PostgreSQL

`documents` 新增：

```text
region_scope TEXT
```

新增索引：

```text
(project_code, region_scope, spec_type)
```

`rag_chunks` 在原列顺序末尾追加 `region_scope`，避免 PostgreSQL `CREATE OR REPLACE VIEW` 列顺序升级问题。

`spec_types` / `spec_subtypes` Master 现在从 `specification_taxonomy.yaml` 自动 UPSERT，不再由 SchemaManager 硬编码。

两个数据库都需要再次执行一次：

```text
Initialize / Upgrade RAG Database
```

## 4. 可维护词库

开发环境直接编辑：

```text
config/specification_taxonomy.yaml
```

EXE 环境支持外部覆盖：

```text
<EXE directory>/config/specification_taxonomy.yaml
```

也可以通过环境变量指定：

```text
SPECIFICATION_TAXONOMY_FILE
```

## v4.1 - Clear pending files on project switch

- When the GUI project changes between `21MM` and `24MM`, the pending document input list is automatically cleared.
- The first project selection does not clear files; only an actual project-to-project switch does.
- The clear is automatic with no confirmation dialog, preventing a batch selected for one project from being processed under the other project.
- The current-file label and pending file count are reset, and the status bar records the project switch.
- JSON import files are not affected; only the normal document-conversion pending file area is cleared.


## v4.2 - Common processing scope + single Database field

- Added `Common` processing scope for non-specification content such as news, meeting material, screenshots, reports and general documents.
- Common uses the same loader/parser/chunk/JSON/PostgreSQL schema, but specification taxonomy classification is marked `NOT_APPLICABLE` and `series/region_scope/spec_type/spec_subtype` stay `NULL`.
- PostgreSQL Settings now exposes one `Database` field instead of separate 21MM/24MM fields.
- Each processing scope remembers its own database name internally; new/unconfigured scopes default to `rag`.
- The database field switches automatically when `21MM`, `24MM`, or `Common` is selected.
- Existing legacy `project_databases` settings remain readable for backward compatibility.
- JSON-only output now separates all three scopes:

```text
output/
├── 21MM/
├── 24MM/
└── COMMON/
```

- Switching between any two scopes automatically clears pending Document Conversion input files.
