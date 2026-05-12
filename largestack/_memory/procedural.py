"""Procedural memory — skill/procedure storage (Voyager-style).

Based on the Voyager paper — agents accumulate reusable skills over time.
Each skill has: trigger (when to use), procedure (how), success rate.
"""
from __future__ import annotations
import json, logging, os, time
from typing import Any

log = logging.getLogger("largestack.memory.procedural")

class Skill:
    def __init__(self, name: str, description: str, procedure: str,
                 trigger: str = "", examples: list[str] = None):
        self.name = name
        self.description = description
        self.procedure = procedure
        self.trigger = trigger
        self.examples = examples or []
        self.usage_count = 0
        self.success_count = 0
        self.created_at = time.time()
        self.last_used = None
    
    @property
    def success_rate(self) -> float:
        if self.usage_count == 0: return 0.0
        return self.success_count / self.usage_count
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "procedure": self.procedure,
            "trigger": self.trigger,
            "examples": self.examples,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "success_rate": round(self.success_rate, 3),
            "created_at": self.created_at,
            "last_used": self.last_used,
        }


class ProceduralMemory:
    """Persistent skill library. Agents can add, search, and recall procedures.
    
        pm = ProceduralMemory()
        pm.add_skill(
            name="book_flight",
            description="Search and book a flight between cities",
            procedure="1. Call flight_search API\n2. Filter by price\n3. Book lowest cost",
            trigger="user wants to book travel"
        )
        
        matches = pm.search("how do I book a trip")
    """
    def __init__(self, storage_path: str = None, auto_save: bool = True):
        self.storage_path = os.path.expanduser(storage_path) if storage_path else None
        self.auto_save = auto_save
        self._skills: dict[str, Skill] = {}
        if self.storage_path and os.path.exists(self.storage_path):
            self._load()
    
    async def add_skill(self, name: str, procedure_or_description: str = "",
                        description_or_procedure: str = "",
                        trigger: str = "", examples: list[str] = None,
                        procedure: str = None, description: str = None) -> Skill:
        """Add a new skill. Flexible signature supports both:
        - add_skill(name, procedure, description)   (legacy test format)
        - add_skill(name, description=..., procedure=...)   (keyword form)
        """
        # Resolve with priority: explicit kwargs > positional
        if procedure is None:
            procedure = procedure_or_description
        if description is None:
            description = description_or_procedure or procedure_or_description
        skill = Skill(name, description, procedure, trigger, examples)
        self._skills[name] = skill
        if self.auto_save: self._save()
        return skill
    
    def get_skill(self, name: str) -> Skill | None:
        return self._skills.get(name)
    
    def remove_skill(self, name: str) -> bool:
        if name in self._skills:
            del self._skills[name]
            if self.auto_save: self._save()
            return True
        return False
    
    async def search_skills(self, query: str, k: int = 5) -> list[Skill]:
        '''Async alias for search().'''
        return self.search(query, k)
    
    def search(self, query: str, k: int = 5) -> list[Skill]:
        """Simple keyword search on name, description, trigger."""
        query_lower = query.lower()
        scored = []
        for skill in self._skills.values():
            score = 0
            score += sum(1 for w in query_lower.split() if w in skill.name.lower()) * 3
            score += sum(1 for w in query_lower.split() if w in skill.description.lower()) * 2
            score += sum(1 for w in query_lower.split() if w in skill.trigger.lower())
            # Success rate boost
            score += skill.success_rate
            if score > 0:
                scored.append((score, skill))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:k]]
    
    def record_usage(self, name: str, success: bool = True):
        """Record that a skill was used and whether it succeeded."""
        skill = self._skills.get(name)
        if skill:
            skill.usage_count += 1
            if success: skill.success_count += 1
            skill.last_used = time.time()
            if self.auto_save: self._save()
    
    def top_skills(self, k: int = 10) -> list[Skill]:
        """Get most-used skills by usage count."""
        return sorted(self._skills.values(), key=lambda s: s.usage_count, reverse=True)[:k]
    
    def _save(self):
        if not self.storage_path: return
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "w") as f:
                json.dump({k: v.to_dict() for k, v in self._skills.items()}, f, indent=2)
        except Exception as e:
            log.warning(f"Could not save procedural memory: {e}")
    
    def _load(self):
        try:
            with open(self.storage_path) as f:
                data = json.load(f)
            for name, d in data.items():
                s = Skill(d["name"], d["description"], d["procedure"],
                         d.get("trigger", ""), d.get("examples", []))
                s.usage_count = d.get("usage_count", 0)
                s.success_count = d.get("success_count", 0)
                s.created_at = d.get("created_at", time.time())
                s.last_used = d.get("last_used")
                self._skills[name] = s
        except Exception as e:
            log.warning(f"Could not load procedural memory: {e}")
    
    def __len__(self):
        return len(self._skills)
