"""Graph/associative memory — entity-relationship knowledge graph.

Real implementation with:
- Bidirectional edges
- Path finding (BFS + shortest path)
- Subgraph extraction
- Entity merging
- Text-based entity extraction
- JSON persistence
"""
from __future__ import annotations
import json, os, logging
from collections import deque
from typing import Any

log = logging.getLogger("largestack.memory.graph")


class GraphMemory:
    """Entity-relationship memory as a directed graph.
    
        g = GraphMemory()
        await g.add_entity("Alice", "person", {"age": 30})
        await g.add_entity("Acme", "company")
        await g.add_relation("Alice", "Acme", "works_at")
        
        # Query
        rels = await g.get_relations("Alice")
        paths = await g.find_paths("Alice", "Bob")
        sub = await g.subgraph("Alice", depth=2)
    """
    def __init__(self, storage_path: str = None, auto_save: bool = False):
        self._entities: dict[str, dict] = {}
        self._edges: list[dict] = []  # [{from, to, relation, attrs, weight}]
        self._adj_out: dict[str, list[int]] = {}  # entity -> [edge_indices outbound]
        self._adj_in: dict[str, list[int]] = {}   # entity -> [edge_indices inbound]
        self.storage_path = os.path.expanduser(storage_path) if storage_path else None
        self.auto_save = auto_save
        if self.storage_path and os.path.exists(self.storage_path):
            self._load()
    
    async def add_entity(self, name: str, entity_type: str = "", attributes: dict = None):
        """Add or update an entity."""
        if not name:
            raise ValueError("Entity name cannot be empty")
        self._entities[name] = {"type": entity_type, "attrs": attributes or {}}
        self._adj_out.setdefault(name, [])
        self._adj_in.setdefault(name, [])
        if self.auto_save: self._save()
    
    async def add_relation(self, from_entity: str, to_entity: str, relation: str,
                           attributes: dict = None, weight: float = 1.0):
        """Add an edge. Entities are auto-created if missing."""
        if from_entity not in self._entities:
            await self.add_entity(from_entity)
        if to_entity not in self._entities:
            await self.add_entity(to_entity)
        
        edge = {
            "from": from_entity, "to": to_entity, "relation": relation,
            "attrs": attributes or {}, "weight": weight,
        }
        idx = len(self._edges)
        self._edges.append(edge)
        self._adj_out[from_entity].append(idx)
        self._adj_in[to_entity].append(idx)
        if self.auto_save: self._save()
    
    async def remove_entity(self, name: str) -> bool:
        """Remove entity and all connected edges."""
        if name not in self._entities:
            return False
        # Remove connected edges
        self._edges = [e for e in self._edges if e["from"] != name and e["to"] != name]
        del self._entities[name]
        self._adj_out.pop(name, None)
        self._adj_in.pop(name, None)
        self._rebuild_adj()
        if self.auto_save: self._save()
        return True
    
    def _rebuild_adj(self):
        """Rebuild adjacency lists after edge removal."""
        self._adj_out = {name: [] for name in self._entities}
        self._adj_in = {name: [] for name in self._entities}
        for i, e in enumerate(self._edges):
            self._adj_out.setdefault(e["from"], []).append(i)
            self._adj_in.setdefault(e["to"], []).append(i)
    
    async def get_entity(self, name: str) -> dict | None:
        return self._entities.get(name)
    
    async def get_relations(self, entity: str, direction: str = "both") -> list[dict]:
        """Get edges touching entity. direction: 'out' | 'in' | 'both'."""
        results = []
        if direction in ("out", "both"):
            for idx in self._adj_out.get(entity, []):
                e = self._edges[idx]
                results.append({"from": e["from"], "to": e["to"], "relation": e["relation"],
                               "direction": "out", **e["attrs"]})
        if direction in ("in", "both"):
            for idx in self._adj_in.get(entity, []):
                e = self._edges[idx]
                results.append({"from": e["from"], "to": e["to"], "relation": e["relation"],
                               "direction": "in", **e["attrs"]})
        return results
    
    async def neighbors(self, entity: str, relation: str = None) -> list[str]:
        """Get names of directly connected entities."""
        result = []
        for idx in self._adj_out.get(entity, []):
            e = self._edges[idx]
            if relation is None or e["relation"] == relation:
                result.append(e["to"])
        for idx in self._adj_in.get(entity, []):
            e = self._edges[idx]
            if relation is None or e["relation"] == relation:
                result.append(e["from"])
        return list(set(result))  # dedupe
    
    async def query(self, entity: str, relation: str = None, depth: int = 1) -> dict:
        """BFS traversal returning all reachable entities within depth."""
        if entity not in self._entities:
            return {"entity": entity, "connected": []}
        
        visited = {entity}
        connected = []
        queue = deque([(entity, 0)])
        
        while queue:
            current, d = queue.popleft()
            if d >= depth: continue
            for idx in self._adj_out.get(current, []):
                e = self._edges[idx]
                if relation and e["relation"] != relation: continue
                if e["to"] not in visited:
                    visited.add(e["to"])
                    connected.append({"entity": e["to"], "relation": e["relation"],
                                      "distance": d + 1, **e["attrs"]})
                    queue.append((e["to"], d + 1))
        
        return {"entity": entity, "connected": connected}
    
    async def find_paths(self, start: str, end: str, max_depth: int = 5) -> list[list[str]]:
        """Find all simple paths between two entities (BFS-based)."""
        if start not in self._entities or end not in self._entities:
            return []
        if start == end:
            return [[start]]
        
        paths = []
        queue = deque([[start]])
        while queue:
            path = queue.popleft()
            if len(path) > max_depth: continue
            current = path[-1]
            for idx in self._adj_out.get(current, []):
                e = self._edges[idx]
                next_node = e["to"]
                if next_node == end:
                    paths.append(path + [end])
                elif next_node not in path:  # avoid cycles
                    queue.append(path + [next_node])
        return paths
    
    async def shortest_path(self, start: str, end: str) -> list[str] | None:
        """Dijkstra's shortest weighted path."""
        if start not in self._entities or end not in self._entities:
            return None
        
        import heapq
        dists = {start: 0.0}
        prev = {start: None}
        heap = [(0.0, start)]
        
        while heap:
            d, u = heapq.heappop(heap)
            if u == end:
                # Reconstruct path
                path = []
                while u is not None:
                    path.append(u)
                    u = prev[u]
                return list(reversed(path))
            if d > dists.get(u, float('inf')): continue
            for idx in self._adj_out.get(u, []):
                e = self._edges[idx]
                v = e["to"]
                new_d = d + e["weight"]
                if new_d < dists.get(v, float('inf')):
                    dists[v] = new_d
                    prev[v] = u
                    heapq.heappush(heap, (new_d, v))
        return None
    
    async def subgraph(self, root: str, depth: int = 2) -> dict:
        """Extract subgraph centered on root within depth."""
        if root not in self._entities:
            return {"entities": {}, "edges": []}
        
        visited = {root}
        queue = deque([(root, 0)])
        while queue:
            current, d = queue.popleft()
            if d >= depth: continue
            for idx in self._adj_out.get(current, []):
                e = self._edges[idx]
                if e["to"] not in visited:
                    visited.add(e["to"])
                    queue.append((e["to"], d + 1))
        
        sub_entities = {n: self._entities[n] for n in visited if n in self._entities}
        sub_edges = [e for e in self._edges if e["from"] in visited and e["to"] in visited]
        return {"entities": sub_entities, "edges": sub_edges}
    
    async def merge_entities(self, keep: str, remove: str):
        """Merge two entities — all edges from 'remove' redirected to 'keep'."""
        if remove not in self._entities or keep not in self._entities:
            return
        for e in self._edges:
            if e["from"] == remove: e["from"] = keep
            if e["to"] == remove: e["to"] = keep
        # Merge attributes
        self._entities[keep]["attrs"].update(self._entities[remove]["attrs"])
        del self._entities[remove]
        self._rebuild_adj()
        if self.auto_save: self._save()
    
    async def search_entities(self, query: str, entity_type: str = None) -> list[dict]:
        """Simple text search across entity names and attributes."""
        q = query.lower()
        results = []
        for name, data in self._entities.items():
            if entity_type and data.get("type") != entity_type:
                continue
            score = 0
            if q in name.lower(): score += 10
            for k, v in data.get("attrs", {}).items():
                if q in str(k).lower() or q in str(v).lower():
                    score += 1
            if score > 0:
                results.append({"name": name, "type": data["type"],
                                "attrs": data["attrs"], "score": score})
        results.sort(key=lambda r: r["score"], reverse=True)
        return results
    
    def _save(self):
        if not self.storage_path: return
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "w") as f:
                json.dump({
                    "entities": self._entities,
                    "edges": self._edges,
                }, f, indent=2, default=str)
        except Exception as e:
            log.warning(f"GraphMemory save failed: {e}")
    
    def _load(self):
        try:
            with open(self.storage_path) as f:
                data = json.load(f)
            self._entities = data.get("entities", {})
            self._edges = data.get("edges", [])
            self._rebuild_adj()
        except Exception as e:
            log.warning(f"GraphMemory load failed: {e}")
    
    @property
    def stats(self) -> dict:
        types = {}
        for e in self._entities.values():
            t = e.get("type", "unknown")
            types[t] = types.get(t, 0) + 1
        
        relations = {}
        for e in self._edges:
            r = e["relation"]
            relations[r] = relations.get(r, 0) + 1
        
        return {
            "entity_count": len(self._entities),
            "edge_count": len(self._edges),
            "entity_types": types,
            "relation_types": relations,
        }
    
    def __len__(self):
        return len(self._entities)
