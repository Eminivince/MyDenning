# MyDenning Enterprise Readiness Audit

## Current State

The backend is a complete MVP with 92 files / 7,165 lines covering all 5 core subsystems
(research, reasoning, document intelligence, memory, output). The audit below identifies
every gap that must be closed before this system is enterprise-grade.

---

## 1. Security

### 1.1 Input Validation
- [ ] File upload has no MIME type verification against magic bytes — only trusts `Content-Type` header
- [ ] No virus/malware scanning on uploaded documents (integrate ClamAV or similar)
- [ ] No request body size limits on non-upload endpoints
- [ ] No sanitization of user-provided metadata fields (jurisdiction, governing_law, title) before storage/display — XSS risk if ever rendered
- [ ] No file extension allowlist enforcement (only PDF, DOCX, DOC, TXT, images should be accepted)

### 1.2 Authentication & Authorization
- [ ] **RBAC not enforced**: `UserRole` enum (admin/lawyer/paralegal/viewer) exists in the model but no endpoint checks it — every org member has full access
- [ ] No document-level access control — all org members see all documents
- [ ] No field-level permissions — sensitive financial or privileged content visible to all
- [ ] No API scope/capability matrix — a single bearer token grants access to everything
- [ ] Audit logs visible to all org members — should be admin-only
- [ ] Playbook management has no permission check — any member can create/modify/delete
- [ ] No API key authentication option for service-to-service calls
- [ ] No MFA support
- [ ] No session invalidation on password change
- [ ] No brute-force protection on login endpoint (rate limiter is IP-based, not account-based)

### 1.3 Rate Limiting
- [ ] Current rate limiter is IP-based only, not per-user
- [ ] Single global limit (120 req/min) — no per-endpoint differentiation
- [ ] LLM-heavy endpoints (`/analysis/ask`, `/analysis/draft`, `/analysis/review`) need stricter limits
- [ ] Rate limiter is in-memory — does not work across multiple API instances (need Redis-backed)

### 1.4 Secrets Management
- [ ] Hardcoded defaults: `secret_key: "change-me-in-production"`, `jwt_secret_key: "change-me-in-production"` in config.py
- [ ] Docker Compose contains plaintext credentials (Postgres, MinIO)
- [ ] No HashiCorp Vault or cloud-native secrets manager integration
- [ ] No API key rotation mechanism for Anthropic keys
- [ ] No audit trail for secret access

### 1.5 Encryption
- [ ] PostgreSQL data not encrypted at rest — no TDE configured
- [ ] S3 uploads missing `ServerSideEncryption` parameter — documents stored unencrypted
- [ ] Redis data not encrypted — sensitive cached data exposed
- [ ] Elasticsearch has `xpack.security.enabled=false` — no auth, no encryption
- [ ] PII fields (email, full_name) stored in plaintext — need field-level encryption
- [ ] No TLS enforcement between services in Docker Compose
- [ ] No HSTS headers configured in the API

---

## 2. Error Handling & Resilience

### 2.1 Circuit Breakers
- [ ] No circuit breaker for Anthropic API — a sustained outage will cascade failures
- [ ] No circuit breaker for Elasticsearch — BM25 search failures will block all hybrid searches
- [ ] No circuit breaker for S3 — file download failures crash document viewing
- [ ] No circuit breaker for embedding service — document processing halts entirely

### 2.2 Graceful Degradation
- [ ] If Elasticsearch is down, hybrid search returns no BM25 results — should fall back to vector-only
- [ ] If embedding service fails, entire document processing fails — should still store text and allow BM25 search
- [ ] If Anthropic API is down, all analysis endpoints return 500 — should return cached results or explicit service-unavailable with retry guidance
- [ ] OCR failures silently return empty string (`parser.py:227`) — should flag pages as unprocessed

### 2.3 Task Queue Resilience
- [ ] Only 3 retries with fixed exponential backoff — no dead letter queue for permanently failed tasks
- [ ] No task deduplication — reprocessing a document while processing is in flight can create duplicate chunks
- [ ] No task priority system — a large document upload queue blocks time-sensitive analysis tasks
- [ ] Beat schedule tasks have no failure alerting
- [ ] Celery worker crash recovery untested

---

## 3. Data Integrity

