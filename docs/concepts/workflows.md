# Workflows

```python
from largestack import Workflow

wf = Workflow("pipeline", mode="dag")
wf.add_node("extract", extract_fn)
wf.add_node("transform", transform_fn, deps=["extract"])
wf.add_node("load", load_fn, deps=["transform"])

result = await wf.run({"input": "data"})
```

Modes: `dag`, `sequential`, `parallel`, `state_machine`.
