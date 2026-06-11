# MQL Primer for BHSA Queries

This primer covers the MQL constructs you will use to query the BHSA Hebrew Bible
via Emdros. Everything here has been verified against the real database.

---

## 1. The object hierarchy

The BHSA database organises text as a strict containment hierarchy. Every object
spans a range of monads (word-position integers), and smaller objects are always
embedded inside larger ones. The chain is:

**book > chapter > verse > sentence > clause > phrase > word**

Secondary types `clause_atom`, `phrase_atom`, and `subphrase` exist between those
levels. The `lex` type holds lexeme nodes (one per dictionary entry). You can skip
levels freely: `[clause [word ...]]` is legal and means "a word anywhere inside the
clause." The word need not be an immediate child.

---

## 2. Query skeleton

Every MQL query has the form:

```
SELECT ALL OBJECTS WHERE
  [<object_type> <feature_constraints> [<inner_blocks>]]
GO
```

The minimal version of a block is just brackets around an object type: `[word]`.
You add feature constraints before the inner blocks, and a `GET` clause to
specify which features to return:

```
SELECT ALL OBJECTS WHERE
  [word sp=verb AND vs=nif
     GET g_word_utf8, gloss
  ]
GO
```

`GO` terminates the statement.

---

## 3. Nesting

When block B appears inside block A (`[A [B]]`), every monad of the matched B
object must lie within the monad span of the matched A object. Query structure
mirrors database containment. This is how you express "a phrase inside a clause"
or "a word inside a phrase."

Each block in a nested query carries its own optional `GET`:

```
SELECT ALL OBJECTS WHERE
  [clause typ=Ellp GET typ
    [phrase function=Objc GET function
      [word sp=subs GET lex, gloss]]]
GO
```

Features are attached to matched objects at each level in the result. Only ask for
features that belong to that object type -- requesting `lex` on a `clause` block
is an error.

---

## 4. Sequence and adjacency -- the most important section

This is where most translation errors originate. Read it carefully.

### Bare juxtaposition means STRICTLY ADJACENT

Two blocks written next to each other with nothing between them:

```
[clause [phrase function=Conj][phrase function=Objc]]
```

require the second matched phrase to begin at the monad immediately after the
first ends. No intervening phrases are allowed. This returns **4490** clauses in
BHSA.

That is a narrow constraint. BHSA clauses often have phrases between the
conjunction and the object. Bare juxtaposition silently under-counts whenever
gaps exist in natural data.

### To allow space: the `..` operator

Put `..` between blocks to mean "B comes after A, in order, with arbitrary
material allowed between them inside the surrounding object":

```
[clause [phrase function=Conj] .. [phrase function=Objc]]
```

This returns **26240** clauses -- nearly six times as many. The phrases are still
ordered (conjunction before object), but gaps are permitted.

Default rule: when the natural-language question does not say "immediately followed
by," use `..`.

### Anchoring to boundaries: `first` and `last`

`first` written after the object type inside a block pins that block's matched
object to the start of its parent:

```
SELECT ALL OBJECTS WHERE [clause [phrase first function=Conj]] GO
```

The conjunction phrase must begin at the clause's first monad -- exactly "the
clause starts with this phrase." `last` pins to the end.

`first and last` together mean the inner object spans the parent completely.

---

## 5. FOCUS

By default, `SELECT ALL OBJECTS` returns every matched object at every nesting
level. When you want only the inner objects (using the outer structure as a
constraint), use `SELECT FOCUS OBJECTS` with the `focus` keyword on the block
you care about:

```
SELECT FOCUS OBJECTS WHERE
  [clause typ=Ellp [phrase focus function=Objc]]
GO
```

This returns the object phrases (1283 of them), not the containing clauses. Use
FOCUS when the structural context is a condition and the inner object is the
actual result.

---

## 6. Feature expressions

Boolean operators inside a block: `AND`, `OR`, `NOT`. Standard precedence: NOT
binds tightest, then AND, then OR. Use parentheses to override:

```
[word sp=verb AND (vs=nif OR vs=piel)]
```

Set membership with `IN`:

```
[phrase function IN (Objc, PreO, PtcO)]
```

Comparison operators: `=`, `<>` (not-equal), `<`, `>`, `<=`, `>=`.

---

## 7. The quoting rule

**Enumeration features compare UNQUOTED. String features compare QUOTED.**

Enumeration features: `sp`, `vs`, `vt`, `gn`, `nu`, `ps`, `function`, `typ`,
`rela`, `kind`, `book`, and many others. Compare them without quotes:

```
sp=verb    vs=nif    typ=Ellp    function=Objc
```

String features: `lex`, `gloss`, `g_word_utf8`, `voc_lex_utf8`. Compare them with
single quotes:

```
lex='BR>['
```

Quoting an enumeration feature throws "Typechecking failed" and the query will
not run. Note that BHSA verb lexemes carry a trailing `[` in transliteration
(bara = `BR>[`).

---

## 8. Verse references

To attach book, chapter, and verse numbers to each hit, wrap the query in a
`verse` block that GETs those features:

```
SELECT ALL OBJECTS WHERE
  [verse GET book, chapter, verse
    [word lex='BR>[' GET g_word_utf8, gloss]]
GO
```

The formatter reads the verse features from the outer sheaf and the word features
from the inner sheaf to produce cited results.

---

## 9. Worked examples

Each example below is a pinned query whose count was verified on the real BHSA
engine.

### Word search -- Niphal verbs (4145 hits)

```
SELECT ALL OBJECTS WHERE
[word sp=verb AND vs=nif
   GET g_word_utf8, gloss
]
GO
```

### Where-question -- occurrences of bara (48 hits)

```
SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse [word lex='BR>[' GET g_word_utf8, gloss]] GO
```

### Phrase function -- object phrases (22668 hits)

```
SELECT ALL OBJECTS WHERE
[phrase function=Objc
   GET function
]
GO
```

### Clause structure -- nominal clauses with a subject (7601 hits)

```
SELECT ALL OBJECTS WHERE [clause typ=NmCl [phrase function=Subj]] GO
```

### Adjacency contrast

Strictly adjacent conjunction + object phrase (bare juxtaposition, 4490 hits):

```
SELECT ALL OBJECTS WHERE [clause [phrase function=Conj][phrase function=Objc]] GO
```

Ordered but gaps allowed (`..`, 26240 hits):

```
SELECT ALL OBJECTS WHERE [clause [phrase function=Conj] .. [phrase function=Objc]] GO
```

The difference -- 4490 vs 26240 -- shows how much data bare juxtaposition
silently drops. Use `..` unless strict adjacency is what you mean.

### Clause structure -- ellipsis clauses starting with a conjunction and an object (1640 hits)

The motivating example. The `first` keyword anchors the conjunction phrase to the
clause's start monad. The `..` between the two phrase blocks lets the object
phrase follow anywhere inside the clause. Without `first`, any conjunction phrase
in the clause would match, not just the first one. Without `..`, the object phrase
would need to be immediately adjacent to the conjunction phrase, silently dropping
most matches.

```
SELECT ALL OBJECTS WHERE
[clause typ=Ellp
   [phrase first function=Conj]
   ..
   [phrase function=Objc]
]
GO
```

### Wayyiqtol clauses with a subject phrase (5874 hits)

```
SELECT ALL OBJECTS WHERE
[clause typ=WayX
   [phrase function=Subj
      GET function
   ]
]
GO
```