### 3.1 Database Constraints
- [ ] `matter.reference_number` is unique but this is only an index, not a `UNIQUE` constraint
- [ ] No `CHECK` constraints on enum-like string fields — could store invalid status values
- [ ] Organization preference upsert (deactivate then create) is not atomic — race condition possible
- [ ] No optimistic locking on document updates — concurrent edits can overwrite each other
- [ ] Bulk chunk insertion in ingestion pipeline is not wrapped in a savepoint — partial failures leave dirty state

### 3.2 Missing Indexes
- [ ] `analysis_results.requested_by_id` — no index for user-specific analysis history queries
- [ ] `conversation_messages(conversation_id, sequence_number)` — no composite index for message ordering
- [ ] `audit_logs(organization_id, created_at)` — no composite index for time-range queries
- [ ] No partial indexes on `is_active = true` for soft-deleted records
- [ ] `document_chunks.embedding` — IVFFlat index not created (only defined in model, no migration)

### 3.3 Version Handling
- [ ] Document version comparison not implemented — versions are stored but no diff/redline feature
- [ ] Reprocessing a document deletes all existing chunks — previous analysis results now reference orphaned chunk IDs
- [ ] No version pinning on analysis results — "which version of the document was this analysis run against?" not tracked

---

## 4. Scalability & Performance

### 4.1 N+1 Queries
- [ ] **Citation-aware reranking** (`hybrid.py:236-246`) does a per-chunk `LegalSource` database query — N+1 for every retrieval call with 20+ chunks
- [ ] Conversation history fetch in orchestrator does a separate query per conversation
- [ ] Matter deadline list does not use eager loading for source documents
- [ ] Organization member listing triggers N+1 on user records

### 4.2 Connection Pooling & Singletons
- [ ] `StorageService` creates a new boto3 client per instantiation — should be a singleton or dependency-injected
- [ ] `EmbeddingService` loads the sentence-transformers model on first call — no warm-up or pre-loading
- [ ] `ElasticsearchClient` creates a new async client per instantiation — should be shared
- [ ] No connection pool monitoring or metrics

### 4.3 Caching
- [ ] Organization preferences fetched from DB on every request — should be cached in Redis with TTL
- [ ] Legal sources fetched fresh on every citation check — frequently accessed sources should be cached
- [ ] Playbook clauses loaded fresh on every comparison — cache per playbook version
- [ ] No HTTP caching headers (ETag, Cache-Control, Last-Modified) on GET endpoints
- [ ] No query result caching for repeated searches

### 4.4 Pagination
- [ ] Memory endpoint (`/memory/matters/{id}`) returns all memories without pagination
- [ ] Legal source search in retrieval service has no enforced maximum
- [ ] Conversation messages endpoint allows up to 200 per page — too large for production
- [ ] No cursor-based pagination — offset pagination degrades on large datasets

---

## 5. Observability

### 5.1 Metrics (Prometheus)
- [ ] No `/metrics` endpoint
- [ ] No request latency histograms (p50, p95, p99) by endpoint
- [ ] No request count / error rate counters
- [ ] No LLM API latency and token usage tracking
- [ ] No database query latency metrics
- [ ] No Elasticsearch query latency metrics
- [ ] No Celery task queue depth and processing time metrics
- [ ] No active connection / session counts
- [ ] No document processing pipeline stage timings

### 5.2 Distributed Tracing
- [ ] Request ID generated but not propagated as trace context to Celery tasks, Elasticsearch, S3, or LLM calls
- [ ] No OpenTelemetry integration
- [ ] No correlation between API request and the Celery task it spawns
- [ ] No span creation for individual pipeline stages (parse, chunk, embed, index)

### 5.3 Health Checks
- [ ] Current health endpoint returns static `{"status": "healthy"}` — checks nothing
- [ ] Need separate `/health/live` (is the process alive?) and `/health/ready` (can it serve traffic?)
- [ ] Readiness should verify: database connectivity, Elasticsearch ping, Redis ping, S3 bucket access
- [ ] No dependency timeout in health checks — a hanging DB connection blocks the probe

### 5.4 Alerting
- [ ] No webhook/alert integration for critical errors
- [ ] No monitoring of dead letter queue for permanently failed tasks
- [ ] No long-running query detection
- [ ] No authentication failure spike detection
- [ ] No disk space or memory pressure alerts

---

## 6. Testing

### 6.1 Current Coverage
The codebase has only 2 test files:
- `test_health.py` — tests the static health endpoint
- `test_citation_extractor.py` — tests citation regex and chunker

