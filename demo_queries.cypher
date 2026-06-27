// ============================================================================
// legalgraph — demo queries for the Online Safety Act regime (Neo4j Aura)
// Paste these into Neo4j Browser / the Aura "Query" tab one at a time.
// The graph view (not the table) is the wow factor — keep "Graph" tab selected.
// ============================================================================

// 1. THE OSA REGIME, all six layers in one picture (a star around the Act).
//    Acts, SIs, guidance, explanatory notes, debates, the bill, cases.
MATCH path = (a:Act {citation: 'Online Safety Act 2023'})
      -[:MADE_UNDER|ISSUED_UNDER|EXPLAINS|DEBATED_IN|BECAME|CONSIDERS]-(d:Document)
RETURN path LIMIT 120;

// 2. RELATED REGIMES — how Online Safety connects to Data Protection,
//    Communications, etc. via shared/adjacent subject concepts.


// 3. DRILL INTO STRUCTURE — the Act's internal tree (Part > section >
//    subsection). This is what powers per-section retrieval (PageIndex).
MATCH path = (a:Act {citation: 'Online Safety Act 2023'})-[:CONTAINS*1..2]->(:Provision)
RETURN path LIMIT 100;

// 4. CONCRETE ANSWERS (table tab):

// 4a. Statutory Instruments made under the Online Safety Act
MATCH (si:StatutoryInstrument)-[:MADE_UNDER]->(:Act {citation: 'Online Safety Act 2023'})
RETURN si.citation AS statutory_instrument ORDER BY statutory_instrument;

// 4b. Ofcom codes / statutory guidance issued under the Act
MATCH (g:Guidance)-[:ISSUED_UNDER]->(:Act {citation: 'Online Safety Act 2023'})
RETURN g.citation AS guidance, g.source_url AS url;

// 4c. Cases that genuinely cite the Data Protection Act 2018 (citation-verified)
MATCH (c:Case)-[:CONSIDERS]->(:Act {citation: 'Data Protection Act 2018'})
RETURN c.citation AS case, c.level AS court ORDER BY court;

// 4d. A specific section's text, by number (e.g. OSA s.1)
MATCH (:Act {citation: 'Online Safety Act 2023'})-[:CONTAINS*]->(p:Provision)
WHERE p.number = '1'
RETURN p.number AS section, p.heading AS heading, p.text AS text;

// 5. THE WHOLE PICTURE — every document touching the Act, by layer.
MATCH (a:Act {citation: 'Online Safety Act 2023'})-[r]-(d:Document)
RETURN [l IN labels(d) WHERE l <> 'Document'][0] AS layer,
       type(r) AS via, count(*) AS n
ORDER BY n DESC;

// 6. SCALE / shape of the whole graph
MATCH (n) RETURN labels(n)[-1] AS label, count(*) AS n ORDER BY n DESC;
