# Testing Without API Calls

```python
from largestack.testing import TestModel, FunctionModel, block_model_requests

# Canned response
test_model = TestModel(custom_output_text="Mocked")

# Or programmatic
def my_logic(messages, info):
    return {"content": f"Echo: {messages[-1]['content']}"}
func_model = FunctionModel(my_logic)

# Block all real LLM calls in tests
with block_model_requests():
    result = await agent.run("test")
```
