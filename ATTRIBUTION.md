# Attribution and data license

The **shebanq-mcp** software is MIT licensed. See [LICENSE](LICENSE).

This project, and the published container image, bundle the **BHSA** (the ETCBC
database of the Hebrew Bible, data version 2021), produced by the **Eep Talstra
Centre for Bible and Computer (ETCBC)** at VU Amsterdam. The BHSA is the data
behind [SHEBANQ](https://shebanq.ancient-data.org/).

## BHSA data license

The BHSA data is licensed
[**Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**](https://creativecommons.org/licenses/by-nc/4.0/).

What that means for this software and the container image that bundles the data:

- **Attribution.** The BHSA is the work of the ETCBC. Please cite it:
  ETCBC, *BHSA: the Biblical Hebrew text database* (data version 2021),
  DOI [10.17026/dans-z6y-skyh](https://doi.org/10.17026/dans-z6y-skyh),
  <https://github.com/ETCBC/bhsa>.
- **Non-commercial.** The bundled BHSA data may not be used for commercial
  purposes. The container image is provided free, for scholarly and educational
  use only.

## What this project builds on

- **Emdros** (Ulrik Sandborg-Petersen), the MQL query engine:
  <https://github.com/emdros/emdros>
- **Text-Fabric** (Dirk Roorda / ETCBC), the corpus engine and notebook format:
  <https://github.com/annotation/text-fabric>
- **SHEBANQ**, the ETCBC's query website: <https://shebanq.ancient-data.org/>

shebanq-mcp wraps this work; it does not replace it.
