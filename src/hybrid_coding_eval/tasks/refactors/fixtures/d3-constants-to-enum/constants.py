"""Status-code string constants scattered across the codebase.

Refactor target: replace this module with a ``StrEnum`` (Python 3.11+)
class. Update every import site to use the enum member instead of the
string literal. ``==`` comparisons against bare string literals in
``workers.py`` / ``reporting.py`` / ``api.py`` should be updated to
compare against enum members. The string values on the wire must not
change (e.g. ``JobStatus.PENDING.value == "pending"``) so existing
persisted records keep working.
"""

# Lifecycle of a batch job
STATUS_PENDING = "pending"
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_TIMEOUT = "timeout"

# Priority bands
PRIORITY_LOW = "low"
PRIORITY_NORMAL = "normal"
PRIORITY_HIGH = "high"
PRIORITY_CRITICAL = "critical"

# Destination / sink types
SINK_S3 = "s3"
SINK_GCS = "gcs"
SINK_LOCAL = "local"
SINK_HTTP = "http"

# Retry strategies
RETRY_NONE = "none"
RETRY_FIXED = "fixed"
RETRY_EXPONENTIAL = "exponential"

# Severity
SEVERITY_DEBUG = "debug"
SEVERITY_INFO = "info"
SEVERITY_WARN = "warn"
SEVERITY_ERROR = "error"
