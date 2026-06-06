"""Graph RAG — entity extraction + relationship mapping + graph traversal retrieval.

Inspired by Microsoft GraphRAG / LazyGraphRAG. NOTE: the headline figures from those
papers ("~0.1% cost", "+26% comprehensiveness / +57% diversity") describe the
*Microsoft* systems, not this module — this is a lightweight regex + co-occurrence
entity/relation extractor, not a benchmarked reproduction of those results.
"""
from __future__ import annotations
import re
from typing import Any
from largestack._memory.graph import GraphMemory

class GraphRAG:
    """Graph-based retrieval: extract entities → build graph → traverse for answers.

    LazyGraphRAG-style: build the graph lazily at query time, not at indexing.
    (Lightweight regex/co-occurrence extraction; the paper benchmark numbers above
    are not claims about this implementation.)
    """
    def __init__(self):
        self.graph = GraphMemory()
        self._documents: list[str] = []
    
    async def ingest(self, documents: list[str]):
        """Extract entities and relationships from documents."""
        self._documents.extend(documents)
        for doc in documents:
            entities = self._extract_entities(doc)
            for entity in entities:
                await self.graph.add_entity(entity["name"], entity.get("type", ""))
            
            relations = self._extract_relations(doc, entities)
            for rel in relations:
                await self.graph.add_relation(rel["from"], rel["to"], rel["relation"])
    
    async def query(self, question: str, depth: int = 2) -> str:
        """Query the graph for relevant information."""
        # Extract key entities from question
        q_entities = self._extract_entities(question)
        
        results = []
        for entity in q_entities:
            traversal = await self.graph.query(entity["name"], depth=depth)
            if traversal["connected"]:
                connections = [f"{c['entity']} ({c['relation']})" for c in traversal["connected"]]
                results.append(f"{entity['name']}: connected to {', '.join(connections)}")
        
        if not results:
            return "No graph connections found for the query entities."
        return "\n".join(results)
    
    def _extract_entities(self, text: str) -> list[dict]:
        """Simple entity extraction via capitalized words and NP patterns."""
        entities = []
        # Capitalized multi-word phrases
        for match in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', text):
            name = match.group(1)
            if len(name) > 2 and name not in ("The", "This", "That", "These"):
                entities.append({"name": name, "type": "entity"})
        return entities[:20]
    
    def _extract_relations(self, text: str, entities: list[dict]) -> list[dict]:
        """Extract relationships between entities."""
        relations = []
        entity_names = [e["name"] for e in entities]
        for i, e1 in enumerate(entity_names):
            for e2 in entity_names[i+1:]:
                # Check if both entities appear near each other in text
                p1 = text.find(e1); p2 = text.find(e2)
                if p1 >= 0 and p2 >= 0 and abs(p1 - p2) < 200:
                    between = text[min(p1, p2):max(p1, p2) + len(max(e1, e2, key=len))]
                    rel = "related_to"
                    if "is a" in between.lower(): rel = "is_a"
                    elif "uses" in between.lower(): rel = "uses"
                    elif "part of" in between.lower(): rel = "part_of"
                    relations.append({"from": e1, "to": e2, "relation": rel})
        return relations[:30]
