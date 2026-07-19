# Google Cloud naming conventions

Gradient runs on Google Cloud, and two kinds of naming drift without a written convention, each caught today only by manual review. This doc records both, and maps each to the enforcement layer that owns it: a `repostyle` rule where the convention is mechanizable, and a `common-style-review` lens plus this doc where it resists a rule.

The two facets are independent. Facet 1 is about identifiers in our own code; Facet 2 is about product and brand names in prose.

## Facet 1 — identifier `name` vs id (AIP-122)

Google's [AIP-122](https://google.aip.dev/122) distinguishes a resource's **name** — the qualified path `projects/{project}`, `buckets/{bucket}/objects/{object}` — from its **id**, the bare token `{project}` or `{object}` that the path is built from. Our code overloads the word `name` across three unrelated meanings:

1. a **bare id** that feeds a Pulumi argument (`project=`, `dataset_id=`);
1. a **qualified path** (`projects/_/buckets/my-bucket/...`) in an IAM condition expression;
1. the **Pulumi logical name** — a resource's first positional argument, the program-local URN handle, which is neither a cloud id nor a path.

A reader who sees a bare `name` parameter cannot tell which of the three it holds. Pulumi's own API deepens the confusion: `gcp.storage.Bucket.name` returns the bare bucket id, not `buckets/{id}`, so the SDK itself calls an id a `name`.

### The convention

- **`*_id`** — the bare identifier token (`project_id`, `bucket_id`, `object_id`). This is what feeds a Pulumi `project=` / `dataset_id=` argument or a resource's `name=`.
- **`*_resource_name` / `*_path`** — a full `{collection}/{id}` path (`projects/{project}`, `buckets/{bucket}/objects/{object}`), the form an IAM condition or a fully-qualified reference needs.
- **`logical_name`** — the Pulumi URN name, a resource's first positional argument. Name it for what it is (a program-local handle), never `*_name` (which reads as a cloud identifier) and not `resource_name`, which AIP-122 already spends on the full path above.
- **Prefer `project_id` over bare `project`** in our own signatures, even though Pulumi's own argument is `project=`. The `_id` suffix states which of the three meanings the value carries; matching Pulumi's looser spelling would reimport the ambiguity.

### Worked example

`core/src/gcs.py::create_gcs_bucket` shows the trap. It takes `bucket_name` (actually the Pulumi logical name, passed as the resource's first positional argument) alongside `gcp_name` (the actual bucket id, passed as `name=`):

```python
def create_gcs_bucket(bucket_name: str, ..., gcp_name: str | None = None):
    bucket = gcp.storage.Bucket(
        bucket_name,            # the Pulumi logical name (a URN handle)
        name=gcp_name or bucket_name,  # the bucket id
        ...
    )
```

Under this convention the first argument is a `logical_name` and the id argument is a `bucket_id`, so a reader can tell them apart without tracing the dataflow. `project` vs `project_id` vs `project_name` is similarly ad hoc across the flat `core/` modules and reads the same way once `*_id` is the rule.

### Enforcement

Deciding whether a given `*_name` holds a bare id, a path, or a URN name is dataflow-dependent, and a linter sees only the identifier, so the full convention is judgment, not a rule:

- **Judgment** — the `common-style-review` naming lens (section Q) reviews the subtle name / id / logical-name calls on a changed line.
- **Mechanical (candidate, not yet built)** — a narrow, low-false-positive rule could reach only the unambiguous subset: a bare parameter named exactly `project` / `bucket` / `dataset` (suggest the `_id` suffix), or a `*_name` parameter passed straight to a Pulumi `project=` / id argument. Left as a possible follow-up; the judgment lens is the primary enforcement.

## Facet 2 — Google Cloud product and brand names in prose

Docstrings and comments mix retired shorthand with current names: `GCS` for Cloud Storage, `GCP` for Google Cloud, `Big Query` for BigQuery. Google retired `GCP` and `Google Cloud Platform` as the umbrella brand (circa 2022) in favor of Google Cloud, and each product has one canonical name: Cloud Storage, Cloud Monitoring, Cloud Logging, Compute Engine, Cloud SQL, Pub/Sub, Secret Manager, BigQuery. Prose that mixes the old shorthand with the current name reads as two systems.

### The convention

Write the current brand and product names in docstring and comment prose. This governs **prose only** — a code identifier (`gcp.storage`, `import pulumi_gcp`) is out of scope, since `gcp` is the established SDK spelling.

### Enforcement

- **Mechanical** — `repostyle` **RS050** (`disfavored-gcp-term`), a warning that `--fix` rewrites in place, over docstring and comment prose. It gates on a curated, unambiguous map to keep false positives low; a term inside a backtick span, a URL, glued to a hyphen, or in an `Args:` caption is left alone. The shipped map:

  | Disfavored | Preferred |
  | -- | -- |
  | `GCP` | `Google Cloud` |
  | `Google Cloud Platform` | `Google Cloud` |
  | `GCS` | `Cloud Storage` |
  | `GCE` | `Compute Engine` |
  | `Big Query` | `BigQuery` |
  | `BigTable` | `Bigtable` |
  | `PubSub` / `Pub Sub` | `Pub/Sub` |

- **Left to review** — a bare `Storage`, `Monitoring`, `Logging`, or `Stackdriver` is too often an ordinary English word, or maps to more than one product, to rewrite mechanically. Prefer `Cloud Storage`, `Cloud Monitoring`, and `Cloud Logging` in prose, but the rule does not enforce the single-word forms; review does.
