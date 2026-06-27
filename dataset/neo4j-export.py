import os
import csv
import json
from neo4j import GraphDatabase

# 1. Credentials directly extracted from your chat log
AURA_URI = "neo4j+s://0893f8bb.databases.neo4j.io"
AURA_USER = "0893f8bb"
AURA_PASSWORD = "xTjnd6QKJC8MANIl-UaI0IABVjX0G5Bk1A-ANxiueEs"

# 2. Comprehensive Cypher Query to prevent structural loss
# Matches source nodes, targeted paths, and downstream target node maps
extraction_query = """
MATCH (source)-[r]->(target)
RETURN 
    labels(source) AS source_labels,
    properties(source) AS source_props,
    type(r) AS rel_type,
    properties(r) AS rel_props,
    labels(target) AS target_labels,
    properties(target) AS target_props
"""

def extract_semantic_graph():
    print(f"Connecting to Aura DB Instance: {AURA_URI}...")
    
    # Establish connection via driver routing table
    driver = GraphDatabase.driver(AURA_URI, auth=(AURA_USER, AURA_PASSWORD))
    
    output_file = "aura_semantic_extract.csv"
    
    try:
        with driver.session() as session:
            print("Executing global match query...")
            result = session.run(extraction_query)
            
            with open(output_file, mode="w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                
                # Dynamic header preserving both ontology structure and semantic values
                writer.writerow([
                    "Source_Labels", "Source_Properties_JSON", 
                    "Relationship_Type", "Relationship_Properties_JSON", 
                    "Target_Labels", "Target_Properties_JSON"
                ])
                
                row_count = 0
                for record in result:
                    writer.writerow([
                        ",".join(record["source_labels"]),
                        json.dumps(record["source_props"], ensure_ascii=False),
                        record["rel_type"],
                        json.dumps(record["rel_props"], ensure_ascii=False),
                        ",".join(record["target_labels"]),
                        json.dumps(record["target_props"], ensure_ascii=False)
                    ])
                    row_count += 1
                    
                print(f"Successfully downloaded {row_count} semantic relationships into '{output_file}'.")
                
    except Exception as e:
        print(f"An extraction error occurred: {str(e)}")
    finally:
        driver.close()

if __name__ == "__main__":
    extract_semantic_graph()