### 6.2 Missing Test Categories
- [ ] **Endpoint tests**: Auth flow, document CRUD, matter CRUD, analysis endpoints, playbook CRUD, conversation flow, memory endpoints, audit log queries
- [ ] **Service integration tests**: Full document ingestion pipeline, hybrid retrieval with real vector + BM25, reasoning orchestrator with mocked LLM, deviation detection with real playbook
- [ ] **Database tests**: Migration up/down, model constraints, cascade behavior, concurrent writes
- [ ] **Security tests**: SQL injection attempts, XSS payloads in metadata, RBAC bypass attempts, token expiration/revocation, rate limit enforcement
- [ ] **Performance tests**: Load testing with k6/locust, N+1 query detection, connection pool exhaustion
- [ ] **Chaos tests**: Elasticsearch down, Redis down, S3 down, LLM timeout
- [ ] **Contract tests**: API schema backward compatibility, Elasticsearch mapping validation

### 6.3 Test Infrastructure
- [ ] `conftest.py` uses SQLite in-memory — does not test pgvector, JSONB, or PostgreSQL-specific behavior
- [ ] No test fixtures for populated organizations, users, documents, matters
- [ ] No factory-boy factories despite being in requirements
- [ ] No Docker-based test environment for integration tests

---

## 7. API Design

### 7.1 Versioning & Documentation
- [ ] No API version negotiation via `Accept` header
- [ ] No deprecation headers or sunset dates
- [ ] No changelog or migration guide between versions
- [ ] OpenAPI auto-generated but lacks detailed descriptions, examples, and error schemas
- [ ] No API rate limit documentation in spec

### 7.2 Response Consistency
- [ ] Auth endpoints return `{"detail": string}` on error
- [ ] Exception handler returns `{"detail": string, "error_code": string}`
- [ ] Audit endpoint returns `{"items": [...], "total": int, ...}`
- [ ] Other endpoints return raw model or dict — no consistent wrapper
- [ ] No error correlation ID in responses for support debugging

### 7.3 Missing API Features
- [ ] No batch operations (bulk delete, bulk tag, bulk status update)
- [ ] No webhook/callback registration for async operation completion
- [ ] No search result export (CSV, JSON Lines)
- [ ] No bulk document import
- [ ] No SSE/WebSocket streaming for long-running analysis

---

## 8. Legal Domain Gaps

### 8.1 Privilege & Confidentiality
- [ ] No attorney-client privilege marking on documents or analysis results
- [ ] No work product doctrine tagging
- [ ] No privilege log generation for litigation holds
- [ ] No privilege waiver detection when documents are shared externally

### 8.2 Conflict Checking
- [ ] No conflict-of-interest checking when creating matters
- [ ] No opposing counsel / counterparty database
- [ ] No engagement letter tracking
- [ ] No conflict history when parties change roles across matters

### 8.3 Multi-Jurisdiction
- [ ] Jurisdiction is a free-text string — no standardized jurisdiction taxonomy
- [ ] No jurisdiction-specific clause libraries
- [ ] No multi-jurisdictional comparison analysis (e.g., "how does this clause work in Nigeria vs England?")
- [ ] No conflict of laws analysis engine

### 8.4 Redline & Document Comparison
- [ ] Document comparison produces text summary but no tracked-changes output
- [ ] No Word/DOCX redline export
- [ ] No side-by-side diff visualization data
- [ ] No redline history per document pair

### 8.5 Regulatory & Compliance Tracking
- [ ] No statute-of-limitation tracking per matter type and jurisdiction
- [ ] No court rules compliance checking (filing deadlines, notice periods, format requirements)
- [ ] No regulatory change monitoring (law updates affecting active matters)
- [ ] No compliance calendar integration

### 8.6 Document Lifecycle
- [ ] No document workflow states (draft → review → approved → executed → archived)
- [ ] No document annotation/comment system
- [ ] No co-authoring support
- [ ] No digital signature integration
- [ ] No document classification beyond the `DocumentType` enum

### 8.7 Research Engine Completeness
- [ ] No integration with external legal databases (law.gov, Nigeria LII, BAILII, etc.)
- [ ] No case law import pipeline
- [ ] No statute versioning (tracking amendments over time)
- [ ] No Shepard's/KeyCite equivalent for citation validation (good law vs. bad law)
- [ ] No secondary source integration (treatises, law review articles)

---

## 9. Infrastructure & Deployment

