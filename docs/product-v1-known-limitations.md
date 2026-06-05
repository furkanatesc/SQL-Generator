# Product V1 Known Limitations

The V1 release establishes a robust foundation for secure and validated text-to-SQL operations. However, to maintain scope and stability, the following technical constraints are explicitly acknowledged for this release. These are not defects, but intentional scoping decisions.

## Identity & Access Management
- **No multi-tenant auth**: The system operates under a single environment scope. It does not support tenant-isolated authentication contexts out of the box.
- **No full RBAC**: Role-Based Access Control is not implemented. Any valid API key has full authorization to invoke the endpoints provided by the backend.

## Deployment & Infrastructure
- **No managed cloud deployment manifest**: We provide Docker images and runbooks, but no native Terraform, CloudFormation, or managed cloud specific configuration files are provided in the V1 core repo.
- **SQLite-backed default deployment profile**: The default operational database uses SQLite. It is suitable for the current load but lacks the distributed concurrency features of a clustered database.

## Observability
- **No external APM/tracing backend**: While logs and warnings are structured and centralized, the system does not integrate with external Application Performance Monitoring (APM) or distributed tracing platforms like Datadog or Jaeger by default.
