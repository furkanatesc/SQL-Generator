# Product V1 Release Notes

We are thrilled to announce the official release of SQL-Generator Product V1! This release marks the completion of our foundational text-to-SQL backend.

## Core Features
- **Natural Language to SQL Engine**: High-accuracy translation of natural language queries into valid SQL, powered by strict semantic evaluation profiles.
- **SQL Validation & Safety**: Proactive interception of dangerous queries (e.g., `DROP TABLE`, `DELETE`, schema modifications) via `UNSAFE_QUERY_DETECTED` guards.

## Security & Configuration
- **API Key Authentication**: Simple, secure endpoint protection.
- **CORS Management**: Explicit origin allowlisting for secure front-end integrations.
- **Fail-Fast Configuration**: Immediate container exit on missing critical configurations.

## Observability & Operations
- **Liveness/Readiness Endpoints**: Robust `/health` and `/ready` endpoints for operational smoke checks and future orchestration integrations.
- **Docker-native Deployment**: Immutable image architecture with detailed rollout and rollback runbooks.

## Known Limitations
Please refer to the `product-v1-known-limitations.md` document for scoping constraints regarding multi-tenant auth, RBAC, and APM.
