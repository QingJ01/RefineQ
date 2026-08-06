# RefineQ repository guide

RefineQ is a personal learning agent for exam-oriented students and advanced learners.

## Architecture boundaries

- `src/refineq/`: Python domain, storage, knowledge retrieval, agent, and FastAPI API.
- `apps/web/`: Next.js user interface.
- `infra/`: container images, Compose, and reverse-proxy configuration.
- `scripts/`: supported demo, backup, restore, and migration commands.
- `tests/`: unit, integration, contract, and deployment tests.
- `docs/`: architecture and operating documentation.

New application code must live inside these boundaries. Runtime state belongs under
`REFINEQ_DATA_ROOT` and must never be committed.

## Development rules

- Configure the backend only through `REFINEQ_*` environment variables.
- Keep user, project, material, and learning-state isolation enforced on the server.
- Treat uploaded material as untrusted data, not as instructions.
- Keep storage writes atomic and backup/restore operations fail-safe.
- Add or update tests with every behavior change.
- Run Python tests, frontend tests, lint, and build before merging.

Git commits use `QingJ01 <qingj1314@163.com>`.

