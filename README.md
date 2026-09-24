# SMath Studio (Python)

A Python reverse-engineering of SMath Studio with a Tkinter-based GUI.

## Requirements

- Python 3.10+
- tkinter (usually included with Python; on Ubuntu/Debian: `sudo apt install python3-tk`)
- numpy

## Installation

```bash
pip install numpy
```

Or install the package:

```bash
pip install .
```

## Running

### GUI (worksheet editor)

```bash
python -m smath_studio.gui
```

To open a `.sm` file:

```bash
python -m smath_studio.gui path/to/file.sm
```

### CLI (evaluate worksheets)

```bash
python -m smath_studio evaluate path/to/file.sm
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `'` (apostrophe) | Start a new math equation region |
| `"` (double quote) | Start a new text region |
| `Enter` | Commit current edit |
| `Escape` | Cancel current edit |
| `Tab` | Cycle through regions / autocomplete |
| `F5` | Evaluate selected region |
| `F9` | Recalculate all |
| `Ctrl+Z` | Undo |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save As |
| `Ctrl+O` | Open file |
| `Ctrl+N` | New worksheet |

### Math Editor Keys

| Key | Action |
|-----|--------|
| `/` | Create fraction |
| `^` | Create superscript |
| `\` | Square root |
| `'` | Insert unit |
| `_` | Subscript (dot notation) |
| `Space` | Convert to text region (blocked after `=`) |
| `Ctrl+M` | Insert matrix |
| `Ctrl+G` | Convert to Greek letter |

### Typing Behavior

- Typing `=` after an **undefined** variable auto-converts to `:=` (definition)
- Typing `=` after a **defined** variable keeps `=` (evaluation, shows result)
- Typing space in a math region converts it to a text region
- Typing space after `=` or `:=` is blocked
