# Multi-Agent Team

```python
from largestack import Team, Agent
researcher = Agent(name="r", instructions="Research")
writer = Agent(name="w", instructions="Write")
team = Team([researcher, writer], strategy="sequential")
```
