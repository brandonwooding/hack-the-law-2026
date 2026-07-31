# Data sources

The official endpoints each adapter in [`src/legalgraph/adapters/`](../src/legalgraph/adapters/)
fetches from. All are public; none require a key.

## United Kingdom

| Source | Endpoint |
| --- | --- |
| legislation.gov.uk (Acts, SIs, CLML) | https://legislation.github.io/data-documentation/api/overview.html |
| Statutory Instruments API | https://statutoryinstruments-api.parliament.uk/index.html |
| Bills API | https://bills-api.parliament.uk/index.html |
| Hansard (parliamentary debates) | https://api.parliament.uk/historic-hansard/api |
| Find Case Law (National Archives) | https://nationalarchives.github.io/ds-find-caselaw-docs/public |
| GOV.UK content API (guidance) | https://content-api.publishing.service.gov.uk/ |

## European Union

| Source | Endpoint |
| --- | --- |
| CELLAR / Publications Office SPARQL | https://publications.europa.eu/webapi/rdf/sparql |
| EUR-Lex web services / data reuse | https://eur-lex.europa.eu/content/help/data-reuse/webservice.html |
| English XHTML manifestation by CELEX | `https://publications.europa.eu/resource/celex/{CELEX}.ENG.xhtml` |

CELLAR provides the stable metadata and the authority-graph links; the XHTML
manifestation provides the document anatomy. The two are joined on CELEX number.
