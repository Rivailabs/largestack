# Memory

```python
from largestack.memory import create_memory

# 8 built-in types
mem = create_memory("buffer")          # Last N messages
mem = create_memory("episodic")        # Important events
mem = create_memory("semantic")        # Vector search
mem = create_memory("graph")           # Entity graph
mem = create_memory("procedural")      # Skill-based
mem = create_memory("observational")   # User behavior
mem = create_memory("compression")     # Summarized history
mem = create_memory("shared")          # Cross-agent

agent.memory = mem
```
