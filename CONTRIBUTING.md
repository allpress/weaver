# Contributing to Weaver

Thanks for your interest in contributing to Weaver. This document covers how to get started.

## Development Setup

```bash
git clone https://github.com/dougallpress/weaver.git
cd weaver
npm install
npm test
```

## How to Contribute

### Reporting Issues

- Use GitHub Issues
- Include steps to reproduce, expected behavior, and actual behavior
- Include your environment (OS, Node version, etc.)

### Pull Requests

1. Fork the repo and create your branch from `main`
2. If you've added code, add tests
3. Ensure the test suite passes
4. Update documentation if you've changed APIs
5. Write a clear PR description

### Commit Messages

Use conventional commits:

```
feat: add context ingestion for git repos
fix: handle empty document arrays in weaver
docs: update architecture diagram
test: add integration tests for sync protocol
```

### Code Style

- TypeScript with strict mode
- Prefer explicit types over `any`
- Write tests for new functionality
- Keep functions focused and small

## Project Structure

```
src/
  core/        # Core weaving engine
  ingestion/   # Context source connectors
  graph/       # Relationship graph
  sync/        # Bidirectional sync protocol
  api/         # Public API surface
  plugins/     # Plugin system
tests/
  unit/
  integration/
docs/
```

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
