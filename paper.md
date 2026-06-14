---
title: 'shebanq-mcp: plain-language, citable queries over the BHSA Hebrew Bible'
tags:
  - Hebrew Bible
  - Biblical Hebrew
  - BHSA
  - ETCBC
  - SHEBANQ
  - Emdros
  - MQL
  - Model Context Protocol
  - digital humanities
  - corpus linguistics
authors:
  - name: Jose Fresco Benaim
    orcid: 0009-0000-2026-0836
    affiliation: 1
affiliations:
  - name: Independent researcher
    index: 1
date: 14 June 2026
bibliography: paper.bib
---

# Summary

`shebanq-mcp` is a Model Context Protocol (MCP) server that lets students
and scholars of the Hebrew Bible query the BHSA, the ETCBC linguistic
database behind SHEBANQ [@shebanq; @bhsa], by asking in plain language.
A question such as "Niphal verbs in Genesis" is translated into a query in
MQL, the query language of the Emdros text database engine [@emdros],
validated against the BHSA feature catalogue, and run on a local Emdros
engine. The server returns two things together: the exact MQL that ran and
the real result rows it produced. The query is never hidden. Every answer
carries the query that made it, queries are checked before they run, and an
empty result is reported as empty rather than dressed up. The tool is meant
to lower the barrier to MQL for teaching and research while keeping the
scholarly act of reading and judging a query in the user's hands: AI as a
way in, not a way around.

# Statement of need

The BHSA encodes the Hebrew Bible word by word with a deep stack of
linguistic features: part of speech, verbal stem and tense, person, gender,
number, phrase and clause function, lexeme, and more [@bhsa]. It is one of
the richest openly licensed datasets in biblical studies. Two established
paths reach it. SHEBANQ [@shebanq] offers a web interface where saved MQL
queries can be browsed and run, and Text-Fabric [@textfabric] exposes the
same corpus to Python notebooks. Both reward fluency in a query language.
MQL in particular has a precise but unforgiving syntax, and a small mistake
(quoting a value that must be unquoted, or the reverse) fails with a
type-checking error rather than a wrong answer. For a scholar who knows
exactly which construction they want but not how to phrase it in MQL, the
language itself is the obstacle.

A general-purpose chatbot can write Hebrew-Bible queries, but it will also
invent counts, miscite verses, and hide the query that produced a number.
That is the wrong trade for scholarship, where a result is only as good as
the query behind it. `shebanq-mcp` takes the opposite stance. It uses a
language model only to draft the query, then validates that query against
the real feature catalogue, runs it on a real engine, and shows it. The
model drafts the query; the scholar reads it, checks it, edits it, and cites
it. This makes the tool usable both as a research aid and as a teaching
instrument for MQL itself.

# Design and functionality

The server exposes a small set of MCP tools, the central one being
`search_bhsa` (natural language to validated MQL plus results), alongside
`run_mql` (run a hand-written query) and `lookup_feature` (inspect the
feature catalogue). It runs read-only: a guard rejects any MQL that is not
a query.

The pipeline is deliberately thin. A single model call turns the question
into MQL. Everything after that is deterministic. A validator that knows
the BHSA enumeration rules checks the query before it runs; in MQL,
enumeration features such as part of speech or verbal stem compare unquoted
(`sp=verb`, `vs=nif`) while string features such as lexeme compare quoted
(`lex='BR>['`), and getting this wrong is the most common failure. Validated
queries run on Emdros over a SQLite build of the BHSA, and the results are
glossed for readability.

Each answer also shows the query in a second language. From the validated
MQL, deterministic code derives the equivalent Text-Fabric search template,
with no second model call, so a user working in notebooks can carry the same
query across tools or cite it as a SHEBANQ saved query. A cross-engine test
suite runs in continuous integration: it executes the MQL on Emdros and the
derived template on Text-Fabric and asserts that the two return identical
result rows over the whole corpus. This equivalence check is what lets the
two-language display be trusted rather than merely plausible. It also
forced a precise reading of how the two engines treat sibling blocks. MQL
has two ways to place one block after another. Bare juxtaposition means
adjacent within the parent's monads, with gaps in the clause skipped, and on
one test query it matches 25827 rows; no Text-Fabric operator expresses this
(the nearest, `<<`, gives 40371 and `<:` gives 25698). The ordered form
`[A] .. [B]`, meaning B anywhere after A, is identical to Text-Fabric `<<`,
proven row for row at 40371. So the converter translates `..` to `<<`
faithfully and refuses bare juxtaposition with a message that teaches the
difference, rather than emitting a template that would return a different
set of verses.

`shebanq-mcp` works from any MCP client and from a hosted web demo, where
results run on Emdros and the Text-Fabric template is shown beside them as
the derived, citable equivalent.

# Acknowledgements

`shebanq-mcp` wraps existing scholarly infrastructure and does not replace
it. The BHSA is the work of the Eep Talstra Centre for Bible and Computer
(ETCBC) at VU Amsterdam and is used under the CC BY-NC 4.0 license [@bhsa].
The query engine is Emdros, by Ulrik Sandborg-Petersen [@emdros]. SHEBANQ
[@shebanq] and Text-Fabric [@textfabric], both from the ETCBC and Dirk
Roorda, are the established interfaces to this corpus that the tool builds
on. The Model Context Protocol provides the client interface [@mcp].

The software and this paper were developed with substantial assistance from
large language models under the author's direction and review. Generated
queries, code, and prose were checked against the live engine and the
project's test suite before inclusion.

# References
