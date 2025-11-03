# Shell Mode (Interactive Usage)

Shell mode provides attribute-style syntax for convenient interactive use in REPL/IPython environments. **This mode is NOT recommended for production code.**

## Overview

Shell mode allows:
- `subject.property` instead of `subject.get("property")`
- `subject.property = value` instead of `subject.set("property", value)`
- `del subject.property` instead of `subject.delete("property")`

**Use case:** Interactive debugging, REPL exploration, quick prototyping.

**Not for:** Production code, libraries, applications.

## Attribute Access

### Get Property

```python
from krules_core.container import KRulesContainer

container = KRulesContainer()
user = container.subject("user-123")

# Standard API (always use in production)
user.set("email", "john@example.com")
email = user.get("email")

# Shell mode (interactive only)
user.email = "john@example.com"
email = user.email  # Returns SubjectPropertyProxy
```

### Set Property

```python
# Standard API
user.set("name", "John Doe")

# Shell mode
user.name = "John Doe"
```

### Delete Property

```python
# Standard API
user.delete("email")

# Shell mode
del user.email
```

## Special Prefixes

### Muted Properties (`m_*`)

Set properties without emitting events:

```python
# Standard API
user.set("counter", 0, muted=True)

# Shell mode
user.m_counter = 0  # No event emitted
```

### Extended Properties (`ext_*`)

Access extended properties:

```python
# Standard API
user.set_ext("last_ip", "192.168.1.1")
ip = user.get_ext("last_ip")

# Shell mode
user.ext_last_ip = "192.168.1.1"
ip = user.ext_last_ip
```

## SubjectPropertyProxy

When accessing properties via attribute syntax, values are wrapped in `SubjectPropertyProxy`:

### Counter Operations

```python
user.counter = 10

# Increment
user.counter.incr()      # +1 (default)
user.counter.incr(5)     # +5

# Decrement
user.counter.decr()      # -1 (default)
user.counter.decr(3)     # -3

# Get actual value
value = int(user.counter)  # or str(), etc.
```

### Proxy Behavior

```python
# Proxy wraps the value
proxy = user.name  # SubjectPropertyProxy wrapping "John"

# Use like normal value
print(proxy)           # "John"
print(len(proxy))      # 4
print(proxy.upper())   # "JOHN"

# Get wrapped value
actual_value = str(proxy)
```

## Limitations

Shell mode has significant limitations:

### 1. Property Names with Special Characters

```python
# ❌ Doesn't work (invalid Python identifier)
user.email-address = "john@example.com"  # Syntax error

# ✅ Use standard API
user.set("email-address", "john@example.com")
```

### 2. Python Keywords

```python
# ❌ Doesn't work (Python keyword)
user.class = "premium"  # Syntax error

# ✅ Use standard API
user.set("class", "premium")
```

### 3. Dynamic Property Names

```python
prop_name = "dynamic_property"

# ❌ Doesn't work
user.prop_name = "value"  # Sets literal "prop_name", not "dynamic_property"

# ✅ Use standard API
user.set(prop_name, "value")
```

### 4. No Lambda Values

```python
# ❌ Doesn't work
user.counter = lambda c: c + 1  # Sets lambda object, not computed value

# ✅ Use standard API
user.set("counter", lambda c: c + 1)
```

### 5. Type Checking

```python
# ❌ Type checkers complain
email: str = user.email  # Type: SubjectPropertyProxy, not str

# ✅ Use standard API for type safety
email: str = user.get("email")
```

### 6. IDE Autocomplete

```python
# ❌ No autocomplete for property names
user.email  # IDE doesn't know "email" exists

# ✅ Standard API allows for explicit property management
user.get("email")
```

## When to Use Shell Mode

### ✅ Good Use Cases

**Interactive Debugging:**
```python
# In IPython/REPL
>>> user = container.subject("user-123")
>>> user.email
'john@example.com'
>>> user.counter.incr()
>>> user.counter
11
```

**Quick Exploration:**
```python
# Check subject state quickly
>>> user.status
'active'
>>> user.login_count
42
```

**Prototyping:**
```python
# Rapid prototyping in Jupyter notebook
device = container.subject("device-001")
device.temperature = 75.5
device.status = "online"
```

### ❌ Bad Use Cases

**Production Code:**
```python
# ❌ Don't do this in application code
@on("user.login")
async def handle_login(ctx):
    ctx.subject.last_login = datetime.now()  # Bad!

# ✅ Use standard API
@on("user.login")
async def handle_login(ctx):
    ctx.subject.set("last_login", datetime.now())
```

**Libraries:**
```python
# ❌ Don't use in library code
def process_user(user):
    user.status = "processed"  # Bad!

# ✅ Use standard API
def process_user(user):
    user.set("status", "processed")
```

**Loops:**
```python
# ❌ Shell mode in loops
for i in range(100):
    user.f"field_{i}" = i  # Doesn't work!

# ✅ Standard API
for i in range(100):
    user.set(f"field_{i}", i)
```

## Mixing Modes

You can mix shell mode and standard API, but be consistent:

```python
# Mixed (works but confusing)
user.name = "John"           # Shell mode
email = user.get("email")    # Standard API

# Better: Pick one style
# Standard API everywhere (recommended)
user.set("name", "John")
email = user.get("email")
```

## Examples

### REPL Session

```python
$ python
>>> from krules_core.container import KRulesContainer
>>> container = KRulesContainer()
>>> user = container.subject("user-123")

# Quick property inspection
>>> user.email = "john@example.com"
>>> user.email
'john@example.com'

# Counter operations
>>> user.login_count = 0
>>> user.login_count.incr()
>>> user.login_count
1

# Muted properties (no events)
>>> user.m_internal_flag = True

# Extended properties
>>> user.ext_metadata = {"source": "cli"}

# Check existence
>>> "email" in user
True

# Iterate
>>> for prop in user:
...     print(f"{prop}: {user.get(prop)}")
email: john@example.com
login_count: 1
```

### IPython/Jupyter

```python
In [1]: from krules_core.container import KRulesContainer
In [2]: container = KRulesContainer()
In [3]: device = container.subject("device-001")

In [4]: device.temperature = 75.5
In [5]: device.status = "online"

In [6]: device.temperature
Out[6]: 75.5

In [7]: device.temperature = 80.2
In [8]: device.temperature
Out[8]: 80.2
```

## Best Practices

1. **Production code** - Always use standard API (`.set()`, `.get()`, `.delete()`)
2. **Interactive only** - Shell mode for REPL/debugging only
3. **Be aware of limitations** - Know when shell mode won't work
4. **Document usage** - If using shell mode in scripts, document it clearly
5. **Consistency** - Don't mix modes in same codebase section
6. **Type safety** - Use standard API for type-checked code
7. **Dynamic names** - Use standard API when property names are dynamic

## Migration from Shell Mode

If you've used shell mode in code, migrate to standard API:

```python
# Before (shell mode)
user.email = "john@example.com"
email = user.email
del user.temp_token

# After (standard API)
user.set("email", "john@example.com")
email = user.get("email")
user.delete("temp_token")
```

## Summary

Shell mode provides convenient syntax for interactive use but has significant limitations. Use it for debugging and exploration, but always use the standard API in production code.

**Rule of thumb:** If it's in a `.py` file (not a notebook/REPL session), use standard API.

## What's Next?

- [Subjects](SUBJECTS.md) - Standard subject API
- [API Reference](API_REFERENCE.md) - Complete API documentation
