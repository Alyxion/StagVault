# StagVault Documentation

This directory contains technical documentation for StagVault.

## Contents

### Architecture
- [CLI Modes](./cli-modes.md) - CLI testing in 3 modes (Python, REST, Static)
- [Source Hierarchy](./source-hierarchy.md) - 2-level source tree structure
- [Filtering](./filtering.md) - Filtering system design (source tree + license only)
- [Static Site](./static-site.md) - Static site architecture and limitations

### Configuration
- [Project Structure](./structure.md) - Overview of directories, config files, and interfaces
- [Configuration](./configuration.md) - YAML source configuration reference
- [Aliases](./aliases.md) - Alias system for human-readable names and search terms

### Integration
- [Providers](./providers.md) - External API provider overview with license/restriction links

### Quality
- [Testing](./testing.md) - Testing requirements and 100% coverage

## Quick Links

- [CLAUDE.md](../CLAUDE.md) - Development guidelines and API usage
- [configs/sources/](../configs/sources/) - Source configuration files

## Key Design Decisions

1. **CLI Testing Modes**: Python (direct), REST (FastAPI), Static (same as web)
2. **Source Hierarchy**: Max 2 levels deep (Category → Subcategory → Source)
3. **Sidebar Filters**: Only source tree and license (categories via search)
4. **Static Mode**: Git sources only (no dynamic API providers)
5. **Test Coverage**: 100% required, with mode parity verification
