# Text-Fabric Search Template Primer for BHSA

A Text-Fabric search template describes a pattern of nested objects, one object
per line. Indentation expresses containment, the way brackets do in MQL.

## 1. The object hierarchy

book > chapter > verse > sentence > clause > phrase > word

Secondary types `clause_atom`, `phrase_atom`, and `subphrase` sit between
levels; `lex` holds lexeme nodes. You can skip levels freely: a `word` line
under a `clause` line means "a word anywhere inside the clause."

## 2. Template form

Each line is an object type followed by zero or more feature constraints:

    clause
      phrase function=Pred
        word sp=verb vs=nif

- The first line has no indentation.
- A line indented deeper than the previous line is contained in it.
- Sibling lines align at the same indentation.
- Use spaces, never tabs. Two spaces per level is the convention.

## 3. Feature constraints

Constraints are space-separated `feature=value` pairs on the object's line.
NOTHING is ever quoted: `sp=verb`, `vs=nif`, `lex=BR>[`, `gloss=create`.
This is the big difference from MQL: there is no enum-versus-string quoting
rule. Use only features and values from the reference below.

BHSA verb lexemes carry a trailing `[` (bara is `lex=BR>[`). Nouns may carry
a trailing `/` (e.g. `lex=DBR/`) and that character is part of the value.

## 4. Examples

All verbs:

    word sp=verb

Niphal verbs:

    word sp=verb vs=nif

Every occurrence of bara:

    word lex=BR>[

Feminine plural nouns:

    word sp=subs gn=f nu=pl

A predicate phrase with an imperative inside a clause:

    clause
      phrase function=Pred
        word vt=impv

## 5. Output rules

Output the template only: no prose, no code fences, no comments. The smallest
template that answers the question is the best one. Put the object the user is
asking about on the LAST line: results are reported from that line's matches.
