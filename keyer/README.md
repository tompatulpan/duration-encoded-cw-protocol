# Keyer Module

This module provides iambic keyer implementations by wrapping the `vail-adapter-lib` package.

## Why a Wrapper?

Instead of duplicating keyer code in this project, we use the well-tested implementations from `vail-adapter-lib`. This ensures:
- **Single source of truth**: Bug fixes and improvements happen in one place
- **No code duplication**: Eliminates ~150 lines × 8+ duplicate copies
- **Consistent behavior**: All senders use the same keyer logic

## Available Classes

### IambicKeyer (Async)
For async applications (e.g., TCI controller):
```python
from keyer import IambicKeyer

keyer = IambicKeyer(wpm=25, mode='B')
await keyer.key_paddle(dit_paddle=True, dah_paddle=False, callback=async_callback)
```

### IambicKeyerSync (Sync)
For synchronous applications (e.g., USB_HID senders):
```python
from keyer import IambicKeyerSync

keyer = IambicKeyerSync(wpm=25, mode='B')
keyer.update(dit_paddle=True, dah_paddle=False, send_element_callback=callback)
```

## Dependencies

Requires `vail-adapter-lib` to be present in the workspace at:
```
../../vail-adapter-lib/vail_adapter_lib/
```

Install vail-adapter-lib:
```bash
cd ../vail-adapter-lib
pip install -e .
```

## Migration Notes

**Old code pattern (duplicate IambicKeyer class in each file):**
```python
class IambicKeyer:
    # 150+ lines of keyer logic
    # ... duplicated in 8+ files
```

**New code pattern (import from shared module):**
```python
from keyer import IambicKeyerSync

keyer = IambicKeyerSync(wpm=25, mode='B')
```

This eliminates ~1,200 lines of duplicate code across the codebase.
