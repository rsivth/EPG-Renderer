# Sources and provenance

Bundled kit definitions are manual transcriptions of manufacturer documentation unless a JSON profile states otherwise. The source title and its specific use are also recorded inside each profile.

## Thermo Fisher Scientific / Applied Biosystems

- *GlobalFiler and GlobalFiler IQC PCR Amplification Kits User Guide*, MAN0029969 Rev. A (2025): GlobalFiler markers, ladder alleles, dyes and assay notes.
- *PCR amplification kits for forensic DNA profiling*, COL012579 0720: approximate GlobalFiler marker ranges.
- *AmpFlSTR NGM PCR Amplification Kit User Guide*, 4466844 Rev. A (2011): NGM markers, dyes, ladder alleles and ranges.
- *AmpFlSTR NGM SElect PCR Amplification Kit User Guide*, PN 4458841, plus Thermo Fisher product information: NGM SElect marker set, PET-channel SE33 placement and ladder organization.
- *AmpFLSTR NGM Detect PCR Amplification Kit User Guide*, 100044085: NGM Detect markers, controls and ladder data.
- *AmpFlSTR Identifiler PCR Amplification Kit User Guide*: Identifiler definition.
- *AmpFlSTR Yfiler Direct PCR Amplification Kit User Guide*, 4479446B: Yfiler Direct definition.
- *Yfiler Plus PCR Amplification Kit User Guide*, MAN0030230: Yfiler Plus definition.
- GeneMapper ID-X analysis-file downloads: acknowledged as the authoritative route for future verified bin-centre imports.

## Promega

- *PowerPlex ESI 17 Fast System Technical Manual*.
- *PowerPlex ESX 17 Fast System Technical Manual*.
- *PowerPlex Y23 System Technical Manual*.
- *PowerPlex Fusion System Technical Manual*.
- *PowerPlex 35GY System for Use on the Spectrum CE System Technical Manual*.

## QIAGEN

- *Investigator Argus X-12 QS Handbook*.
- *Investigator ESSplex SE QS Handbook*.

## Scientific limitation

Bundled x-coordinates are nominal display coordinates unless the profile explicitly declares verified exact bin centres. They are not measured sample fragment sizes or official GeneMapper bin sets. PowerPlex 35GY is not declared GeneMapper-export compatible.

## GeneMapper table export behavior

- *GeneMapper ID Software Version 3.1 Human Identification Analysis User Guide*, PN 4338775C: configurable Samples/Genotypes table export, table-setting-dependent columns and variable allele display width.
- *GeneMapper Software Version 3.0 User Guide*, PN 4356655: indexed allele, size, height, area, mutation and comment fields.
- *GeneMapper ID-X Software Version 1.5 Basic Features Getting Started Guide*: combined table export follows currently displayed columns.
- *GeneMapper ID-X Software Version 1.6 New Features and Software Verification User Bulletin*: export-with-stutter behavior and sequential exported peaks.

The parser therefore preserves configurable source fields and does not assume that every `Allele n` entry necessarily represents a two-allele genotype.

## RFU validity boundary

- Thermo Fisher's [BigDye Terminator FAQ](https://www.thermofisher.com/order/catalog/product/4337454/faqs) documents 32,000 RFU as the maximum raw-data signal threshold for the Applied Biosystems 3500/3500xL. Signals above that threshold are off-scale detector saturation.
- Thermo Fisher's [fragment-analysis troubleshooting guidance](https://www.thermofisher.com/blog/learning-at-the-bench/fragment-analysis-ce-gsd-ts-ce-25042/) likewise identifies 32,000 RFU as the 3500-series detection limit and warns that off-scale peaks can produce incorrect spectral correction and pull-up.
- Promega's [VersaPlex Matrix Standards protocol for the Spectrum Compact CE System](https://worldwide.promega.com/-/media/files/resources/protocols/technical-manuals/tmd/versaplex-matrix-standards-for-spectrum-compact-ce-system-protocol-tmd072.pdf) specifies a maximum raw spectral-calibration signal of 32,767 RFU and warns that saturated peaks can cause bleed-through or oversubtraction.

EPG-Renderer therefore rejects peak heights above 32,767 RFU across its supported input domain. This is a structural plausibility ceiling, not an analytical threshold: data known to originate from a 3500/3500xL may already be off-scale above 32,000 RFU and require upstream review. The Promega figure is documented for spectral-calibration raw data rather than as a universal sample-analysis threshold; it supports the common digital ceiling without replacing method-specific quality control.

## Test data provenance

Every bundled test fixture is synthetic. The GeneMapper table exports under
`tests/fixtures/genemapper_exports/` and the `.tsv` fixtures beside them contain no
laboratory data: sample names, sample files, sample identifiers, run names and peak
heights are invented, and allele values are drawn from the allelic-ladder lists of the
bundled kit definitions. The exception is `ngm_showcase.tsv`: it deliberately adds
off-ladder calls (`OL`, with and without a size) and an allele outside the ladder, to
show in [Reading the figure](READING_THE_FIGURE.md) how such calls are drawn.

They are deliberately shaped like real configurable exports rather than like minimal
examples, because the parser contracts they protect concern exactly that shape: an
unnamed trailing export column, a marker call that fills the highest displayed allele
column and therefore raises the truncation warning, repeated display names that must
remain separate source injections, and complete marker coverage in kit-panel order for
unambiguous kit resolution.
