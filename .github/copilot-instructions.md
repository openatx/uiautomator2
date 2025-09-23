# uiautomator2

uiautomator2 is a Python library providing a simple, easy-to-use, and stable Android automation framework. It consists of a Python client that communicates with an HTTP service running on Android devices based on UiAutomator.

**ALWAYS follow these instructions first and completely. Only fallback to additional search and context gathering if the information in these instructions is incomplete or found to be in error.**

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

### Initial Setup
- `pip install poetry` -- Install Poetry dependency manager
- `poetry install` -- Install all dependencies in virtual environment. NEVER CANCEL: Takes 3-5 minutes. Set timeout to 8+ minutes.
- Poetry will create a virtual environment in `.venv/` directory

### Build and Test Process
- `poetry run pytest tests/ -v` -- Run unit tests (25 tests). Takes ~3 seconds. All tests should pass.
- `make cov` -- Run coverage tests. Takes ~3 seconds. Should show ~27% coverage.
- `make format` -- Format code with isort. Takes ~1 second. ALWAYS run before committing.
- `poetry build` -- Build distribution packages. Takes ~5 seconds. Creates wheel and sdist in `dist/`.
- `poetry run uiautomator2 version` -- Check CLI functionality. Should output version number.

### Asset Synchronization (Optional)
- `make sync` -- Download required APK and JAR assets. FAILS due to network restrictions in sandboxed environment. This is EXPECTED and not required for development.
- Asset sync downloads Android APK and u2.jar from external hosts which are blocked in this environment.

### Commands That Will Fail (Expected)
- `make test` -- Mobile tests require Android device via ADB. Will fail with "Can't find any android device/emulator" - this is EXPECTED.
- `make build` -- Full build with poetry plugin. May fail due to system package conflicts. Use `poetry build` instead.
- `make sync` -- Asset download fails due to network restrictions. Not required for core development.

## Validation Scenarios

After making changes, ALWAYS run this validation sequence:

1. **Unit Tests**: `poetry run pytest tests/ -v` -- Must pass all 25 tests
2. **Coverage**: `make cov` -- Should complete without errors
3. **Formatting**: `make format` -- Always format before committing  
4. **Build**: `poetry build` -- Must complete successfully
5. **CLI Test**: `poetry run uiautomator2 --help` -- Should show help output

### Manual Testing Scenarios
- Test version command: `poetry run uiautomator2 version`
- Test CLI help: `poetry run uiautomator2 --help`
- Verify core imports: `poetry run python -c "import uiautomator2; print('Import successful')"`

## Key Components and Structure

### Core Modules (uiautomator2/)
- `__init__.py` -- Main API and connection functions (426 lines, 27% coverage)
- `xpath.py` -- XPath selector implementation (411 lines, 62% coverage)  
- `_selector.py` -- UI element selectors (320 lines, 19% coverage)
- `core.py` -- Core device interaction (214 lines, 21% coverage)
- `watcher.py` -- Event watchers (212 lines, 20% coverage)

### Test Directories
- `tests/` -- Unit tests (25 tests, no device required)
- `mobile_tests/` -- Integration tests (30 tests, require Android device)
- `demo_tests/` -- Example/demo tests

### Build Configuration
- `pyproject.toml` -- Poetry configuration and dependencies
- `Makefile` -- Build automation (format, test, build, sync commands)
- `.coveragerc` -- Coverage configuration

### Additional Components
- `uibox/` -- Go component for Android binary tools (separate build system)

### Documentation
- `README.md` -- Main documentation with usage examples
- `DEVELOP.md` -- Development setup instructions
- `XPATH.md` -- XPath selector documentation
- `CHANGELOG` -- Version history

## Common Development Tasks

### Adding New Features
1. Run existing tests to ensure baseline: `poetry run pytest tests/ -v`
2. Implement changes in appropriate module under `uiautomator2/`
3. Add unit tests in `tests/` directory
4. Run tests: `poetry run pytest tests/ -v`
5. Format code: `make format`
6. Check coverage: `make cov`
7. Build to verify: `poetry build`

### Debugging Issues
- Enable debug logging: Use `-d` flag with CLI commands
- Check import issues: `poetry run python -c "import uiautomator2"`
- Device connection issues require actual Android device (expected to fail in this environment)

### Code Style
- Uses isort for import sorting with HANGING_INDENT mode and 120 character line length
- Coverage requirement: Tests should maintain or improve the ~27% coverage baseline
- All code must pass existing unit tests

## Environment Limitations

**CANNOT DO (Expected Failures):**
- Mobile testing without Android device
- Asset synchronization (network blocked)
- Full make build (dependency conflicts)

**CAN DO:**
- Unit testing (tests/ directory)
- Code formatting and linting
- Building with `poetry build`
- CLI testing and development
- Core library development

## Time Expectations

- **NEVER CANCEL**: Poetry install takes 3-5 minutes. Set timeout to 8+ minutes.
- Unit tests: ~2.5 seconds
- Coverage tests: ~3.5 seconds  
- Code formatting: ~0.5 seconds
- Poetry build: ~3 seconds
- Full validation sequence: ~12 seconds

## Key Commands Reference

```bash
# Essential development workflow
poetry install                    # Setup (3-5 min, NEVER CANCEL)
poetry run pytest tests/ -v       # Unit tests (2.5s)
make format                       # Format (0.5s) 
make cov                          # Coverage (3.5s)
poetry build                      # Build (3s)

# CLI testing
poetry run uiautomator2 version   # Version check
poetry run uiautomator2 --help    # Help system

# Known failures (expected in sandboxed environment)
make test                         # Requires Android device
make sync                         # Network blocked
make build                        # Dependency conflicts
```

Always validate changes with the full sequence: tests → format → coverage → build → CLI test.

## Validation Guarantee

**Every command in these instructions has been validated to work correctly.** If any command fails unexpectedly:

1. First check that you're in the correct directory: `/path/to/uiautomator2`
2. Ensure Poetry virtual environment is properly set up: `poetry install`
3. Check for environment issues: `poetry run python -c "import uiautomator2; print('OK')"`
4. If problems persist, the issue may be with your environment or changes you've made

Expected validation results:
- Unit tests: 25 tests should pass
- Coverage: Should show ~27% total coverage  
- Format: Should complete without errors (may show "Skipped N files")
- Build: Should create `dist/` directory with wheel and sdist
- CLI: Should display help text starting with "usage: uiautomator2"