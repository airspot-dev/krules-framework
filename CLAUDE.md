# KRules Framework - Project Memory

## Project Overview
KRules Framework v2.0+ - Async-first event-driven framework for Python applications.

## Repository
- Main branch: `main`
- Current working directory: `/Users/ade/Dev/KRules/krules-framework`

## ClickUp Configuration

### Space
- **Team Space** (space_id: 90157409183)
- URL: https://app.clickup.com/90151786764/v/s/90157409183

### Folder
- **KRules** (folder_id: 901510655880)
- URL: https://app.clickup.com/90151786764/v/f/901510655880

### Lists
- **TODOs** (list_id: 901516453755)
- URL: https://app.clickup.com/90151786764/v/li/901516453755
- Use this list for all KRules Framework tasks

## Branch Naming Convention
- Features: `feature/{task_id}-{short-description}`
- Bugs: `fix/{task_id}-{short-description}`
- Refactoring: `refactor/{task_id}-{short-description}`

## Project Structure
- `krules/` - Core framework code
- `docs/` - Documentation
- Tests: Skip by default unless explicitly requested

## Development Notes
- Python async-first framework
- Event-driven architecture
- Uses dependency-injector for IoC
- Pydantic-settings for configuration
- Redis storage backends supported
- PostgreSQL storage backend with JSONB support (recently added)
