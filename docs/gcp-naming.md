# Google Cloud naming conventions

Two kinds of Google Cloud naming drift without a written convention. This doc records both and maps each to the layer that enforces it. A `repostyle` rule reaches the mechanizable subset, and review against this doc covers what resists a rule.

The two facets are independent. The first is about identifiers in our own code. The second is about product and brand names in prose.

## Facet 1: identifier name versus id (AIP-122)

Google's [AIP-122](https://google.aip.dev/122) distinguishes a resource's **name**, the qualified path `projects/{project}` or `buckets/{bucket}/objects/{object}`, from its **id**, the bare token `{project}` or `{object}` that the path is built from. Our code overloads the word `name` across three unrelated meanings:

1. A **bare id** that feeds a Pulumi argument, such as `project=` or `dataset_id=`.
1. A **qualified path** such as `projects/_/buckets/my-bucket/...`, used in an IAM condition expression.
1. The **Pulumi logical name**, a resource's first positional argument. This is the program-local URN handle, which is neither a cloud id nor a path.

A reader who sees a bare `name` parameter cannot tell which of the three it holds. Pulumi's own API deepens the confusion: `gcp.storage.Bucket.name` returns the bare bucket id rather than `buckets/{id}`, so the SDK itself calls an id a name.

### The convention

- **`*_id`** is the bare identifier token: `project_id`, `bucket_id`, `object_id`. This is what feeds a Pulumi `project=` or `dataset_id=` argument, or a resource's `name=`.
- **`*_resource_name` or `*_path`** is a full `{collection}/{id}` path, such as `projects/{project}` or `buckets/{bucket}/objects/{object}`. This is the form an IAM condition or a fully-qualified reference needs.
- **`logical_name`** is the Pulumi URN name, a resource's first positional argument. Name it for what it is, a program-local handle. Never call it `*_name`, which reads as a cloud identifier, and not `resource_name`, which AIP-122 already spends on the full path above.
- **Prefer `project_id` over a bare `project`** in our own signatures, even though Pulumi's own argument is `project=`. The `_id` suffix states which of the three meanings the value carries, and matching Pulumi's looser spelling would reimport the ambiguity.

### Worked example

A bucket-creating helper shows the trap. It takes `bucket_name`, which is actually the Pulumi logical name passed as the resource's first positional argument, alongside `gcp_name`, which is the actual bucket id passed as `name=`:

```python
def create_bucket(bucket_name: str, ..., gcp_name: str | None = None):
    bucket = gcp.storage.Bucket(
        bucket_name,                   # the Pulumi logical name (a URN handle)
        name=gcp_name or bucket_name,  # the bucket id
        ...
    )
```

Under this convention the first argument is a `logical_name` and the id argument is a `bucket_id`, so a reader can tell them apart without tracing the dataflow. The `project`, `project_id`, and `project_name` trio drifts the same way, and reads the same way once `*_id` is the rule.

### Enforcement

Deciding whether a given `*_name` holds a bare id, a path, or a URN name is dataflow-dependent, and a linter sees only the identifier. The full convention is therefore judgment, not a rule.

**Review** covers the subtle name, id, and logical-name calls on a changed line, and remains the primary enforcement.

**RS051** (`gcp-bare-identifier`) mechanizes the unambiguous subset as a warning: a string-typed parameter named exactly for a Google Cloud resource collection (`project`, `bucket`, `dataset`, `topic`, `subscription`, `instance`) wants the `_id` suffix. A `*_name` parameter passed straight to a Pulumi id argument stays with review, since that call is dataflow-dependent.

## Facet 2: Google Cloud product and brand names in prose

Docstrings and comments mix retired shorthand with current names: `GCS` for Cloud Storage, `GCP` for Google Cloud, `Big Query` for BigQuery. Google retired `GCP` and `Google Cloud Platform` as the umbrella brand around 2022 in favor of Google Cloud, and each product has one canonical name: Cloud Storage, Cloud Monitoring, Cloud Logging, Compute Engine, Cloud SQL, Pub/Sub, Secret Manager, BigQuery. Prose that mixes the old shorthand with the current name reads as two systems.

### The convention

Write the current brand and product names in docstring and comment prose. This governs prose only. A code identifier such as `gcp.storage` or `import pulumi_gcp` is out of scope, since `gcp` is the established SDK spelling.

### Enforcement

**RS050** (`disfavored-gcp-term`) is a warning that `--fix` rewrites in place, over docstring and comment prose. It gates on a curated, unambiguous map to keep false positives low, and leaves alone a term inside a backtick span, in a URL, glued to a hyphen, or in an `Args:` caption. The shipped map:

| Disfavored | Preferred |
| -- | -- |
| `GCP` | `Google Cloud` |
| `Google Cloud Platform` | `Google Cloud` |
| `GCS` | `Cloud Storage` |
| `GCE` | `Compute Engine` |
| `Big Query` | `BigQuery` |
| `BigTable` | `Bigtable` |
| `PubSub` or `Pub Sub` | `Pub/Sub` |

**Review** covers the rest. A bare `Storage`, `Monitoring`, `Logging`, or `Stackdriver` is too often an ordinary English word, or maps to more than one product, to rewrite mechanically. Prefer `Cloud Storage`, `Cloud Monitoring`, and `Cloud Logging` in prose, but the rule does not enforce the single-word forms.