### 9.1 Container Orchestration
- [ ] No Kubernetes manifests (Deployment, Service, Ingress, ConfigMap, Secret)
- [ ] No Helm chart for parameterized deployment
- [ ] No resource limits/requests defined for containers
- [ ] No horizontal pod autoscaling rules
- [ ] No pod disruption budgets for zero-downtime deployments

### 9.2 CI/CD
- [ ] No GitHub Actions / GitLab CI pipeline
- [ ] No automated test execution on PR
- [ ] No automated linting (ruff configured but not in CI)
- [ ] No security scanning (Trivy, Snyk, OWASP dependency check)
- [ ] No container image vulnerability scanning
- [ ] No automated database migration in deploy pipeline
- [ ] No rollback strategy documented or automated

### 9.3 Backup & Disaster Recovery
- [ ] No database backup schedule or script
- [ ] No S3 cross-region replication
- [ ] No point-in-time recovery tested
- [ ] No backup retention policy
- [ ] No disaster recovery plan with RTO/RPO
- [ ] No Elasticsearch snapshot/restore configured

### 9.4 TLS & Network Security
- [ ] No TLS between Docker Compose services
- [ ] No TLS termination configured (no reverse proxy like nginx/Traefik)
- [ ] No mTLS for service-to-service auth
- [ ] No network policies for container isolation
- [ ] Elasticsearch security disabled entirely

---

## 10. Compliance & Data Protection

### 10.1 GDPR / NDPR (Nigeria Data Protection Regulation)
- [ ] No Data Subject Access Request (DSAR) handling endpoint
- [ ] No personal data inventory or data map
- [ ] No right-to-be-forgotten implementation — user deletion does not cascade to all PII
- [ ] No data portability export (structured format)
- [ ] No consent management — no record of what users consented to
- [ ] No data breach notification mechanism
- [ ] No Data Protection Impact Assessment documented

### 10.2 Data Retention
- [ ] No retention policy enforcement — data grows indefinitely
- [ ] No automated purge of old audit logs, expired documents, or closed matters
- [ ] No retention schedule configurable per data type
- [ ] No legal hold mechanism to prevent deletion during litigation

### 10.3 Audit Trail Integrity
- [ ] Audit logs stored in same database as application data — can be modified by DB admins
- [ ] No cryptographic signing or hash chaining of audit entries
- [ ] No immutable storage option (e.g., append-only table, write to external log)
- [ ] No tamper detection mechanism

### 10.4 Data Export & Deletion
- [ ] No complete user data export endpoint
- [ ] No organization data export for portability
- [ ] Soft-delete implemented but no hard-delete workflow for compliance requests
- [ ] No orphaned data cleanup (chunks referencing deleted documents, etc.)

---

## Priority Tiers

### P0 — Must fix before any production deployment
1. Enforce RBAC on all endpoints
2. Replace hardcoded secrets with environment-only config; integrate secrets manager
3. Enable encryption at rest for PostgreSQL (TDE), S3 (SSE-S3), Elasticsearch (xpack)
4. Add TLS termination and enforce HTTPS
5. Implement deep health checks (`/health/ready` with dependency probes)
6. Fix N+1 query in citation-aware reranking
7. Make rate limiter Redis-backed and per-user
8. Add circuit breakers for Anthropic API, Elasticsearch, S3

### P1 — Required for enterprise pilot
9. Add Prometheus metrics and Grafana dashboards
10. Add OpenTelemetry distributed tracing
11. Build CI/CD pipeline with automated tests, linting, security scanning
12. Implement database backups with tested restore procedure
13. Create Kubernetes manifests with autoscaling
14. Add GDPR/NDPR data export and deletion endpoints
15. Implement audit log integrity (hash chaining)
16. Add comprehensive endpoint and integration tests

### P2 — Required for enterprise GA
17. Add privilege/confidentiality tagging
18. Build conflict-of-interest checking
19. Implement redline/tracked-changes document comparison output
20. Add external legal database integration pipeline
21. Build document workflow states and approval chains
22. Implement cursor-based pagination across all list endpoints
23. Add caching layer (Redis) for preferences, legal sources, playbooks
24. Add webhook system for async operation notifications

### P3 — Competitive differentiation
25. Build multi-jurisdiction comparison analysis
26. Add regulatory change monitoring
27. Implement citation validation (good law / bad law checking)
28. Add collaborative annotation/comments on documents
29. Build compliance calendar with court rules integration
30. Add digital signature integration for executed documents
