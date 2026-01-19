# Testing Requirements

StagVault requires comprehensive testing to ensure consistent behavior across all access modes.

## Coverage Requirement

**100% unit test coverage** is required for:

- All filtering logic (source tree, license filters)
- All search functions (grouped, ungrouped, prefix matching)
- All CLI commands
- Static/REST/Python mode parity
- Alias resolution
- Thumbnail generation

## Test Structure

```
tests/
├── conftest.py                    # Shared fixtures
├── test_search.py                 # Search functionality
├── test_filtering.py              # Filter logic
├── test_cli.py                    # CLI commands
├── test_static_index.py           # Static index builder
├── test_mode_parity.py            # Cross-mode parity tests
├── models/
│   └── test_source.py             # Data models
├── providers/
│   ├── test_base.py               # Base provider
│   ├── test_pixabay.py            # Pixabay provider
│   ├── test_pexels.py             # Pexels provider
│   ├── test_unsplash.py           # Unsplash provider
│   ├── test_cache.py              # Provider cache
│   └── test_registry.py           # Provider registry
├── thumbnails/
│   ├── test_renderer.py           # Thumbnail rendering
│   └── test_cache.py              # Thumbnail cache
└── integration/
    └── test_providers.py          # Real API tests
```

## Test Modes

Tests must verify behavior across all three modes using parameterized tests:

```python
import pytest

@pytest.mark.parametrize("mode", ["python", "rest", "static"])
def test_search_returns_results(mode, vault_fixture):
    """Search should return results in all modes."""
    results = search("arrow", mode=mode)
    assert len(results) > 0

@pytest.mark.parametrize("mode", ["python", "rest", "static"])
def test_source_filter_excludes(mode, vault_fixture):
    """Excluding a source should remove its items."""
    all_results = search("arrow", mode=mode)
    filtered = search("arrow", mode=mode, exclude_sources=["heroicons"])

    assert len(filtered) < len(all_results)
    assert not any(r.source_id == "heroicons" for r in filtered)

@pytest.mark.parametrize("mode", ["python", "rest", "static"])
def test_license_filter(mode, vault_fixture):
    """License filter should work in all modes."""
    results = search("arrow", mode=mode, license="MIT")
    assert all(r.license == "MIT" for r in results)
```

## Expected Behavior Tests

Specific search behaviors must be verified:

### Flag Search Tests

```python
def test_flag_search_us():
    """Search 'US' should return US flags first (waved and flat)."""
    results = search("US")

    # Top results should be US flags
    top_names = [r.name.lower() for r in results[:4]]
    assert any("united states" in n or n == "us" for n in top_names)

    # Should have both waved and flat variants
    styles = {r.style for r in results[:4]}
    assert "waved" in styles or "flat" in styles

def test_flag_search_de():
    """Search 'DE' should return German flags first."""
    results = search("DE")

    top_names = [r.name.lower() for r in results[:4]]
    assert any("germany" in n or n == "de" for n in top_names)

def test_flag_search_both_variants():
    """Flag searches should return both waved and non-waved variants."""
    for query in ["US", "DE", "FR", "JP"]:
        results = search(query)
        styles = {r.style for r in results[:10] if "flag" in r.name.lower()}
        # Should have multiple style variants
        assert len(styles) >= 1
```

### Alias Resolution Tests

```python
def test_emoji_alias_search():
    """Emoji should be findable by name, not just codepoint."""
    # Search by display name
    results = search("grinning face")
    assert len(results) > 0
    assert any("grinning" in r.name.lower() for r in results)

def test_emoji_alias_synonyms():
    """Emoji aliases should work."""
    # "smile" is an alias for "grinning face"
    results = search("smile")
    assert any("grinning" in r.name.lower() or "smile" in r.name.lower()
               for r in results)
```

### Source Tree Tests

```python
def test_source_tree_hierarchy():
    """Source tree should be max 2 levels deep."""
    tree = get_source_tree()

    for category, subcats in tree.items():
        assert isinstance(subcats, dict)
        for subcat, sources in subcats.items():
            # Sources should be leaf nodes (list of IDs)
            assert isinstance(sources, list)
            assert all(isinstance(s, str) for s in sources)

def test_parent_checkbox_excludes_children():
    """Unchecking parent should exclude all children."""
    # Exclude "Icons" subcategory
    results = search("arrow", exclude_subcategory=["Icons"])

    icon_sources = ["phosphor-icons", "lucide", "heroicons", "tabler-icons", "feather"]
    assert not any(r.source_id in icon_sources for r in results)
```

## Mode Parity Tests

Ensure identical behavior across modes:

```python
@pytest.mark.parametrize("query", ["arrow", "home", "US", "grinning face"])
def test_search_parity(query):
    """Same query should return same results across modes."""
    python_results = search(query, mode="python")
    rest_results = search(query, mode="rest")
    static_results = search(query, mode="static")

    # Same number of results (static may have fewer due to no dynamic sources)
    # Compare only git sources for parity
    git_sources = ["phosphor-icons", "lucide", "heroicons", "tabler-icons", "feather", "noto-emoji"]

    python_git = [r for r in python_results if r.source_id in git_sources]
    rest_git = [r for r in rest_results if r.source_id in git_sources]
    static_git = static_results  # Static only has git sources

    assert len(python_git) == len(rest_git) == len(static_git)

    # Same IDs in same order
    assert [r.id for r in python_git] == [r.id for r in rest_git] == [r.id for r in static_git]
```

## Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage report
poetry run pytest --cov=stagvault --cov-report=html

# Run specific test file
poetry run pytest tests/test_search.py

# Run mode parity tests only
poetry run pytest tests/test_mode_parity.py

# Run with verbose output
poetry run pytest -v

# Run tests matching pattern
poetry run pytest -k "flag_search"
```

## Test Markers

```python
@pytest.mark.slow          # Slow-running tests
@pytest.mark.integration   # Tests requiring real API keys
@pytest.mark.mock          # Tests using mocked responses
@pytest.mark.parity        # Cross-mode parity tests
```

```bash
# Skip slow tests
poetry run pytest -m "not slow"

# Run only integration tests
poetry run pytest -m integration
```

## Fixtures

Common fixtures in `conftest.py`:

```python
@pytest.fixture
def vault():
    """Configured StagVault instance."""
    return StagVault("./test_data", "./test_configs")

@pytest.fixture
def static_index(tmp_path):
    """Built static index for testing."""
    builder = StaticIndexBuilder(vault)
    builder.build(tmp_path)
    return tmp_path

@pytest.fixture
def api_client(vault):
    """FastAPI test client."""
    app = create_app(vault)
    return TestClient(app)
```

## CI/CD Integration

Tests run automatically on:
- Every push to main
- Every pull request
- Nightly builds (including slow/integration tests)

Coverage must remain at 100% for merges to be accepted.
