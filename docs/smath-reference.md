# What SMath does, read from the copy in this repository

The task list says to use the supplied `SMath Studio/` installation as the
behaviour reference for equation-editor questions, by observing the
application rather than copying its implementation. This is that audit written
down, so the next session does not have to derive it again.

Nothing here is taken from SMath's code. The `.dll` files were not
disassembled and are not read by anything in CalcForge. What follows comes
from its **saved worksheets** and its **unit catalogue**, which are XML.

## How SMath stores an expression

Every math region in a `.sm` worksheet is a flat postfix list of typed nodes
under `<input>`. Across the 20 worksheets shipped in `examples/` and
`snippets/` there are 1987 operands, 937 operators, 246 functions and 40
brackets, and only those four kinds:

```xml
<e type="operand">x</e>
<e type="operand">2</e>
<e type="operator" args="2">+</e>
```

Three things follow from that, and all three matter here.

**It is a tree, not text.** SMath never stores the characters somebody typed;
it stores the structure and draws it. That is the model `docs/tasklist.md` §4
asks CalcForge to move to, and it is why an expression that does not parse
should still be drawn as structure rather than dropping back to its
characters.

**A bracket is a node.** Brackets are stored, not inferred at drawing time.
Wrapping a selected expression in brackets is therefore a change to the
structure in SMath too, which is what CalcForge's bracket-over-a-selection
does.

**Arity is carried, so unary and binary are different operators.** `-` appears
70 times with `args="1"` and 68 times with `args="2"`. A minus sign in front
of something is not the same node as a minus between two things.

The operators the shipped worksheets use, with their arity:

| Operator | Args | Uses | Meaning |
|---|---|---|---|
| `:` | 2 | 263 | define — CalcForge's `:=` |
| `*` `+` `/` | 2 | 419 | arithmetic |
| `-` | 1 and 2 | 138 | negate, and subtract |
| `^` | 2 | 65 | power |
| `≤` `≥` `<` `>` `≠` | 2 | 36 | comparisons |
| `≡` | 2 | 9 | boolean equality, separate from define |
| `!` | 1 | 3 | factorial |
| `&` `\|` | 2 | 4 | boolean and, or |

`≡` is worth noting: SMath separates *defining* a name from *asserting* an
equality. CalcForge folds both onto `=`, which defines the first time a name
appears and checks afterwards. That is a deliberate difference, not a gap.

## Units

`entries/Units.xml` holds 48 prefixes and 127 units. Checking every one of
them against this application's registry found 14 it did not understand. Of
those, `Smoot` is a joke, `atom` is chemistry, and `Angstrom` is a casing the
completion list already corrects. Five were units an engineer reaches for and
are now defined in `calcforge/core/units.py`:

`ksf`, `tonf`, `lbm`, `rev`, `rph`.

The remainder — `Fd`, `lbmol`, `ppb`, `radpm`, `sb`, and the binary prefixes
`Gi`/`Ti`/`kibi`/`gibi` — are left out on purpose: none of them belongs on a
structural calculation sheet, and every name added to the registry is a name
that can no longer be used as a variable.

## What was not done

SMath itself was not run. It is a .NET desktop application and this is a Linux
container, so its live interaction — caret movement through the tree, what a
click on a fraction selects, how a slot is entered and left — could not be
observed. Those questions are still open, and this file should grow when
somebody can sit in front of it.
